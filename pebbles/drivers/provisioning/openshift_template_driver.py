import datetime
import json

import dpath
import requests
import yaml
from dateutil import parser as dateutil_parser
from openshift.dynamic.exceptions import ConflictError

from pebbles.drivers.provisioning.kubernetes_driver import OpenShiftRemoteDriver
from pebbles.models import EnvironmentSession


class OpenShiftTemplateDriver(OpenShiftRemoteDriver):
    """ OpenShift Template Driver allows provisioning environment_sessions in an existing OpenShift cluster,
        using an Openshift Template. All the templates require a label defined in the template,
        like - "label: app: <app_label>"

        Similar to the openshift driver, it needs credentials for the cluster in the cluster config

        Since this driver is subclassed from OpenShiftRemoteDriver, it uses a lot of methods from it.
    """

    @staticmethod
    def get_configuration():
        """ Return the default config values which are needed for the
            driver creation (via schemaform)
        """
        from pebbles.drivers.provisioning.openshift_template_driver_config import CONFIG

        config = CONFIG.copy()
        return config

    def do_provision(self, token, environment_session_id):
        """ Implements provisioning, called by superclass.
            A namespace is created if necessary.
        """
        environment_session = self.fetch_and_populate_environment_session(token, environment_session_id)
        namespace = self.get_environment_session_namespace(environment_session)
        self.ensure_namespace(namespace)

        self.logger.info(
            'provisioning %s in namespace %s on cluster %s',
            environment_session['name'],
            namespace,
            self.cluster_config['name']
        )

        template_objects = self.render_template_objects(namespace, environment_session)
        for template_object in template_objects:
            # label resources to be able to query them later
            dpath.util.new(template_object, '/metadata/labels/sessionName', environment_session['name'])
            # add label also to templates (in Deployments, DeploymentConfigs, StatefulSets...) to have labels on pods
            if dpath.search(template_object, '/spec/template/metadata'):
                dpath.util.new(template_object, '/spec/template/metadata/labels/sessionName', environment_session['name'])

            try:
                client = self.dynamic_client.resources.get(
                    api_version=template_object['apiVersion'],
                    kind=template_object['kind']
                )
                resp = client.create(body=template_object, namespace=namespace)
                self.logger.debug('created %s %s', resp.kind, resp.metadata.name)
            except ConflictError:
                self.logger.info(
                    "%s %s already exists",
                    template_object['kind'],
                    template_object['metadata']['name']
                )

        # tell base_driver that we need to check on the readiness later by explicitly returning STATE_STARTING
        return EnvironmentSession.STATE_STARTING

    def do_check_readiness(self, token, environment_session_id):
        """ Implements readiness checking, called by superclass. Checks that all the pods are ready.
        """
        environment_session = self.fetch_and_populate_environment_session(token, environment_session_id)

        # warn if environment_session is taking longer than 5 minutes to start
        createts = datetime.datetime.utcfromtimestamp(dateutil_parser.parse(environment_session['created_at']).timestamp())
        if datetime.datetime.utcnow().timestamp() - createts.timestamp() > 300:
            self.logger.warning(
                'environment_session %s created at %s, is taking a long time to start',
                environment_session['name'],
                environment_session['created_at']
            )

        namespace = self.get_environment_session_namespace(environment_session)
        api = self.dynamic_client.resources.get(api_version='v1', kind='Pod')
        pods = api.get(
            namespace=namespace,
            label_selector='environment_sessionName=%s' % environment_session['name']
        )

        if len(pods.items) < 1:
            self.logger.warning('no pods for environment_session %s found', environment_session['name'])
            return None

        # check readiness of all pods
        for pod in pods.items:
            if pod.status.phase != 'Running':
                self.logger.debug('pod %s not ready for %s', pod.metadata.name, environment_session['name'])
                return None

        # environment_session ready, create and publish an endpoint url.
        # This assumes that the template creates a route to the main application in
        # a compatible way (https://environment_session-name.application-domain)
        return dict(
            namespace=namespace,
            endpoints=[dict(
                name='https',
                access='%s://%s' % (self.endpoint_protocol, self.get_environment_session_hostname(environment_session))
            )]
        )

    def do_deprovision(self, token, environment_session_id):
        """ Implements deprovisioning, called by superclass.
            Iterates through template object types, queries them by label and deletes all objects.
        """
        environment_session = self.fetch_and_populate_environment_session(token, environment_session_id)
        namespace = self.get_environment_session_namespace(environment_session)

        self.logger.info(
            'deprovisioning %s in namespace %s on cluster %s',
            environment_session['name'],
            namespace,
            self.cluster_config['name']
        )

        template_objects = self.render_template_objects(namespace, environment_session)
        processed_types = list()

        for template_object in template_objects:
            # check and record if we have already processed these kind of objects
            object_type = '%s/%s' % (template_object['apiVersion'], template_object['kind'])
            if object_type in processed_types:
                continue
            processed_types.append(object_type)

            client = self.dynamic_client.resources.get(
                api_version=template_object['apiVersion'],
                kind=template_object['kind']
            )
            label_selector = 'sessionName=%s' % environment_session['name']
            # noinspection PyBroadException
            try:
                # we need to list objects and delete them individually, because not all object types
                # support deletion by label
                # https://github.com/kubernetes/client-go/issues/409
                res = client.get(namespace=namespace, label_selector=label_selector)

                for obj in res.items:
                    client.delete(namespace=namespace, name=obj.metadata.name)
                    self.logger.debug('deleted %s/%s in namespace %s', object_type, obj.metadata.name, namespace)
                else:
                    self.logger.debug('no %s found by label %s in namespace %s', object_type, label_selector, namespace)
            except Exception:
                self.logger.warning(
                    'failed deleting %s by label %s in namespace %s',
                    object_type, label_selector, namespace
                )
                # retry
                return EnvironmentSession.STATE_DELETING

    def render_template_objects(self, namespace, environment_session):
        """ Render the template for the environment session. This is done on OpenShift server.
        """
        environment_config = environment_session['environment']['full_config']

        template_url = environment_config['os_template']
        if not template_url:
            raise RuntimeError('No template url given')

        try:
            template_url_data = requests.get(template_url)
            template_yaml = yaml.safe_load(template_url_data.text)
        except Exception as e:
            raise RuntimeError(e)

        if not template_yaml:
            raise RuntimeError('No template yaml could be loaded')

        if 'parameters' in template_yaml:
            # create a dict out of space separated list of VAR=VAL entries
            env_var_array = environment_config.get('environment_vars', '').split()
            env_var_dict = {k: v for k, v in [x.split('=') for x in env_var_array]}

            # fill template parameters from environment environment variables
            for template_param in template_yaml['parameters']:
                if template_param['name'] in env_var_dict:
                    env_template_param_val = env_var_dict[template_param['name']]
                    # magic key to fill in the environment session name dynamically
                    if env_template_param_val == 'environment_session_name':
                        template_param['value'] = environment_session['name']
                    else:
                        template_param['value'] = env_template_param_val

        # post the filled template to server to get objects back
        template_objects_resp = self.dynamic_client.request(
            method='POST',
            path='/apis/template.openshift.io/v1/namespaces/%s/processedtemplates' % namespace,
            body=template_yaml,
        )
        template_objects_json = json.loads(template_objects_resp.data)
        return template_objects_json['objects']
