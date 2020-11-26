import os
import time
from enum import Enum, unique
from urllib.parse import urlparse, parse_qs

import kubernetes
import requests
import yaml
from kubernetes.client.rest import ApiException
from openshift.dynamic import DynamicClient

from pebbles.drivers.provisioning import base_driver
from pebbles.models import Instance
from pebbles.utils import b64encode_string


@unique
class VolumePersistenceLevel(Enum):
    INSTANCE_LIFETIME = 1
    ENVIRONMENT_LIFETIME = 2
    USER_LIFETIME = 3


def parse_template(name, values):
    with open(os.path.join(os.path.dirname(__file__), 'templates', name), 'r') as f:
        template = f.read()
        if values:
            return template.format(**values)
        else:
            return template


def get_volume_name(instance, persistence_level=VolumePersistenceLevel.INSTANCE_LIFETIME):
    if persistence_level == VolumePersistenceLevel.INSTANCE_LIFETIME:
        return 'pvc-%s-%s' % (instance['user']['pseudonym'], instance['name'])
    else:
        raise RuntimeError('volume persistence level %s is not supported' % persistence_level)


class KubernetesDriverBase(base_driver.ProvisioningDriverBase):
    @staticmethod
    def get_configuration():
        """ Return the default config values which are needed for the
            driver creation (via schemaform)
        """
        from pebbles.drivers.provisioning.kubernetes_driver_config import CONFIG

        config = CONFIG.copy()
        return config

    def __init__(self, logger, config, cluster_config):
        super().__init__(logger, config, cluster_config)

        self.ingress_app_domain = cluster_config.get('appDomain', 'localhost')
        self.endpoint_protocol = cluster_config.get('endpointProtocol', 'http')
        self._namespace = None

        # this is implemented in subclass
        self.kubernetes_api_client = self.create_kube_client()
        self.dynamic_client = DynamicClient(self.kubernetes_api_client)

    def get_instance_hostname(self, instance):
        return self.ingress_app_domain

    def get_instance_path(self, instance):
        return '/notebooks/%s' % instance['id']

    def get_instance_namespace(self, instance):
        # implement this in subclass if you need to override simple default behaviour
        self.logger.debug('returning static namespace for instance %s' % instance.get('name'))
        return self._namespace

    def ensure_namespace(self, namespace):
        api = self.dynamic_client.resources.get(api_version='v1', kind='Namespace')
        try:
            api.get(name=namespace)
            return
        except ApiException as e:
            # RBAC enabled cluster will give us 403 for a namespace that does not exist as well
            if e.status not in (403, 404):
                raise e
        self.create_namespace(namespace)

    def create_namespace(self, namespace):
        # implement this in subclass
        raise RuntimeWarning('create_namespace() not implemented')

    def create_kube_client(self):
        # implement this in subclass
        raise RuntimeWarning('create_kube_client() not implemented')

    def customize_deployment_dict(self, deployment_dict):
        # override this in subclass to set custom values in deployment

        # check if cluster config has a node selector set
        if 'nodeSelector' in self.cluster_config:
            self.logger.debug('setting nodeSelector in deployment')
            pod_spec = deployment_dict['spec']['template']['spec']
            pod_spec['nodeSelector'] = self.cluster_config['nodeSelector']

        return deployment_dict

    def do_provision(self, token, instance_id):
        instance = self.fetch_and_populate_instance(token, instance_id)
        namespace = self.get_instance_namespace(instance)
        self.ensure_namespace(namespace)
        self.ensure_volume(namespace, instance)
        self.create_deployment(namespace, instance)
        self.create_service(namespace, instance)
        self.create_ingress(namespace, instance)
        # tell base_driver that we need to check on the readiness later by explicitly returning STATE_STARTING
        return Instance.STATE_STARTING

    def do_check_readiness(self, token, instance_id):
        instance = self.fetch_and_populate_instance(token, instance_id)
        namespace = self.get_instance_namespace(instance)
        api = self.dynamic_client.resources.get(api_version='v1', kind='Pod')
        pods = api.get(
            namespace=namespace,
            label_selector='name=%s' % instance.get('name')
        )

        if len(pods.items) != 1:
            raise RuntimeWarning('pod results length is not one. dump: %s' % pods.to_str())

        pod = pods.items[0]
        if pod.status.phase == 'Running':
            # instance ready, create and publish an endpoint url. note that we pick the protocol
            # from a property that can be set in a subclass
            return dict(
                namespace=namespace,
                endpoints=[dict(
                    name='https',
                    access='%s://%s%s' % (
                        self.endpoint_protocol,
                        self.get_instance_hostname(instance),
                        self.get_instance_path(instance)
                    )
                )]
            )

        return None

    def do_deprovision(self, token, instance_id):
        instance = self.fetch_and_populate_instance(token, instance_id)
        namespace = self.get_instance_namespace(instance)
        # remove deployment
        try:
            self.delete_deployment(namespace, instance)
        except ApiException as e:
            if e.status == 404:
                self.logger.warning('Deployment not found, assuming it is already deleted')
            else:
                raise e

        # remove service
        try:
            self.delete_service(namespace, instance)
        except ApiException as e:
            if e.status == 404:
                self.logger.warning('Service not found, assuming it is already deleted')
            else:
                raise e

        # remove ingress
        try:
            self.delete_ingress(namespace, instance)
        except ApiException as e:
            if e.status == 404:
                self.logger.warning('Ingress not found, assuming it is already deleted')
            else:
                raise e

        # remove volume (only level 1 persistence implemented so far)
        try:
            volume_name = get_volume_name(instance)
            self.delete_volume(namespace, volume_name)
        except ApiException as e:
            if e.status == 404:
                self.logger.warning('Volume not found, assuming it is already deleted')
            else:
                raise e

    def do_housekeep(self, token):
        pass

    def do_update_connectivity(self, token, instance_id):
        pass

    def get_running_instance_logs(self, token, instance_id):
        pass

    def is_expired(self):
        if 'token_expires_at' in self.cluster_config.keys():
            if self.cluster_config.get('token_expires_at') < time.time() + 600:
                return True
        return False

    def create_deployment(self, namespace, instance):

        environment_config = instance['environment']['full_config']

        # create a dict out of space separated list of VAR=VAL entries
        env_var_array = environment_config.get('environment_vars', '').split()
        env_var_dict = {k: v for k, v in [x.split('=') for x in env_var_array]}
        env_var_dict['INSTANCE_ID'] = instance['id']
        env_var_list = [dict(name=x, value=env_var_dict[x]) for x in env_var_dict.keys()]

        deployment_yaml = parse_template('deployment.yaml', dict(
            name=instance['name'],
            image=environment_config['image'],
            volume_mount_path=environment_config['volume_mount_path'],
            pvc_name=get_volume_name(instance)
        ))
        deployment_dict = yaml.safe_load(deployment_yaml)
        deployment_dict['spec']['template']['spec']['containers'][0]['env'] = env_var_list

        # process templated arguments
        if 'args' in environment_config:
            args = environment_config.get('args').format(
                instance_id='%s' % instance['id']
            )
            deployment_dict['spec']['template']['spec']['containers'][0]['args'] = args.split()

        deployment_dict = self.customize_deployment_dict(deployment_dict)

        self.logger.debug('creating deployment\n%s' % yaml.safe_dump(deployment_dict))

        api = self.dynamic_client.resources.get(api_version='apps/v1', kind='Deployment')
        return api.create(body=deployment_dict, namespace=namespace)

    def delete_deployment(self, namespace, instance):
        self.logger.debug('deleting deployment %s' % instance.get('name'))
        api_deployment = self.dynamic_client.resources.get(api_version='apps/v1', kind='Deployment')
        return api_deployment.delete(namespace=namespace, name=instance.get('name'))

    def create_service(self, namespace, instance):
        service_yaml = parse_template('service.yaml', dict(
            name=instance['name'],
            target_port=instance['environment']['full_config']['port']
        ))
        self.logger.debug('creating service\n%s' % service_yaml)

        api = self.dynamic_client.resources.get(api_version='v1', kind='Service')
        return api.create(body=yaml.safe_load(service_yaml), namespace=namespace)

    def delete_service(self, namespace, instance):
        self.logger.debug('deleting service %s' % instance.get('name'))
        api = self.dynamic_client.resources.get(api_version='v1', kind='Service')
        api.delete(
            namespace=namespace,
            name=instance.get('name')
        )

    def create_ingress(self, namespace, instance):
        ingress_yaml = parse_template('ingress.yaml', dict(
            name=instance['name'],
            path=self.get_instance_path(instance),
            host=self.get_instance_hostname(instance),
        ))
        self.logger.debug('creating ingress\n%s' % ingress_yaml)

        api = self.dynamic_client.resources.get(api_version='extensions/v1beta1', kind='Ingress')
        return api.create(body=yaml.load(ingress_yaml), namespace=namespace)

    def delete_ingress(self, namespace, instance):
        self.logger.debug('deleting ingress %s' % instance.get('name'))
        api = self.dynamic_client.resources.get(api_version='extensions/v1beta1', kind='Ingress')
        api.delete(namespace=namespace, name=instance.get('name'))

    def ensure_volume(self, namespace, instance):
        volume_name = get_volume_name(instance)
        api = self.dynamic_client.resources.get(api_version='v1', kind='PersistentVolumeClaim')
        try:
            api.get(namespace=namespace, name=volume_name)
            return
        except ApiException as e:
            if e.status != 404:
                raise e
        return self.create_volume(namespace, volume_name)

    def create_volume(self, namespace, volume_name):
        pvc_yaml = parse_template('pvc.yaml', dict(
            name=volume_name,
            storage_size='1Gi',
        ))
        pvc_dict = yaml.safe_load(pvc_yaml)
        storage_class_name = self.cluster_config.get('storageClassName')
        if storage_class_name is not None:
            pvc_dict['spec']['storageClassName'] = storage_class_name

        self.logger.debug('creating pvc\n%s' % pvc_yaml)

        api = self.dynamic_client.resources.get(api_version='v1', kind='PersistentVolumeClaim')
        return api.create(body=pvc_dict, namespace=namespace)

    def delete_volume(self, namespace, volume_name):
        self.logger.debug('deleting volume %s' % volume_name)
        api = self.dynamic_client.resources.get(api_version='v1', kind='PersistentVolumeClaim')
        api.delete(
            namespace=namespace,
            name=volume_name
        )

    def fetch_and_populate_instance(self, token, instance_id):
        pbclient = self.get_pb_client(token)
        instance = pbclient.get_instance(instance_id)
        instance['environment'] = pbclient.get_instance_environment(instance_id)
        instance['user'] = pbclient.get_user(instance['user_id'])

        return instance


