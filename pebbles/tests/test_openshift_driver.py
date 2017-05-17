import json
import logging

import requests
import responses

import pebbles.drivers.provisioning.openshift_driver as openshift_driver
from pebbles.tests.base import BaseTestCase

logging.basicConfig()
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


class PBClientMock(object):
    def __init__(self):
        self.instance_data = {}
        config = dict(
            memory_limit='512m',
            environment_vars=''
        )
        self.blueprint_data = {
            'bp-01': dict(
                id='bp-01',
                name='test blueprint 01',
                config=config,
                full_config=dict(
                    image='csc/test_image',
                    port=8888,
                    memory_limit='512M',
                    environment_vars='VAR=value ANOTHER_VAR=value2',
                    autodownload_url='http://example.org/materials.md',
                    autodownload_file='example_materials.md',
                    openshift_cluster_id='TEST',
                )
            ),
            'bp-02': dict(
                id='bp-02',
                name='test blueprint 02',
                config=config,
                full_config=dict(
                    image='csc/test_image',
                    port=8888,
                    memory_limit='512M',
                    openshift_cluster_id='TEST',
                    volume_mount_dir='/scratch',
                )
            )

        }

    def add_instance_data(self, instance_id, blueprint_id='bp-01'):
        self.instance_data[instance_id] = dict(
            id='%s' % instance_id,
            name='pb-%s' % instance_id,
            username='user1@example.com',
            user_id='1111-1111-1111-1111',
            state='starting',
            blueprint_id=blueprint_id
        )

    def get_instance_description(self, instance_id):
        return self.instance_data[instance_id]

    def get_blueprint_description(self, blueprint_id):
        return self.blueprint_data[blueprint_id]

    def do_instance_patch(self, instance_id, payload):
        data = self.instance_data[instance_id]
        data.update(payload)
        if 'instance_data' in data.keys() and isinstance(data['instance_data'], str):
            data['instance_data'] = json.loads(data['instance_data'])


class OpenShiftClientMock(openshift_driver.OpenShiftClient):
    def _request_token(self, current_ts=None):
        return {
            'access_token': 'asdfasdfasdfasdf',
            'lifetime': 86400,
            'expires_at': 186400,
        }


# noinspection PyUnusedLocal
class OpenShiftDriverAccessMock(object):
    def __init__(self, m2m_creds):
        self._m2m_creds = m2m_creds
        self.pbc_mock = PBClientMock()

    def get_pb_client(self, token, base_url, ssl_verify):
        return self.pbc_mock

    def get_openshift_client(self, cluster_id):
        key_base = 'OSD_%s_' % cluster_id
        return OpenShiftClientMock(
            base_url=self._m2m_creds.get(key_base + 'BASE_URL'),
            subdomain=self._m2m_creds.get(key_base + 'SUBDOMAIN'),
            user=self._m2m_creds.get(key_base + 'USER'),
            password=self._m2m_creds.get(key_base + 'PASSWORD'),
        )


# noinspection PyProtectedMember
class OpenShiftDriverTestCase(BaseTestCase):
    def setUp(self):
        pass

    @staticmethod
    def create_openshift_driver():
        config = dict(
            INSTANCE_DATA_DIR='/tmp',
            M2M_CREDENTIAL_STORE='',
            INTERNAL_API_BASE_URL='http://bogus/api/v1',
            TEST_MODE=True,
            PUBLIC_IPV4='10.0.0.1',
            EXTERNAL_HTTPS_PORT=443,
        )
        osd = openshift_driver.OpenShiftDriver(logger, config)
        osd._ap = OpenShiftDriverAccessMock(
            m2m_creds={
                'OSD_TEST_BASE_URL': 'https://localhost:8443/',
                'OSD_TEST_SUBDOMAIN': 'oso.example.com',
                'OSD_TEST_USER': 'm2m',
                'OSD_TEST_PASSWORD': 'machinehead',
            }
        )
        return osd

    @responses.activate
    def test_provision_deprovision(self):
        osd = self.create_openshift_driver()
        osdam = osd._get_access_proxy()
        osc = osdam.get_openshift_client('TEST')

        user1_ns = 'user1-at-example-com-1111'

        # spawn a simple instance and destroy it
        osdam.pbc_mock.add_instance_data('1001')
        self.populate_responses(osc, user1_ns, 'pb-1001')
        osd.do_provision(token='foo', instance_id='1001')
        osd.do_deprovision(token='foo', instance_id='1001')

    @responses.activate
    def test_provision_deprovision_volume(self):
        osd = self.create_openshift_driver()
        osdam = osd._get_access_proxy()
        osc = osdam.get_openshift_client('TEST')

        user1_ns = 'user1-at-example-com-1111'

        # spawn an instance with a volume
        osdam.pbc_mock.add_instance_data('1002', blueprint_id='bp-02')
        self.populate_responses(osc, user1_ns, 'pb-1002')
        osd.do_provision(token='foo', instance_id='1002')
        osd.do_deprovision(token='foo', instance_id='1002')

    @responses.activate
    def test_print_response(self):
        url = 'http://example.org/test'
        # first add provisioning responses
        responses.add(
            responses.GET,
            url,
            json=dict(items=[dict(foo='bar', foo2='bar2')])
        )
        resp = requests.get(url, verify=False)
        openshift_driver.OpenShiftClient.print_response(resp)

    @staticmethod
    def populate_responses(osc, user1_ns, instance_name):
        oapi_ns = osc.oapi_base_url + '/namespaces/' + user1_ns
        kubeapi_ns = osc.kube_base_url + '/namespaces/' + user1_ns

        # first add provisioning responses
        responses.add(
            responses.GET,
            osc.oapi_base_url + '/projects/' + user1_ns,
        )

        responses.add(
            responses.POST,
            oapi_ns + '/deploymentconfigs',
        )

        responses.add(
            responses.GET,
            kubeapi_ns + '/pods',
            json=dict(items=[dict(status=dict(containerStatuses=[dict(name=instance_name, ready=True)]))])
        )
        responses.add(
            responses.POST,
            kubeapi_ns + '/services',
        )
        responses.add(
            responses.POST,
            oapi_ns + '/routes',
            json={'spec': {'host': '%s.%s' % (instance_name, osc.subdomain)}}
        )

        # then add deprovisioning responses
        responses.add(
            responses.GET,
            kubeapi_ns + '/replicationcontrollers',
            json={'items': [{'spec': {'replicas': 1}, 'metadata': {'name': '%s-1' % instance_name}}]}
        )
        responses.add(
            responses.PUT,
            kubeapi_ns + '/replicationcontrollers/%s-1' % instance_name,
        )
        responses.add(
            responses.GET,
            kubeapi_ns + '/replicationcontrollers/%s-1' % instance_name,
            json={'status': {'replicas': 0}, 'metadata': {'name': '%s-1' % instance_name}}
        )
        responses.add(
            responses.DELETE,
            oapi_ns + '/deploymentconfigs/%s' % instance_name,
        )
        responses.add(
            responses.DELETE,
            kubeapi_ns + '/replicationcontrollers/%s-1' % instance_name,
        )
        responses.add(
            responses.DELETE,
            oapi_ns + '/routes/%s' % instance_name,
        )
        responses.add(
            responses.DELETE,
            kubeapi_ns + '/services/%s' % instance_name,
        )
