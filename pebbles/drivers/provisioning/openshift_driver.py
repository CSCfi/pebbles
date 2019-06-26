"""
To set up the OpenShift driver you need

* a workin OpenShift instance
* a user in the OpenShift instance (a separate machine to machine account is
  recommended)

1. Start by adding the url, username, password and subdomain in the creds
file. names are "OSO_XXX_URL", where XXX is the name of your installation
(there can be multiple installations)
2. Restart Pebbles
3. Check out https://github.com/cscfi/notebook-images/
4. Log in as the M2M user using the *oc* command line utility
5. run build_openshift.sh to build and publish images to the OpenShift Docker registry
6. Enable OpenShiftDriver in the Admin UI



"""

import json
import time
import uuid
from pprint import pprint
import requests
# noinspection PyUnresolvedReferences
from six.moves.urllib.parse import urlparse, parse_qs

import pebbles.utils
from pebbles.client import PBClient
from pebbles.drivers.provisioning import base_driver

# maximum time to wait for pod creation before failing
MAX_POD_SPAWN_WAIT_TIME_SEC = 900
# maximum time to wait for pod (down) scaling
MAX_POD_SCALE_WAIT_TIME_SEC = 120
# refresh the token if it is this close to expiration
TOKEN_REFRESH_DELTA = 600


