import datetime
import logging
import os
import time
from enum import Enum, unique
from pathlib import Path
from urllib.parse import urlparse, parse_qs

import jinja2
import kubernetes
import requests
import yaml
from kubernetes.client.rest import ApiException
from openshift.dynamic import DynamicClient

from pebbles.drivers.provisioning import base_driver
from pebbles.models import ApplicationSession
from pebbles.utils import b64encode_string

# limit for application session startup duration before it is marked as failed
SESSION_STARTUP_TIME_LIMIT = 30 * 60


@unique
class VolumePersistenceLevel(Enum):
    SESSION_LIFETIME = 1
    WORKSPACE_LIFETIME = 2
    USER_LIFETIME = 3


def format_with_jinja2(str, values):
    template = jinja2.Template(str)
    return template.render(values)


def parse_template(name, values):
    with open(os.path.join(os.path.dirname(__file__), 'templates', name), 'r') as f:
        template = f.read()
        return format_with_jinja2(template, values)


def get_session_volume_name(application_session, persistence_level=VolumePersistenceLevel.SESSION_LIFETIME):
    if persistence_level == VolumePersistenceLevel.SESSION_LIFETIME:
        return 'pvc-%s-%s' % (application_session['user']['pseudonym'], application_session['name'])
    else:
        raise RuntimeError('volume persistence level %s is not supported' % persistence_level)


def get_user_work_volume_name(application_session, persistence_level=VolumePersistenceLevel.WORKSPACE_LIFETIME):
    if persistence_level != VolumePersistenceLevel.WORKSPACE_LIFETIME:
        raise RuntimeError('volume persistence level %s is not supported' % persistence_level)

    if application_session['provisioning_config']['custom_config'].get('enable_user_work_folder'):
        return 'pvc-%s-work' % application_session['user']['pseudonym']

    return None


def get_shared_volume_name(application_session):
    if application_session['provisioning_config']['custom_config'].get('enable_shared_folder', False):
        return 'pvc-ws-vol-1'

    return None


