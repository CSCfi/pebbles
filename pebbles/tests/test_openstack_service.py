import mock
from mock import create_autospec
from pebbles.tests.base import BaseTestCase
from pebbles.services import openstack_service
from pebbles.tests.test_mocks import NovaClientMock
from sys import version_info

mock_nc_config = (
    '{"OS_PASSWORD": "password", "OS_AUTH_URL": "https://example.org",'
    '"OS_USERNAME": "username", "OS_TENANT_NAME": "tenant"}')

if version_info.major == 2:
    import __builtin__ as builtins
else:
    import builtins


def mock_open_context(func):
    def inner(*args, **kwargs):
        with mock.patch.object(builtins, 'open', mock.mock_open(read_data=mock_nc_config)):
            return func(*args, **kwargs)
    return inner


class OpenStackClientTest(BaseTestCase):
    @mock_open_context
    def test_nova_client_instantiation(self):
        import novaclient.v2.client
        nc = openstack_service.get_openstack_nova_client({'M2M_CREDENTIAL_STORE': '/tmp/config.json'})
        self.assertEqual(type(nc), novaclient.v2.client.Client)

    @mock_open_context
    def test_cinder_client_instantiation(self):
        import cinderclient.v2.client
        nc = openstack_service.get_openstack_cinder_client({
            'M2M_CREDENTIAL_STORE': '/tmp/config.json'})
        self.assertEqual(type(nc), cinderclient.v2.client.Client)

    @mock_open_context
    def test_neutron_client_instantiation(self):
        import neutronclient.v2_0.client
        nc = openstack_service.get_openstack_neutron_client({
            'M2M_CREDENTIAL_STORE': '/tmp/config.json'})
        self.assertEquals(type(nc), neutronclient.v2_0.client.Client)


class OpenStackServiceTestCase(BaseTestCase):
    def setUp(self):
        openstack_service.get_openstack_nova_client = create_autospec(
            openstack_service.get_openstack_nova_client, return_value=NovaClientMock())
        openstack_service.get_openstack_cinder_client = create_autospec(
            openstack_service.get_openstack_cinder_client,
            return_value=NovaClientMock())
        openstack_service.get_openstack_neutron_client = create_autospec(
            openstack_service.get_openstack_neutron_client,
            return_value=NovaClientMock())
        self.config = {"OS_PASSWORD": "password",
                       "OS_AUTH_URL": "https://example.org/v2.0",
                       "OS_USERNAME": "username",
                       "OS_TENANT_NAME": "tenant"}

    def test_provision(self):
        oss = openstack_service.OpenStackService(self.config)
        resp = oss.provision_instance(
            'display_name', 'image_name', 'flavor_name', '', [],
            master_sg_name='master_sg_name', nics=None, data_volume_size=10)
        self.assertEquals(resp.get('server_id'), 'instance_1')