class OpenShiftClient(object):
    """
    An abstraction of accessing an OpenShift cluster
    """

    def __init__(self, base_url, subdomain, user, password):
        """
        Constructor

        :param base_url: url to access the api, like https://oso.example.org:8443/
        :param subdomain: the subdomain for creating the routes, like osoapps.example.org
        :param user:
        :param password:
        """
        if base_url[-1] == '/':
            base_url = base_url[:-1]
        self.base_url = base_url
        self.subdomain = subdomain
        self.oapi_base_url = base_url + '/oapi/v1'
        self.kube_base_url = base_url + '/api/v1'
        self.template_base_url = base_url + '/apis/template.openshift.io/v1'
        self.user = user
        self.password = password

        # token_data caches the token to access the API. See _request_token() for details.
        self.token_data = None
        self._session = requests.session()

    @staticmethod
    def make_base_kube_object(kind, name=None):
        return dict(
            kind=kind,
            apiVersion="v1",
            metadata=dict(
                name=name
            )
        )

    @staticmethod
    def print_response(resp):
        if resp.ok:
            print('success: %s' % resp.status_code)
            pprint(resp.json())
        else:
            print('error in response: %s %s %s' % (resp.status_code, resp.reason, resp.text))

    def _request_token(self, current_ts=None):
        """
        Requests an access token for the cluster

        :param current_ts: current timestamp
        :return: dict containing access_token, lifetime and expiry time
        """
        url = self.base_url + '/oauth/authorize'
        auth_encoded = pebbles.utils.b64encode_string(bytes('%s:%s' % (self.user, self.password)))

        headers = {
            'Authorization': 'Basic %s' % str(auth_encoded),
            'X-Csrf-Token': '1'
        }
        params = {
            'response_type': 'token',
            'client_id': 'openshift-challenging-client'
        }

        resp = requests.get(url, headers=headers, verify=False, params=params, allow_redirects=False)

        location = resp.headers.get('location')

        if not current_ts:
            current_ts = int(time.time())

        parsed_data = urlparse(location)
        parsed_query = parse_qs(parsed_data.fragment)

        return {
            'access_token': parsed_query['access_token'][0],
            'lifetime': int(parsed_query['expires_in'][0]),
            'expires_at': int(parsed_query['expires_in'][0]) + current_ts,
        }

    def _get_token(self, current_ts=None):
        """
        Caching version of _request_token
        """
        if not self.token_data:
            self.token_data = self._request_token(current_ts)
        else:
            if not current_ts:
                current_ts = int(time.time())
            if self.token_data['expires_at'] - TOKEN_REFRESH_DELTA < current_ts:
                self.token_data = self._request_token(current_ts)

        return self.token_data['access_token']

    def _construct_object_url(self, api_type, namespace=None, object_kind=None, object_id=None, subop=None):
        """
        Create a url string for given object
        :param kubeapi: whether plain k8s or oso api is used
        :param namespace: namespace for the object
        :param object_kind: type of the object
        :param object_id: id of the object
        :return: url string, like 'https://oso.example.org:8443/api/v1/my-project/pods/18hfgy1'
        """
        if api_type == 'kubeapi':
            url_components = [self.kube_base_url]
        elif api_type == 'template_oapi':
            url_components = [self.template_base_url]
        else:
            url_components = [self.oapi_base_url]

        if namespace:
            url_components.append('namespaces')
            url_components.append(namespace)
        if object_kind:
            url_components.append(object_kind)
        if object_id:
            url_components.append(object_id)
        if subop:
            url_components.append(subop)
        url = '/'.join(url_components)

        return url

    def make_request(self, method=None, api_type='oapi', verbose=False, namespace=None, object_kind=None, object_id=None,
                     subop=None, params=None, data=None, raise_on_failure=True):
        """
        Makes a request to OpenShift API

        :param method: GET, PUT, POST
        :param kubeapi: whether plain k8s or oso api is used
        :param verbose: debugging on
        :param namespace: namespace for the object
        :param object_kind: type of the object
        :param object_id: id of the object
        :param subop: if it's a suboperation eg. getting logs of an object
        :param params: request parameters
        :param data: request data
        :param raise_on_failure: should we raise a RuntimeError on failure
        :return: response object from requests session
        """
        url = self._construct_object_url(api_type, namespace, object_kind, object_id, subop)
        headers = {'Authorization': 'Bearer %s' % self._get_token()}
        if isinstance(data, dict):
            data = json.dumps(data)

        if data:
            if not method or method == 'POST':
                resp = self._session.post(url, headers=headers, verify=False, params=params, data=data)
            elif method == 'PUT':
                resp = self._session.put(url, headers=headers, verify=False, params=params, data=data)
            else:
                raise RuntimeError('Do not know what to do with data and method %s' % method)
        else:
            if method and method != 'GET':
                raise RuntimeError('Do not know what to do with no data and method %s' % method)
            resp = self._session.get(url, headers=headers, verify=False, params=params)
        if verbose:
            self.print_response(resp)

        if raise_on_failure and not resp.ok:
            raise RuntimeError(resp.text)

        return resp

    def make_delete_request(self, api_type='oapi', verbose=False, namespace=None, object_kind=None, object_id=None,
                            params=None, raise_on_failure=True):
        """
        Makes a delete request to OpenShift API

        :param kubeapi: whether plain k8s or oso api is used
        :param verbose: debugging on
        :param namespace: namespace for the object
        :param object_kind: type of the object
        :param object_id: id of the object
        :param raise_on_failure: should we raise a RuntimeError on failure
        :return: response object from requests session
        """
        url = self._construct_object_url(api_type, namespace, object_kind, object_id)
        headers = {'Authorization': 'Bearer %s' % self._get_token()}

        resp = self._session.delete(url, headers=headers, verify=False, params=params)
        if verbose:
            self.print_response(resp)

        if raise_on_failure and not resp.ok:
            raise RuntimeError(resp.text)

        return resp

    def search_by_label(self, api_type, namespace=None, object_kind=None, params=None):
        """
        Performs a search by label(s)

        :param kubeapi: k8s api instead of openshift
        :param namespace:
        :param object_kind:
        :param params: a dict containing search criteria, like {'labelSelector': 'app=my-app'}
        :return: search results as json
        """
        res = self.make_request(
            api_type=api_type,
            namespace=namespace,
            object_kind=object_kind,
            params=params
        )
        res_json = res.json()
        return res_json.get('items', [])


class OpenShiftDriverAccessProxy(object):
    """
    Abstraction layer for isolating driver from real world to enable mocking in unit tests
    """

    def __init__(self, m2m_creds):
        self._m2m_creds = m2m_creds

    def get_openshift_client(self, cluster_id):
        key_base = 'OSD_%s_' % cluster_id
        return OpenShiftClient(
            base_url=self._m2m_creds.get(key_base + 'BASE_URL'),
            subdomain=self._m2m_creds.get(key_base + 'SUBDOMAIN'),
            user=self._m2m_creds.get(key_base + 'USER'),
            password=self._m2m_creds.get(key_base + 'PASSWORD'),
        )

    @staticmethod
    def get_pb_client(token, api_base_url, ssl_verify):
        return PBClient(token, api_base_url, ssl_verify)