class KubernetesDriverBase(base_driver.ProvisioningDriverBase):
    def __init__(self, logger, config, cluster_config, token):
        super().__init__(logger, config, cluster_config, token)

        self.ingress_app_domain = cluster_config.get('appDomain', 'localhost')
        self.endpoint_protocol = cluster_config.get('endpointProtocol', 'http')
        self._namespace = None
        self.kubernetes_api_client = None
        self.dynamic_client = None

    def get_application_session_hostname(self, application_session):
        return self.ingress_app_domain

    def get_application_session_path(self, application_session):
        return '/notebooks/%s' % application_session['id']

    def get_namespace(self, workspace_id):
        if 'namespace' in self.cluster_config.keys():
            # if we have a single namespace configured, use that
            namespace = self.cluster_config['namespace']
            self.logger.debug('using fixed namespace %s')
        else:
            # generate namespace name based on prefix and workspace pseudonym
            namespace_prefix = self.cluster_config.get('namespacePrefix', 'pb-')
            ws = self.pb_client.get_workspace(workspace_id)
            namespace = '%s%s' % (namespace_prefix, ws.get('pseudonym'))

        return namespace

    def get_application_session_namespace(self, application_session):
        if 'session_data' in application_session and 'namespace' in application_session['session_data']:
            # application_session already has namespace assigned in session_data
            namespace = application_session['session_data']['namespace']
            self.logger.debug('found namespace %s for session %s' % (namespace, application_session.get('name')))
        else:
            namespace = self.get_namespace(application_session['application']['workspace_id'])
            self.logger.debug('assigned namespace %s to session %s' % (namespace, application_session.get('name')))

        return namespace

    def connect(self):
        # create_kube_client() is implemented by subclasses
        self.kubernetes_api_client = self.create_kube_client()

        self.test_connection()

        # create dynamic client for actual use - this requires a working connection
        self.dynamic_client = DynamicClient(self.kubernetes_api_client)

    def test_connection(self):
        logging.debug('testing connection to Kubernetes API')
        api = kubernetes.client.CoreV1Api(self.kubernetes_api_client)
        api.get_api_resources(_request_timeout=2)

    def namespace_exists(self, namespace):
        logging.debug('checking if namespace %s exists', namespace)
        api = self.dynamic_client.resources.get(api_version='v1', kind='Namespace')
        try:
            api.get(name=namespace)
        except ApiException as e:
            # RBAC enabled cluster will give us 403 for a namespace that does not exist as well
            if e.status in (403, 404):
                return False
            else:
                raise

        return True

    def ensure_namespace(self, namespace):
        if not self.namespace_exists(namespace):
            self.create_namespace(namespace)

    def create_namespace(self, namespace):
        self.logger.info('creating namespace %s' % namespace)
        namespace_yaml = parse_template('namespace.yaml', dict(
            name=namespace,
        ))
        api = self.dynamic_client.resources.get(api_version='v1', kind='Namespace')
        namespace_res = api.create(body=yaml.safe_load(namespace_yaml))

        # create a network policy for isolating the pods in the namespace
        # the template blocks traffic to all private ipv4 networks
        self.logger.info('creating default network policy in namespace %s' % namespace)
        networkpolicy_yaml = parse_template('networkpolicy.yaml', {})
        api = self.dynamic_client.resources.get(api_version='networking.k8s.io/v1', kind='NetworkPolicy')
        api.create(body=yaml.safe_load(networkpolicy_yaml), namespace=namespace)

        return namespace_res

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

    def do_provision(self, token, application_session_id):
        # figure out parameters
        application_session = self.fetch_and_populate_application_session(token, application_session_id)
        namespace = self.get_application_session_namespace(application_session)
        session_volume_name = get_session_volume_name(application_session)
        user_volume_name = get_user_work_volume_name(application_session)
        shared_volume_name = get_shared_volume_name(application_session)
        session_storage_class_name = self.cluster_config.get('storageClassNameSession')
        user_storage_class_name = self.cluster_config.get('storageClassNameUser')
        shared_storage_class_name = self.cluster_config.get('storageClassNameShared')

        session_volume_size = self.cluster_config.get('volumeSizeSession', '5Gi')
        shared_volume_size = self.cluster_config.get('volumeSizeShared', '20Gi')
        user_volume_size = '%dGi' % application_session['provisioning_config'].get('user_work_folder_size_gib', 1)

        # create namespace if necessary
        self.ensure_namespace(namespace)
        # create volumes if necessary
        self.ensure_volume(namespace, application_session,
                           session_volume_name, session_volume_size, session_storage_class_name)
        self.ensure_volume(namespace, application_session,
                           shared_volume_name, shared_volume_size, shared_storage_class_name,
                           access_mode='ReadWriteMany',
                           annotations={'pebbles.csc.fi/backup': 'yes'})
        if user_volume_name:
            self.ensure_volume(namespace, application_session,
                               user_volume_name, user_volume_size, user_storage_class_name,
                               access_mode='ReadWriteMany',
                               annotations={'pebbles.csc.fi/backup': 'yes'})

        # create actual session/application_session objects
        self.create_deployment(namespace, application_session)
        self.create_configmap(namespace, application_session)
        self.create_service(namespace, application_session)
        self.create_ingress(namespace, application_session)

        # tell base_driver that we need to check on the readiness later by explicitly returning STATE_STARTING
        return ApplicationSession.STATE_STARTING

    def do_check_readiness(self, token, application_session_id):
        application_session = self.fetch_and_populate_application_session(token, application_session_id)
        namespace = self.get_application_session_namespace(application_session)
        pod_api = self.dynamic_client.resources.get(api_version='v1', kind='Pod')
        pods = pod_api.get(
            namespace=namespace,
            label_selector='name=%s' % application_session.get('name')
        )

        # if it is long since creation, mark the application session as failed
        # TODO: when we implement queueing, change the reference time
        create_ts = datetime.datetime.fromisoformat(application_session['created_at']).timestamp()
        if create_ts < time.time() - SESSION_STARTUP_TIME_LIMIT:
            raise RuntimeWarning('application_session %s takes too long to start' % application_session_id)

        # no pods, continue waiting
        if len(pods.items) == 0:
            return None

        # more than one pod with given search condition, we have a logic error
        if len(pods.items) > 1:
            raise RuntimeWarning('pod results length is not one. dump: %s' % pods.to_str())

        pod = pods.items[0]
        # first check that the pod is running, then check readiness of all containers
        if pod.status.phase == 'Running' and not [x for x in pod.status.containerStatuses if not x.ready]:
            # application session ready, create and publish an endpoint url. note that we pick the protocol
            # from a property that can be set in a subclass
            return dict(
                namespace=namespace,
                endpoints=[dict(
                    name='https',
                    access='%s://%s%s' % (
                        self.endpoint_protocol,
                        self.get_application_session_hostname(application_session),
                        self.get_application_session_path(application_session) + '/'
                    )
                )]
            )

        # pod not ready yet, extract status for the user
        event_api = self.dynamic_client.resources.get(api_version='v1', kind='Event')
        event_resp = event_api.get(
            namespace=namespace,
            field_selector='involvedObject.name=%s' % pod.metadata.name
        )
        if event_resp.items:
            # turn k8s events into provisioning log entries
            def extract_log_entries(x):
                event_time = x.firstTimestamp if x.firstTimestamp else x.eventTime
                ts = datetime.datetime.fromisoformat(event_time[:-1]).timestamp()
                if ts < time.time() - 30:
                    return None
                if 'assigned' in x.message:
                    return ts, 'scheduled to a node'
                if 'ulling image' in x.message:
                    return ts, 'pulling container image'
                if 'olume' in x.message:
                    return ts, 'waiting for volumes'
                if 'eadiness probe' in x.message:
                    return ts, 'starting'
                if 'reated container' in x.message:
                    return ts, 'starting'
                for msg in ('ErrImagePull', 'ImagePullBackOff', 'Failed to pull image', 'Back-off pulling image'):
                    if msg in x.message:
                        return ts, 'image could not be pulled'

                return None

            log_entries = map(extract_log_entries, event_resp.items)
            log_entries = [x for x in log_entries if x]
            if log_entries:
                ts, message = log_entries[-1]
                self.get_pb_client().add_provisioning_log(
                    application_session_id=application_session_id,
                    timestamp=ts,
                    message=message
                )

        return None

    def do_deprovision(self, token, application_session_id):
        application_session = self.fetch_and_populate_application_session(token, application_session_id)
        namespace = self.get_application_session_namespace(application_session)
        # remove deployment
        try:
            self.delete_deployment(namespace, application_session)
        except ApiException as e:
            if e.status == 404:
                self.logger.warning('Deployment not found, assuming it is already deleted')
            else:
                raise e

        # remove configmap
        try:
            self.delete_configmap(namespace, application_session)
        except ApiException as e:
            if e.status == 404:
                self.logger.warning('ConfigMap not found, assuming it is already deleted')
            else:
                raise e

        # remove service
        try:
            self.delete_service(namespace, application_session)
        except ApiException as e:
            if e.status == 404:
                self.logger.warning('Service not found, assuming it is already deleted')
            else:
                raise e

        # remove ingress
        try:
            self.delete_ingress(namespace, application_session)
        except ApiException as e:
            if e.status == 404:
                self.logger.warning('Ingress not found, assuming it is already deleted')
            else:
                raise e

        # remove user volume (only level 1 persistence implemented so far)
        try:
            volume_name = get_session_volume_name(application_session)
            self.delete_volume(namespace, volume_name)
        except ApiException as e:
            if e.status == 404:
                self.logger.warning('Volume not found, assuming it is already deleted')
            else:
                raise e

    def do_housekeep(self, token):
        pass

    def do_get_running_logs(self, token, application_session_id):
        application_session = self.fetch_and_populate_application_session(token, application_session_id)
        namespace = self.get_application_session_namespace(application_session)
        api = self.dynamic_client.resources.get(api_version='v1', kind='Pod')
        pods = api.get(
            namespace=namespace,
            label_selector='name=%s' % application_session.get('name')
        )
        if len(pods.items) != 1:
            raise RuntimeWarning('pod results length is not one. dump: %s' % pods.to_str())

        # now we got the pod, query the logs
        resp = self.dynamic_client.request(
            'GET',
            '/api/v1/namespaces/%s/pods/%s/log?container=pebbles-session' % (namespace, pods.items[0].metadata.name))
        return resp

    def is_expired(self):
        if 'token_expires_at' in self.cluster_config.keys():
            if self.cluster_config.get('token_expires_at') < time.time() + 600:
                return True
        return False

    def create_deployment(self, namespace, application_session):
        # get provisioning configuration and extract application specific custom config
        provisioning_config = application_session['provisioning_config']
        custom_config = provisioning_config['custom_config']

        # create a dict out of space separated list of VAR=VAL entries
        env_var_array = provisioning_config.get('environment_vars', '').split()
        env_var_dict = {k: v for k, v in [x.split('=') for x in env_var_array]}
        env_var_dict['SESSION_ID'] = application_session['id']
        if custom_config.get('download_method', 'none') != 'none':
            env_var_dict['AUTODOWNLOAD_METHOD'] = custom_config.get('download_method', '')
            env_var_dict['AUTODOWNLOAD_URL'] = custom_config.get('download_url', '')

        # set memory in bytes as an env variable, consumed by jupyter-resource-usage
        memory_bytes = round(float(provisioning_config['memory_gib']) * 1024 * 1024 * 1024)
        env_var_dict['MEM_LIMIT'] = str(memory_bytes)

        # set cpu_limit as an env variable, consumed by jupyter-resource-usage
        env_var_dict['CPU_LIMIT'] = str(provisioning_config.get('cpu_limit', '8'))

        # turn environment variable dict to list
        env_var_list = [dict(name=x, value=env_var_dict[x]) for x in env_var_dict.keys()]

        # admins do not have this defined, so first check if we have membership
        if application_session['workspace_membership']:
            # read_write only for managers
            shared_data_read_only_mode = not application_session['workspace_membership']['is_manager']
        else:
            shared_data_read_only_mode = True

        deployment_yaml = parse_template('deployment.yaml.j2', dict(
            name=application_session['name'],
            image=provisioning_config['image'],
            image_pull_policy=provisioning_config.get('image_pull_policy', 'IfNotPresent'),
            volume_mount_path=provisioning_config['volume_mount_path'],
            port=int(provisioning_config['port']),
            cpu_limit=provisioning_config.get('cpu_limit', '8'),
            memory_limit=provisioning_config.get('memory_limit', '512Mi'),
            pvc_name_session=get_session_volume_name(application_session),
            pvc_name_user_work=get_user_work_volume_name(application_session),
            pvc_name_shared=get_shared_volume_name(application_session),
            shared_data_read_only_mode=shared_data_read_only_mode,
        ))
        deployment_dict = yaml.safe_load(deployment_yaml)

        # find the spec for pebbles application_session container
        application_session_spec = list(filter(
            lambda x: x['name'] == 'pebbles-session',
            deployment_dict['spec']['template']['spec']['containers']))[0]
        application_session_spec['env'] = env_var_list
        deployment_dict['spec']['template']['spec']['initContainers'][0]['env'] = env_var_list

        # process templated arguments
        if 'args' in provisioning_config:
            args = format_with_jinja2(
                provisioning_config.get('args'),
                dict(
                    session_id='%s' % application_session['id'],
                    **custom_config
                )
            )
            application_session_spec['args'] = args.split()

        # add custom tolerations
        toleration_spec = deployment_dict['spec']['template']['spec']['tolerations']
        for toleration in provisioning_config.get('scheduler_tolerations', []):
            k, v = toleration.split('=')
            toleration_spec.append(dict(key=k, value=v, effect='NoSchedule'))

        deployment_dict = self.customize_deployment_dict(deployment_dict)

        self.logger.debug('creating deployment\n%s' % yaml.safe_dump(deployment_dict))

        api = self.dynamic_client.resources.get(api_version='apps/v1', kind='Deployment')
        return api.create(body=deployment_dict, namespace=namespace)

    def delete_deployment(self, namespace, application_session):
        self.logger.debug('deleting deployment %s' % application_session.get('name'))
        api_deployment = self.dynamic_client.resources.get(api_version='apps/v1', kind='Deployment')
        return api_deployment.delete(namespace=namespace, name=application_session.get('name'))

    def create_configmap(self, namespace, application_session):
        provisioning_config = application_session['provisioning_config']

        configmap_yaml = parse_template('configmap.yaml', dict(
            name=application_session['name'],
        ))
        configmap_dict = yaml.safe_load(configmap_yaml)
        if application_session['provisioning_config'].get('proxy_rewrite') == 'nginx':
            proxy_config = """
                server {
                  server_name             _;
                  listen                  8080;
                  location {{ path|d('/', true) }} {
                    proxy_pass http://localhost:{{port}};
                    proxy_set_header Upgrade $http_upgrade;
                    proxy_set_header Connection "upgrade";
                    proxy_read_timeout 86400;
                    rewrite ^{{path}}/(.*)$ /$1 break;
                    proxy_redirect http://localhost:{{port}}/ {{proto}}://{{host}}{{path}}/;
                    proxy_redirect https://localhost:{{port}}/ {{proto}}://{{host}}{{path}}/;

                    # raise size limit for uploads
                    client_max_body_size 5G;
                  }
                }
            """
        else:
            proxy_config = """
                server {
                  server_name             _;
                  listen                  8080;
                  location {{ path|d('/', true) }} {
                    proxy_pass http://localhost:{{port}};
                    proxy_set_header Upgrade $http_upgrade;
                    proxy_set_header Connection "upgrade";
                    proxy_read_timeout 86400;

                    # websocket headers
                    proxy_http_version 1.1;
                    proxy_set_header X-Scheme $scheme;

                    proxy_buffering off;
                  }
                }
            """

        proxy_config = format_with_jinja2(
            proxy_config,
            dict(
                port=int(provisioning_config['port']),
                name=application_session['name'],
                path=self.get_application_session_path(application_session),
                host=self.get_application_session_hostname(application_session),
                proto=self.endpoint_protocol
            )
        )
        configmap_dict['data']['proxy.conf'] = proxy_config
        self.logger.debug('creating configmap\n%s' % yaml.safe_dump(configmap_dict))
        api = self.dynamic_client.resources.get(api_version='v1', kind='ConfigMap')
        return api.create(body=configmap_dict, namespace=namespace)

    def delete_configmap(self, namespace, application_session):
        self.logger.debug('deleting configmap %s' % application_session.get('name'))
        api_configmap = self.dynamic_client.resources.get(api_version='v1', kind='ConfigMap')
        return api_configmap.delete(namespace=namespace, name=application_session.get('name'))

    def create_service(self, namespace, application_session):
        service_yaml = parse_template('service.yaml', dict(
            name=application_session['name'],
            target_port=8080
        ))
        self.logger.debug('creating service\n%s' % service_yaml)

        api = self.dynamic_client.resources.get(api_version='v1', kind='Service')
        return api.create(body=yaml.safe_load(service_yaml), namespace=namespace)

    def delete_service(self, namespace, application_session):
        self.logger.debug('deleting service %s' % application_session.get('name'))
        api = self.dynamic_client.resources.get(api_version='v1', kind='Service')
        api.delete(
            namespace=namespace,
            name=application_session.get('name')
        )

    def create_ingress(self, namespace, application_session):
        ingress_yaml = parse_template('ingress.yaml.j2', dict(
            name=application_session['name'],
            path=self.get_application_session_path(application_session),
            host=self.get_application_session_hostname(application_session),
            ingress_class=self.cluster_config.get('ingressClass')
        ))
        self.logger.debug('creating ingress\n%s' % ingress_yaml)

        api = self.dynamic_client.resources.get(api_version='networking.k8s.io/v1', kind='Ingress')
        return api.create(body=yaml.safe_load(ingress_yaml), namespace=namespace)

    def delete_ingress(self, namespace, application_session):
        self.logger.debug('deleting ingress %s' % application_session.get('name'))
        api = self.dynamic_client.resources.get(api_version='networking.k8s.io/v1', kind='Ingress')
        api.delete(namespace=namespace, name=application_session.get('name'))

    def ensure_volume(self, namespace, application_session, volume_name, volume_size, storage_class_name,
                      access_mode='ReadWriteOnce', annotations=None):
        api = self.dynamic_client.resources.get(api_version='v1', kind='PersistentVolumeClaim')
        try:
            api.get(namespace=namespace, name=volume_name)
            return
        except ApiException as e:
            if e.status != 404:
                raise e
        return self.create_volume(namespace, volume_name, volume_size, storage_class_name, access_mode, annotations)

    def create_volume(self, namespace, volume_name, volume_size, storage_class_name,
                      access_mode='ReadWriteOnce', annotations=None):
        pvc_yaml = parse_template('pvc.yaml', dict(
            name=volume_name,
            volume_size=volume_size,
            access_mode=access_mode,
        ))
        pvc_dict = yaml.safe_load(pvc_yaml)
        if storage_class_name is not None:
            pvc_dict['spec']['storageClassName'] = storage_class_name
        if annotations:
            pvc_dict['metadata']['annotations'] = annotations
        self.logger.debug('creating pvc\n%s' % yaml.safe_dump(pvc_dict))
        api = self.dynamic_client.resources.get(api_version='v1', kind='PersistentVolumeClaim')
        return api.create(body=pvc_dict, namespace=namespace)

    def delete_volume(self, namespace, volume_name):
        self.logger.debug('deleting volume %s' % volume_name)
        api = self.dynamic_client.resources.get(api_version='v1', kind='PersistentVolumeClaim')
        api.delete(
            namespace=namespace,
            name=volume_name
        )

    def fetch_and_populate_application_session(self, token, application_session_id):
        pbclient = self.get_pb_client()
        application_session = pbclient.get_application_session(application_session_id)
        application_session['application'] = pbclient.get_application_session_application(application_session_id)
        application_session['user'] = pbclient.get_user(application_session['user_id'])
        # get workspace memberships for the user and find the relevant one
        application_session['workspace_membership'] = next(filter(
            lambda x: x['workspace_id'] == application_session['application']['workspace_id'],
            pbclient.get_workspace_memberships(user_id=application_session['user_id'])
        ), None)

        return application_session

    def create_volume_backup_job(self, token, workspace_id, volume_name):
        ws = self.pb_client.get_workspace(workspace_id)
        namespace = self.get_namespace(workspace_id)

        # check that the volume exists
        pvc_api = self.dynamic_client.resources.get(api_version='v1', kind='PersistentVolumeClaim')
        try:
            pvc_api.get(namespace=namespace, name=volume_name)
        except ApiException as e:
            if e.status != 404:
                raise e
            raise RuntimeWarning('No volume %s/%s found for backup job' % (namespace, volume_name))

        workspace_backup_bucket_name = Path(
            '/run/secrets/pebbles/backup-secret/workspace-backup-bucket-name').read_text()
        backup_job_yaml = parse_template('pvc_backup_job.yaml.j2', dict(
            cluster_name=self.cluster_config['name'],
            workspace_pseudonym=ws['pseudonym'],
            pvc_name=volume_name,
            workspace_backup_bucket_name=workspace_backup_bucket_name,
        ))
        self.logger.debug('creating backup_job\n%s' % backup_job_yaml)

        job_api = self.dynamic_client.resources.get(api_version='batch/v1', kind='Job')
        job_api.create(namespace=namespace, body=yaml.safe_load(backup_job_yaml))

        # create a secret for encrypting and uploading to object storage
        secret_api = self.dynamic_client.resources.get(api_version='v1', kind='Secret')

        pvc_backup_secret_dict = yaml.safe_load(parse_template('pvc_backup_secret.yaml.j2', dict(pvc_name=volume_name)))
        pvc_backup_secret_dict['stringData']['s3cfg'] = Path(
            '/run/secrets/pebbles/backup-secret/s3cfg').read_text()
        pvc_backup_secret_dict['stringData']['encrypt-public-key'] = Path(
            '/run/secrets/pebbles/backup-secret/encrypt-public-key').read_text()

        secret_api.create(namespace=namespace, body=pvc_backup_secret_dict)

    def check_volume_backup_job(self, token, workspace_id, volume_name):
        namespace = self.get_namespace(workspace_id)

        # check if the namespace exists
        if not self.namespace_exists(namespace):
            raise RuntimeWarning('Backup: Namespace for workspace %s does not exist', workspace_id)

        job_api = self.dynamic_client.resources.get(api_version='batch/v1', kind='Job')
        pod_api = self.dynamic_client.resources.get(api_version='v1', kind='Pod')
        secret_api = self.dynamic_client.resources.get(api_version='v1', kind='Secret')

        job = job_api.get(namespace=namespace, name='backup-pvc-%s' % volume_name)

        if job['status'].get('active') == 1:
            return False

        # job completed, we can delete the resources in K8s
        secret_api.delete(namespace=namespace, name='pvc-backup-secret-%s' % volume_name)
        job_api.delete(namespace=namespace, name=job['metadata']['name'])
        pod_api.delete(
            namespace=namespace,
            label_selector='job-name=%s' % job['metadata']['name']
        )

        if job['status'].get('failed'):
            raise RuntimeWarning('Backup job for volume %s failed in workspace %s' % (volume_name, workspace_id))

        return True

    def create_volume_restore_job(self, token, workspace_id, volume_name, volume_size_spec, storage_class, src_cluster):
        ws = self.pb_client.get_workspace(workspace_id)
        namespace = self.get_namespace(workspace_id)
        workspace_backup_bucket_name = Path(
            '/run/secrets/pebbles/backup-secret/workspace-backup-bucket-name').read_text()

        # make sure the namespace exists
        self.ensure_namespace(namespace)

        # restore job
        self.create_volume(
            namespace,
            volume_name,
            volume_size_spec,
            storage_class,
            access_mode='ReadWriteMany',
            annotations={'pebbles.csc.fi/backup': 'yes'}
        )

        restore_job_yaml = parse_template('pvc_restore_job.yaml.j2', dict(
            src_cluster=src_cluster,
            workspace_pseudonym=ws['pseudonym'],
            pvc_name=volume_name,
            workspace_backup_bucket_name=workspace_backup_bucket_name,
        ))
        self.logger.debug('creating restore_job\n%s' % restore_job_yaml)

        job_api = self.dynamic_client.resources.get(api_version='batch/v1', kind='Job')
        job_api.create(namespace=namespace, body=yaml.safe_load(restore_job_yaml))

        # finally create a secret for downloading from object storage
        secret_api = self.dynamic_client.resources.get(api_version='v1', kind='Secret')
        pvc_restore_secret_dict = yaml.safe_load(
            parse_template('pvc_restore_secret.yaml.j2', dict(pvc_name=volume_name)))
        for name in ('s3cfg', 'encrypt-private-key', 'encrypt-private-key-password'):
            pvc_restore_secret_dict['stringData'][name] = Path(
                '/run/secrets/pebbles/backup-secret/%s' % name).read_text()

        secret_api.create(namespace=namespace, body=pvc_restore_secret_dict)

    def check_volume_restore_job(self, token, workspace_id, volume_name):
        namespace = self.get_namespace(workspace_id)

        # check if the namespace exists
        if not self.namespace_exists(namespace):
            raise RuntimeWarning('Backup: Namespace for workspace %s does not exist', workspace_id)

        job_api = self.dynamic_client.resources.get(api_version='batch/v1', kind='Job')
        pod_api = self.dynamic_client.resources.get(api_version='v1', kind='Pod')
        secret_api = self.dynamic_client.resources.get(api_version='v1', kind='Secret')

        job = job_api.get(namespace=namespace, name='restore-pvc-%s' % volume_name)

        if job['status'].get('active') == 1:
            return False

        # job completed, we can delete the resources in K8s
        secret_api.delete(namespace=namespace, name='pvc-restore-secret-%s' % volume_name)
        job_api.delete(namespace=namespace, name=job['metadata']['name'])
        pod_api.delete(
            namespace=namespace,
            label_selector='job-name=%s' % job['metadata']['name']
        )

        if job['status'].get('failed'):
            raise RuntimeWarning('Restore job for volume %s failed in workspace %s' % (volume_name, workspace_id))

        return True