class KubernetesLocalDriver(KubernetesDriverBase):
    def create_kube_client(self):
        # pick up our namespace
        with open('/var/run/secrets/kubernetes.io/serviceaccount/namespace', mode='r') as f:
            self._namespace = f.read()
        self.logger.debug('detected namespace: %s', self._namespace)

        # load service account based config
        kubernetes.config.load_incluster_config()
        return kubernetes.client.ApiClient()


class KubernetesRemoteDriver(KubernetesDriverBase):
    def create_kube_client(self):
        # load cluster config from kubeconfig
        context = self.cluster_config['name']
        self.logger.debug('loading context %s from /var/run/secrets/pebbles/cluster-kubeconfig', context)
        return kubernetes.config.new_client_from_config(
            config_file='/var/run/secrets/pebbles/cluster-kubeconfig',
            context=self.cluster_config['name']
        )

    def get_instance_namespace(self, instance):
        if 'instance_data' in instance and 'namespace' in instance['instance_data']:
            # instance already has namespace assigned in instance_data
            namespace = instance['instance_data']['namespace']
            self.logger.debug('found namespace %s for instance %s' % (namespace, instance.get('name')))
        elif 'namespace' in self.cluster_config.keys():
            # if we have a single namespace configured, use that
            namespace = self.cluster_config['namespace']
            self.logger.debug('using fixed namespace %s for instance %s' % (namespace, instance.get('name')))
        else:
            # generate namespace name based on prefix and user pseudonym
            namespace_prefix = self.cluster_config.get('namespacePrefix', 'pb-')
            namespace = '%s%s' % (namespace_prefix, instance['user']['pseudonym'])
            self.logger.debug('assigned namespace %s to instance %s' % (namespace, instance.get('name')))
        return namespace

    def create_namespace(self, namespace):
        self.logger.info('creating namespace %s' % namespace)
        namespace_yaml = parse_template('namespace.yaml', dict(
            name=namespace,
        ))
        api = self.dynamic_client.resources.get(api_version='v1', kind='Namespace')
        namespace_res = api.create(body=yaml.load(namespace_yaml))

        # create a network policy for isolating the pods in the namespace
        self.logger.info('creating default network policy in namespace %s' % namespace)
        networkpolicy_yaml = parse_template('networkpolicy.yaml', dict())
        api = self.dynamic_client.resources.get(api_version='networking.k8s.io/v1', kind='NetworkPolicy')
        api.create(body=yaml.load(networkpolicy_yaml), namespace=namespace)

        return namespace_res