class OpenShiftDriver(base_driver.ProvisioningDriverBase):
    """ OpenShift Driver allows provisioning instances in an existing OpenShift cluster.
    It creates a project per user, identified by user eppn, and optionally a persistent
    volume claim (PVC) for user data.

    The driver needs credentials for the cluster. The credentials are placed in the same
    m2m creds file that OpenStack and Docker driver use. The keys are as follows:

    "OSD_[cluster_id]_BASE_URL": "https://oso-cluster-api.example.org:8443",
    "OSD_[cluster_id]_SUBDOMAIN": "oso-cluster.example.org",
    "OSD_[cluster_id]_USER": "pebbles-m2m-user",
    "OSD_[cluster_id]_PASSWORD": "sickritt"

    Replace [cluster_id] with a unique string to a cluster. When creating a blueprint template,
    refer to the cluster id in the configuration, key 'openshift_cluster_id' .You can have multiple
    credentials configured in the creds file.

    """

    def get_configuration(self):
        from pebbles.drivers.provisioning.openshift_driver_config import CONFIG

        config = CONFIG.copy()

        return config

    def get_running_instance_logs(self, token, instance_id):
        """ Get the logs of the openshift based instance which is in running state """
        self.logger.debug("getting container logs for instance id %s" % instance_id)

        ap = self._get_access_proxy()
        pbclient = ap.get_pb_client(token, self.config['INTERNAL_API_BASE_URL'], ssl_verify=False)
        running_log_uploader = self.create_prov_log_uploader(token, instance_id, log_type='running')

        instance = pbclient.get_instance_description(instance_id)

        # create openshift client by getting the cluster id from the blueprint config
        blueprint = pbclient.get_blueprint_description(instance['blueprint_id'])
        blueprint_config = blueprint['full_config']
        oc = ap.get_openshift_client(
            cluster_id=blueprint_config['openshift_cluster_id'],
        )

        instance_name = instance['name']
        project = self._get_project_name(instance)

        log_res = oc.make_request(
            method='GET',
            namespace=project,
            object_kind='deploymentconfigs',
            object_id=instance_name,
            subop='log',
        )

        running_log_uploader.info(log_res.text)

    def _get_access_proxy(self):
        if not getattr(self, '_ap', None):
            m2m_creds = self.get_m2m_credentials()
            self._ap = OpenShiftDriverAccessProxy(m2m_creds)
        return self._ap

    def do_update_connectivity(self, token, instance_id):
        self.logger.warning('do_update_connectivity not implemented')

    def do_provision(self, token, instance_id):
        self.logger.debug('do_provision %s' % instance_id)
        log_uploader = self.create_prov_log_uploader(token, instance_id, log_type='provisioning')

        log_uploader.info('Provisioning OpenShift based instance (%s)\n' % instance_id)

        return self._do_provision(token, instance_id, int(time.time()))

    def _do_provision(self, token, instance_id, cur_ts):
        """
        Provisions a new instance on OpenShift.

        :param token: token to access the API with
        :param instance_id: instance that should be provisioned
        :param cur_ts: current time
        """
        ap = self._get_access_proxy()

        pbclient = ap.get_pb_client(token, self.config['INTERNAL_API_BASE_URL'], ssl_verify=False)

        log_uploader = self.create_prov_log_uploader(token, instance_id, log_type='provisioning')

        instance = pbclient.get_instance_description(instance_id)

        # fetch config
        blueprint = pbclient.get_blueprint_description(instance['blueprint_id'])
        blueprint_config = blueprint['full_config']

        # get/generate a project name
        project_name = self._get_project_name(instance)

        # create an openshift client based for selected cluster
        oc = ap.get_openshift_client(
            cluster_id=blueprint_config['openshift_cluster_id'],
        )
        # create a dict out of space separated list of VAR=VAL entries
        env_var_array = blueprint_config.get('environment_vars', '').split()
        env_vars = {k: v for k, v in [x.split('=') for x in env_var_array]}
        env_vars['INSTANCE_ID'] = instance_id

        # merge the autodownload vars into environment
        for var_suffix in ('url', 'filename'):
            var = 'autodownload_{}'.format(var_suffix)
            if blueprint_config.get(var, None):
                env_vars[var.upper()] = blueprint_config[var]

        # create a project and PVC if necessary and spawn a pod (through DC/RC), service and route

        res = self._spawn_project_and_objects(
            oc=oc,
            project_name=project_name,
            blueprint_config=blueprint_config,
            instance=instance,
            environment_vars=env_vars
        )

        instance_data = {
            'endpoints': [
                {
                    'name': 'https',
                    'access': res['route']
                },
            ],
            'project_name': project_name,
            'spawn_ts': cur_ts
        }

        if 'show_password' in blueprint_config and blueprint_config['show_password']:
            instance_data['password'] = instance_id

        pbclient.do_instance_patch(
            instance_id,
            {
                'instance_data': json.dumps(instance_data),
            }
        )

        log_uploader.info("provisioning done for %s\n" % instance_id)

    def _create_project(self, oc, project_name):

        # https://server:8443/oapi/v1/projectrequests
        project_data = oc.make_base_kube_object('ProjectRequest', project_name)

        # create the project if it does not exist yet
        from time import sleep
        for delay_count in range(0, 30):  # sometimes the project isn't created and the code starts to create pvc
            res = oc.make_request(object_kind='projects', object_id=project_name, raise_on_failure=False)
            if not res.ok and res.status_code == 403:
                oc.make_request(object_kind='projectrequests', data=project_data)
            else:
                break  # project has been created, exit the loop
            sleep(2)  # sleep for 2 seconds, the loop goes on for 1 minute

    # noinspection PyTypeChecker
    def _spawn_project_and_objects(self, oc, project_name, blueprint_config, instance, environment_vars=None):
        """
        Creates an OpenShift project (if needed) and launches a pod in it. If a volume mount point is requested,
        a volume is allocated (if needed) and mounted to the pod. A secure route is also created.

        :param oc: openshift client to use
        :param project_name: namespace/project name
        :param pod_name: pod name
        :param pod_image: image to use for pod
        :param port: the port to expose
        :param pod_memory: amount of memory to reserve
        :param volume_mount_point: where the persistent data should be mounted in the pod
        :param environment_vars: environment vars to set in the pod
        :return: dict with key 'route' set to the provisioned route to the instance
        """

        self._create_project(oc, project_name)

        pod_name = instance['name']
        pod_image = blueprint_config['image']
        port = int(blueprint_config['port'])
        pod_memory = blueprint_config['memory_limit']
        volume_mount_point = blueprint_config.get('volume_mount_point', None)

        # create PVC if it does not exist yet
        if volume_mount_point:
            pvc_data = {
                'apiVersion': 'v1',
                'kind': 'PersistentVolumeClaim',
                'metadata': {
                    'name': 'pvc001'
                },
                'spec': {
                    'accessModes': ['ReadWriteMany'],
                    'resources': {
                        'requests': {
                            'storage': '1Gi'
                        }
                    },
                },
            }
            # calling kubernetes API here
            # https://server:8443/api/v1/namespaces/project/persistentvolumeclaims

            # first check if we already have a PVC
            res = oc.make_request(
                namespace=project_name,
                object_kind='persistentvolumeclaims',
                object_id=pvc_data['metadata']['name'],
                api_type='kubeapi',
                raise_on_failure=False,
            )
            # nope, let's create it
            if not res.ok and res.status_code == 404:
                oc.make_request(
                    namespace=project_name,
                    object_kind='persistentvolumeclaims',
                    data=pvc_data,
                    api_type='kubeapi'
                )

        # https://server:8443/oapi/v1/namespaces/project/deploymentconfigs
        dc_data = {
            'kind': 'DeploymentConfig',
            'apiVersion': 'v1',
            'metadata': {
                'name': pod_name,
                'creationTimestamp': None,
                'labels': {
                    'run': pod_name
                }
            },
            'spec': {
                'strategy': {
                    'resources': {}
                },
                'triggers': None,
                'replicas': 1,
                'test': False,
                'selector': {
                    'run': pod_name
                },
                'template': {
                    'metadata': {
                        'creationTimestamp': None,
                        'labels': {
                            'run': pod_name
                        }
                    },
                    'spec': {
                        'containers': [
                            {
                                'name': pod_name,
                                'image': pod_image,
                                'resources': {
                                    'requests': {
                                        'memory': pod_memory
                                    },
                                    'limits': {
                                        'memory': pod_memory
                                    },
                                },
                                'ports': [
                                    {
                                        'protocol': 'TCP',
                                        'containerPort': port,
                                    }
                                ],
                                'readinessProbe': {
                                    'httpGet': {
                                        'path': '/',
                                        'port': port,
                                        'scheme': 'HTTP',

                                    }
                                }
                            }
                        ],
                    }
                }
            }
        }

        dc_volume_mounts = []
        dc_volumes = []

        # workaround for service account secret automount.
        # see https://github.com/kubernetes/kubernetes/issues/16779
        # TODO revise this workaround
        dc_volume_mounts.append(
            {
                'mountPath': '/var/run/secrets/kubernetes.io/serviceaccount',
                'name': 'nosecret',
            }
        )
        dc_volumes.append(
            {
                'name': 'nosecret',
                'emptyDir': {}
            }
        )

        # add a mount point to persistent storage, if configured
        if volume_mount_point:
            dc_volume_mounts.append(
                {
                    'mountPath': volume_mount_point,
                    'name': 'work',
                }
            )
            dc_volumes.append(
                {
                    'name': 'work',
                    'persistentVolumeClaim': {
                        'claimName': 'pvc001'
                    }
                }
            )

        dc_data['spec']['template']['spec']['containers'][0]['volumeMounts'] = dc_volume_mounts
        dc_data['spec']['template']['spec']['volumes'] = dc_volumes

        # create environment variables for the blueprint
        env_data = []
        if environment_vars:
            for key, value in environment_vars.items():
                env_data.append({'name': key, 'value': value})

        dc_data['spec']['template']['spec']['containers'][0]['env'] = env_data

        oc.make_request(namespace=project_name, object_kind='deploymentconfigs', data=dc_data)

        pod_selector_params = dict(labelSelector='run=%s' % pod_name)

        self._wait_for_pod_creation(oc, project_name, pod_selector_params, pod_name)

        # calling kubernetes API here
        # https://server:8443/api/v1/namespaces/project/services
        svc_data = {
            'kind': 'Service',
            'apiVersion': 'v1',
            'metadata': {
                'name': pod_name,
                'labels': {
                    'run': pod_name
                }
            },
            'spec': {
                'ports': [
                    {
                        'protocol': 'TCP',
                        'port': port,
                        'targetPort': port,
                    }
                ],
                'selector': {
                    'run': pod_name
                }
            }, 'status': {'loadBalancer': {}}
        }

        oc.make_request(api_type='kubeapi', namespace=project_name, object_kind='services', data=svc_data)

        route_host = '%s-%s.%s' % (pod_name, uuid.uuid4().hex[:10], oc.subdomain)

        # https://server:8443/oapi/v1/namespaces/project/routes
        route_data = {
            'kind': 'Route',
            'apiVersion': 'v1',
            'metadata': {
                'name': pod_name,
                'labels': {
                    'run': pod_name
                }
            },
            'spec': {
                'host': route_host,
                'to': {
                    'name': pod_name,
                },
                'port': {
                    'targetPort': port,
                },
                'tls': {
                    'termination': 'edge'
                }
            }
        }

        route_data = oc.make_request(namespace=project_name, object_kind='routes', data=route_data)
        route_json = route_data.json()

        return dict(route='https://%s/' % route_json['spec']['host'])

    def _wait_for_pod_creation(self, oc, project_name, params, pod_name):
        # wait for pod to become ready
        end_ts = time.time() + MAX_POD_SPAWN_WAIT_TIME_SEC
        while time.time() < end_ts:
            # pods live in kubernetes API
            res = oc.make_request(
                api_type='kubeapi',
                namespace=project_name,
                object_kind='pods',
                params=params,
            )
            if res.ok:
                pod_ready = None
                for pod in res.json()['items']:
                    try:
                        pod_status = pod['status']['phase']
                        if pod_status != 'Running':
                            break
                        pod_ready = True
                    except:
                        pass

                if pod_ready:
                    break

            self.logger.debug('waiting for pod to be ready %s' % pod_name)
            time.sleep(5)
        else:
            raise RuntimeError('Timeout waiting for pod readiness for %s' % params['labelSelector'])

    def do_deprovision(self, token, instance_id):
        return self._do_deprovision(token, instance_id)

    def _do_deprovision(self, token, instance_id):
        """
        Deprovisions an instance. It removes
        - DeploymentConfig (DC)
        - ReplicationController (RC)
        - Service
        - Route

        DC is removed first, then RC is scaled down to get rid of Pods. When the Pods are gone, RC is removed.
        Then Service and Route are removed.

        Any volumes attached to the instance are left intact, as well as the project the instance is running in.

        :param token: token to access API
        :param instance_id: the instance to delete
        """
        self.logger.debug('do_deprovision %s' % instance_id)

        ap = self._get_access_proxy()

        pbclient = ap.get_pb_client(token, self.config['INTERNAL_API_BASE_URL'], ssl_verify=False)
        instance = pbclient.get_instance_description(instance_id)
        log_uploader = self.create_prov_log_uploader(token, instance_id, log_type='deprovisioning')

        log_uploader.info('Deprovisioning OpenShift based instance (%s)\n' % instance_id)

        # fetch config
        blueprint = pbclient.get_blueprint_description(instance['blueprint_id'])
        blueprint_config = blueprint['full_config']

        oc = ap.get_openshift_client(
            cluster_id=blueprint_config['openshift_cluster_id'],
        )

        project = self._get_project_name(instance)

        self._delete_objects(oc=oc, project=project, blueprint_config=blueprint_config, instance=instance)

    def _delete_objects(self, oc, project, instance, blueprint_config=None):
        """ Delete openshift objects
        """
        name = instance['name']
        instance_id = instance['id']

        # remove dc
        res = oc.make_delete_request(
            namespace=project,
            object_kind='deploymentconfigs',
            object_id=name,
            raise_on_failure=False,
        )
        if not res.ok:
            if res.status_code == 404:
                self.logger.warning('do_deprovision: DC not found, assuming deleted: %s' % name)
            else:
                raise RuntimeError(res.reason)

        # find rc
        params = dict(labelSelector='run=%s' % name)
        rc_list = oc.search_by_label(
            api_type='kubeapi',
            namespace=project,
            object_kind='replicationcontrollers',
            params=params
        )
        # then set replicas to 0 and let pods die
        for rc in rc_list:
            self._scale_rc(oc, project, rc, 0)

        # remove rc
        for rc in rc_list:
            res = oc.make_delete_request(
                api_type='kubeapi',
                namespace=project,
                object_kind='replicationcontrollers',
                object_id=rc['metadata']['name'],
                raise_on_failure=False,
            )
            if not res.ok:
                if res.status_code == 404:
                    self.logger.warning('do_deprovision: RC not found, assuming deleted: %s' % name)
                else:
                    raise RuntimeError(res.reason)

        # remove route
        res = oc.make_delete_request(
            namespace=project,
            object_kind='routes',
            object_id=name,
            raise_on_failure=False,
        )
        if not res.ok:
            if res.status_code == 404:
                self.logger.warning('do_deprovision: route not found, assuming deleted: %s' % name)
            else:
                raise RuntimeError(res.reason)

        # remove service
        res = oc.make_delete_request(
            api_type='kubeapi',
            namespace=project,
            object_kind='services',
            object_id=name,
            raise_on_failure=False,
        )
        if not res.ok:
            if res.status_code == 404:
                self.logger.warning('do_deprovision: service not found, assuming deleted: %s' % name)
            else:
                raise RuntimeError(res.reason)

        self.logger.debug('do_deprovision done for %s' % instance_id)

    @staticmethod
    def _scale_rc(oc, project, rc, num_replicas):
        """
        Scale a ReplicationController and wait for the amount of replicas to catch up. The maximum waiting time
        is taken from MAX_POD_SCALE_WAIT_TIME_SEC

        :param oc: the openshift client to use
        :param project: project name
        :param rc: ReplicationController name
        :param num_replicas: new number of replicas
        """
        # scale the pods down
        rc['spec']['replicas'] = num_replicas
        res = oc.make_request(
            api_type='kubeapi',
            method='PUT',
            namespace=project,
            object_kind='replicationcontrollers',
            object_id=rc['metadata']['name'],
            data=rc,
        )
        if not res.ok:
            raise RuntimeError(res.reason)

        # wait for scaling to be complete
        end_ts = time.time() + MAX_POD_SCALE_WAIT_TIME_SEC
        while time.time() < end_ts:
            res = oc.make_request(
                api_type='kubeapi',
                namespace=project,
                object_kind='replicationcontrollers',
                object_id=rc['metadata']['name'],
            )
            rc = res.json()
            if int(rc['status']['replicas']) == num_replicas:
                break
            time.sleep(2)
        else:
            raise RuntimeError('Could not scale pods to %d for %s' % (num_replicas, rc['metadata']['name']))

    @staticmethod
    def _get_project_name(instance):
        """
        Generate a project name from instance data. If the instance data already has 'project_name' attribute,
        use that.

        :param instance: dict containing instance data
        :return: project name based on username and first 4 characters of user id
        """
        if 'instance_data' in instance and 'project_name' in instance['instance_data']:
            return instance['instance_data']['project_name']
        else:
            # create a project name based on username and userid
            name = ('%s-%s' % (instance['username'], instance['user_id'][:4]))
            name = name.replace('@', '-at-').replace('.', '-').lower()
            return name

    def do_housekeep(self, token):
        # TODO: Implement optional cleaning of the old projects.
        self.logger.info('do_housekeep not implemented')