class KubernetesLocalDriver(KubernetesDriverBase):
    def create_kube_client(self):
        # pick up our namespace
        with open('/var/run/secrets/kubernetes.io/serviceaccount/namespace', mode='r') as f:
            self._namespace = f.read()
        self.logger.debug('detected namespace: %s', self._namespace)

        # load service account based config
        kubernetes.config.load_incluster_config()
        return kubernetes.client.ApiClient()

    def get_namespace(self, workspace_id):
        return self._namespace

    def get_application_session_namespace(self, application_session):
        return self._namespace


class KubernetesRemoteDriver(KubernetesDriverBase):
    def create_kube_client(self):
        # load cluster config from kubeconfig
        context = self.cluster_config['name']
        config_file = self.config['CLUSTER_KUBECONFIG_FILE']
        self.logger.debug('loading context %s from %s', context, config_file)
        return kubernetes.config.new_client_from_config(
            config_file=config_file,
            context=self.cluster_config['name']
        )


class OpenShiftLocalDriver(KubernetesLocalDriver):

    def create_ingress(self, namespace, application_session):
        pod_name = application_session.get('name')
        route_yaml = parse_template('route.yaml', dict(
            name=pod_name,
            host=self.get_application_session_hostname(application_session)
        ))
        api = self.dynamic_client.resources.get(api_version='route.openshift.io/v1', kind='Route')
        api.create(body=yaml.safe_load(route_yaml), namespace=namespace)

    def delete_ingress(self, namespace, application_session):
        api = self.dynamic_client.resources.get(api_version='route.openshift.io/v1', kind='Route')
        api.delete(name=application_session.get('name'), namespace=namespace)

    def get_application_session_hostname(self, application_session):
        return '%s.%s' % (application_session.get('name'), self.ingress_app_domain)

    def get_application_session_path(self, application_session):
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

    def get_application_session_namespace(self, application_session):
        if 'session_data' in application_session and 'namespace' in application_session['session_data']:
            # application_session already has namespace assigned in session_data
            namespace = application_session['session_data']['namespace']
            self.logger.debug('found namespace %s for session %s' % (namespace, application_session.get('name')))
        elif 'namespace' in self.cluster_config.keys():
            # if we have a single namespace configured, use that
            namespace = self.cluster_config['namespace']
            self.logger.debug('using fixed namespace %s for session %s' % (namespace, application_session.get('name')))
        else:
            # generate namespace name based on prefix and workspace pseudonym
            namespace_prefix = self.cluster_config.get('namespacePrefix', 'pb-')
            namespace = '%s%s' % (namespace_prefix, application_session['application']['workspace_pseudonym'])
            self.logger.debug('assigned namespace %s to session %s' % (namespace, application_session.get('name')))
        return namespace

    def create_namespace(self, namespace):
        self.logger.info('creating namespace %s' % namespace)
        project_data = dict(kind='ProjectRequest', apiVersion='project.openshift.io/v1', metadata=dict(name=namespace))

        api = self.dynamic_client.resources.get(api_version='project.openshift.io/v1', kind='ProjectRequest')
        api.create(body=project_data)