class OpenShiftLocalDriver(KubernetesLocalDriver):

    def create_ingress(self, namespace, instance):
        pod_name = instance.get('name')
        route_yaml = parse_template('route.yaml', dict(
            name=pod_name,
            host=self.get_instance_hostname(instance)
        ))
        api = self.dynamic_client.resources.get(api_version='route.openshift.io/v1', kind='Route')
        api.create(body=yaml.safe_load(route_yaml), namespace=namespace)

    def delete_ingress(self, namespace, instance):
        api = self.dynamic_client.resources.get(api_version='route.openshift.io/v1', kind='Route')
        api.delete(name=instance.get('name'), namespace=namespace)

    def get_instance_hostname(self, instance):
        return '%s.%s' % (instance.get('name'), self.ingress_app_domain)

    def get_instance_path(self, instance):
        return ''


class OpenShiftRemoteDriver(OpenShiftLocalDriver):

    @staticmethod
    def _request_token(base_url, user, password):
        # oauth url (could also get this dynamically from HOST/.well-known/oauth-authorization-server)
        url = base_url + '/oauth/authorize'
        auth_encoded = b64encode_string('%s:%s' % (user, password))
        headers = {
            'Authorization': 'Basic %s' % str(auth_encoded),
            'X-Csrf-Token': '1'
        }
        params = {
            'response_type': 'token',
            'client_id': 'openshift-challenging-client'
        }

        # get a token
        resp = requests.get(url, headers=headers, params=params, allow_redirects=False)

        # the server replies with a redirect, the data is in 'location'
        location = resp.headers.get('location')
        parsed_data = urlparse(location)
        parsed_query = parse_qs(parsed_data.fragment)

        return {
            'access_token': parsed_query['access_token'][0],
            'lifetime': int(parsed_query['expires_in'][0]),
            'expires_at': int(parsed_query['expires_in'][0]) + int(time.time()),
        }

    def create_kube_client(self):
        try:
            token = self._request_token(
                base_url=self.cluster_config.get('url'),
                user=self.cluster_config.get('user'),
                password=self.cluster_config.get('password')
            )
        except Exception as e:
            self.logger.warning(
                'Could not request token, check values for url, user and password for cluster %s',
                self.cluster_config['name']
            )
            raise e

        self.logger.debug('got token %s....' % token['access_token'][:10])
        self.cluster_config['token'] = token['access_token']
        self.cluster_config['token_expires_at'] = token['expires_at']

        conf = kubernetes.client.Configuration()
        conf.host = self.cluster_config.get('url')
        conf.api_key = dict(authorization='Bearer %s' % self.cluster_config['token'])

        return kubernetes.client.ApiClient(conf)

    def get_instance_namespace(self, instance):
        if 'instance_data' in instance and 'namespace' in instance['instance_data']:
            # instance already has namespace assigned in instance_data
            namespace = instance['instance_data']['namespace']
            self.logger.debug('found namespace %s for instance %s' % (namespace, instance.get('name')))
        elif 'namespace' in self.cluster_config.keys():
            # if we have a single namespace configured, use that
            namespace = self.cluster_config['namespace']
            self.logger.debug('using fixed namespace %s for instance %s' % (namespace, instance.get('name')))
        else:
            # generate namespace name based on prefix and user pseudonym
            namespace_prefix = self.cluster_config.get('namespacePrefix', 'pb-')
            namespace = '%s%s' % (namespace_prefix, instance['user']['pseudonym'])
            self.logger.debug('assigned namespace %s to instance %s' % (namespace, instance.get('name')))
        return namespace

    def create_namespace(self, namespace):
        self.logger.info('creating namespace %s' % namespace)
        project_data = dict(kind='ProjectRequest', apiVersion='project.openshift.io/v1', metadata=dict(name=namespace))

        api = self.dynamic_client.resources.get(api_version='project.openshift.io/v1', kind='ProjectRequest')
        api.create(body=project_data)
