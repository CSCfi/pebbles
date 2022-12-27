import datetime
import json

import dpath
import requests
import yaml
from dateutil import parser as dateutil_parser
from openshift.dynamic.exceptions import ConflictError

from pebbles.drivers.provisioning.kubernetes_driver import OpenShiftRemoteDriver
from pebbles.models import ApplicationSession


class OpenShiftTemplateDriver(OpenShiftRemoteDriver):
    """ OpenShift Template Driver allows provisioning application_sessions in an existing OpenShift cluster,
        using an Openshift Template. All the templates require a label defined in the template,
        like - "label: app: <app_label>"

        Similar to the openshift driver, it needs credentials for the cluster in the cluster config

        Since this driver is subclassed from OpenShiftRemoteDriver, it uses a lot of methods from it.
    """

    def do_provision(self, token, application_session_id):
        """ Implements provisioning, called by superclass.
            A namespace is created if necessary.
        """
        application_session = self.fetch_and_populate_application_session(token, application_session_id)
        namespace = self.get_application_session_namespace(application_session)
        self.ensure_namespace(namespace)

        self.logger.info(
            'provisioning %s in namespace %s on cluster %s',
            application_session['name'],
            namespace,
            self.cluster_config['name']
        )

        template_objects = self.render_template_objects(namespace, application_session)
        for template_object in template_objects:
            # label resources to be able to query them later
            dpath.util.new(template_object, '/metadata/labels/sessionName', application_session['name'])
            # add label also to templates (in Deployments, DeploymentConfigs, StatefulSets...) to have labels on pods
            if dpath.search(template_object, '/spec/template/metadata'):
                dpath.util.new(template_object, '/spec/template/metadata/labels/sessionName', application_session['name'])

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
        return ApplicationSession.STATE_STARTING

    def do_check_readiness(self, token, application_session_id):
        """ Implements readiness checking, called by superclass. Checks that all the pods are ready.
        """
        application_session = self.fetch_and_populate_application_session(token, application_session_id)

        # warn if application_session is taking longer than 5 minutes to start
        createts = datetime.datetime.utcfromtimestamp(dateutil_parser.parse(application_session['created_at']).timestamp())
        if datetime.datetime.utcnow().timestamp() - createts.timestamp() > 300:
            self.logger.warning(
                'application_session %s created at %s, is taking a long time to start',
                application_session['name'],
                application_session['created_at']
            )

        namespace = self.get_application_session_namespace(application_session)
        api = self.dynamic_client.resources.get(api_version='v1', kind='Pod')
        pods = api.get(
            namespace=namespace,
            label_selector='application_sessionName=%s' % application_session['name']
        )

        if len(pods.items) < 1:
            self.logger.warning('no pods for application_session %s found', application_session['name'])
            return None

        # check readiness of all pods
        for pod in pods.items:
            if pod.status.phase != 'Running':
                self.logger.debug('pod %s not ready for %s', pod.metadata.name, application_session['name'])
                return None

        # application_session ready, create and publish an endpoint url.
        # This assumes that the template creates a route to the main application in
        # a compatible way (https://application_session-name.application-domain)
        return dict(
            namespace=namespace,
            endpoints=[dict(
                name='https',
                access='%s://%s' % (self.endpoint_protocol, self.get_application_session_hostname(application_session))
            )]
        )

    def do_deprovision(self, token, application_session_id):
        """ Implements deprovisioning, called by superclass.
            Iterates through template object types, queries them by label and deletes all objects.
        """
        application_session = self.fetch_and_populate_application_session(token, application_session_id)
        namespace = self.get_application_session_namespace(application_session)

        self.logger.info(
            'deprovisioning %s in namespace %s on cluster %s',
            application_session['name'],
            namespace,
            self.cluster_config['name']
        )

        template_objects = self.render_template_objects(namespace, application_session)
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
            label_selector = 'sessionName=%s' % application_session['name']
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
                return ApplicationSession.STATE_DELETING

    def render_template_objects(self, namespace, application_session):
        """ Render the template for the application session. This is done on OpenShift server.
        """
        application_config = application_session['provisioning_config']

        template_url = application_config['os_template']
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
            env_var_array = application_config.get('environment_vars', '').split()
            env_var_dict = {k: v for k, v in [x.split('=') for x in env_var_array]}

            # fill template parameters from application application variables
            for template_param in template_yaml['parameters']:
                if template_param['name'] in env_var_dict:
                    env_template_param_val = env_var_dict[template_param['name']]
                    # magic key to fill in the application session name dynamically
                    if env_template_param_val == 'application_session_name':
                        template_param['value'] = application_session['name']
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
