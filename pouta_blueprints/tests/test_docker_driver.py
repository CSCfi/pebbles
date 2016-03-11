import json
import logging
import docker.errors
import pouta_blueprints.drivers.provisioning.docker_driver as docker_driver
from pouta_blueprints.tests.base import BaseTestCase
from pouta_blueprints.drivers.provisioning.docker_driver import DD_STATE_ACTIVE, DD_STATE_INACTIVE, DD_STATE_SPAWNED
import mock
from sys import version_info
import docker.utils

if version_info.major == 2:
    import __builtin__ as builtins
else:
    import builtins

logging.basicConfig()
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


# decorator for overriding open
def mock_open_context(func):
    def inner(*args, **kwargs):
        with mock.patch.object(builtins, 'open', mock.mock_open(read_data='1234123412341234')):
            return func(*args, **kwargs)

    return inner


# decorator for raising RuntimeError if in failure mode
def raise_on_failure_mode(func):
    def inner(*args, **kwargs):
        if args[0].failure_mode:
            raise RuntimeError('In failure mode')
        return func(*args, **kwargs)

    return inner


class MockResponse(object):
    def __init__(self, status_code):
        self.status_code = status_code


class OpenStackServiceMock(object):
    def __init__(self, config):
        self.spawn_count = 0
        self.servers = []
        self.failure_mode = False

    @raise_on_failure_mode
    def provision_instance(self, display_name, image_name, flavor_name,
                           public_key, extra_sec_groups=None,
                           master_sg_name=None, allocate_public_ip=True,
                           root_volume_size=0, data_volume_size=0, data_volume_type=None,
                           userdata=None
                           ):
        self.spawn_count += 1
        res = dict(
            server_id='%s' % self.spawn_count
        )
        res['address_data'] = dict(
            private_ip='192.168.1.%d' % self.spawn_count,
            public_ip=None,
        )
        if allocate_public_ip:
            res['address_data']['public_ip'] = '172.16.0.%d' % self.spawn_count

        self.servers.append(res)

        return res

    @raise_on_failure_mode
    def deprovision_instance(self, instance_id, name=None, delete_attached_volumes=False):
        self.servers = [x for x in self.servers if str(x['server_id']) != str(instance_id)]
        return {}

    @raise_on_failure_mode
    def upload_key(self, key_name, public_key):
        pass

    @raise_on_failure_mode
    def delete_key(self, key_name):
        pass


# noinspection PyUnusedLocal
class DockerClientMock(object):
    def __init__(self):
        self._containers = []
        self.spawn_count = 0
        self.failure_mode = False

    @raise_on_failure_mode
    def pull(self, image):
        pass

    @raise_on_failure_mode
    def containers(self):
        return self._containers[:]

    def create_host_config(self, *args, **kwargs):
        return {}

    @raise_on_failure_mode
    def create_container(self, name, **kwargs):
        self.spawn_count += 1
        container = dict(
            Id='%s' % self.spawn_count,
            Name=name,
            Labels=dict(slots='1')
        )
        self._containers.append(container)
        return container

    @raise_on_failure_mode
    def start(self, container_id, **kwargs):
        pass

    @raise_on_failure_mode
    def remove_container(self, name, **kwargs):
        matches = [x for x in self._containers if x['Name'] == name]
        if len(matches) == 1:
            container = matches[0]
            self._containers.remove(container)
        elif len(matches) == 0:
            response = MockResponse(status_code=404)
            raise docker.errors.APIError("foo", response=response, explanation='')
        else:
            raise RuntimeError('More than one container with same name detected')

    @raise_on_failure_mode
    def port(self, *args):
        return [{'HostPort': 32768 + self.spawn_count % 32768}]

    def load_image(self, *args):
        pass


class PBClientMock(object):
    def __init__(self):
        self.instance_data = {}
        self.blueprint_data = {
            'bp-01': dict(
                id='bp-01',
                name='test blueprint 01',
                config=dict(
                    docker_image='csc/test_image',
                    internal_port=8888,
                    consumed_slots=1,
                    memory_limit='512m',
                    environment_vars=''
                ),
            )
        }

    def add_instance_data(self, instance_id):
        self.instance_data[instance_id] = dict(
            id='%s' % instance_id,
            name='pb-%s' % instance_id,
            state='starting',
            blueprint_id='bp-01',
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


# noinspection PyUnusedLocal
class DockerDriverAccessMock(object):
    def __init__(self, config):
        self.json_data = {}
        self.oss_mock = OpenStackServiceMock(config)
        self.dc_mocks = {}
        self.pbc_mock = PBClientMock()
        self.shutdown_mode = False
        self.failure_mode = False

    def load_json(self, data_file, default):
        return self.json_data.get(data_file, default)

    def save_as_json(self, data_file, data):
        self.json_data[data_file] = data

    def get_docker_client(self, docker_url):
        if docker_url not in self.dc_mocks.keys():
            self.dc_mocks[docker_url] = DockerClientMock()

        self.dc_mocks[docker_url].failure_mode = self.failure_mode
        return self.dc_mocks[docker_url]

    def get_openstack_service(self, config):
        return self.oss_mock

    def get_pb_client(self, token, base_url, ssl_verify):
        return self.pbc_mock

    def run_ansible_on_host(self, host, custom_logger, config):
        if self.failure_mode:
            raise RuntimeError

    @staticmethod
    def proxy_add_route(route_id, target_url, options):
        pass

    @staticmethod
    def proxy_remove_route(route_id):
        pass

    def __repr__(self):
        res = dict(
            json_data=self.json_data,
            oss_mock='%s' % self.oss_mock
        )
        return json.dumps(res)

    @staticmethod
    def get_image_names():
        return ['test/test1']

    @staticmethod
    def wait_for_port(ip_address, port, max_wait_secs=60):
        pass


# noinspection PyProtectedMember
class DockerDriverTestCase(BaseTestCase):
    def setUp(self):
        # set up a constants to known values for tests
        docker_driver.DD_HOST_LIFETIME = 900

    @staticmethod
    def create_docker_driver():
        config = dict(
            INSTANCE_DATA_DIR='/tmp',
            M2M_CREDENTIAL_STORE='',
            INTERNAL_API_BASE_URL='http://bogus/api/v1',
            TEST_MODE=True,
            PUBLIC_IPV4='10.0.0.1',
            EXTERNAL_HTTPS_PORT=443,
            DD_HOST_IMAGE='CentOS-7.0',
            DD_MAX_HOSTS=4,
            DD_SHUTDOWN_MODE=False,
            DD_FREE_SLOT_TARGET=4,
            DD_HOST_FLAVOR_NAME_SMALL='mini',
            DD_HOST_FLAVOR_SLOTS_SMALL=4,
            DD_HOST_FLAVOR_NAME_LARGE='small',
            DD_HOST_FLAVOR_SLOTS_LARGE=16,
            DD_HOST_MASTER_SG='pb_server',
            DD_HOST_EXTRA_SGS='',
            DD_HOST_ROOT_VOLUME_SIZE=0,
            DD_HOST_DATA_VOLUME_FACTOR=4,
            DD_HOST_DATA_VOLUME_DEVICE='/dev/vdc',
            DD_HOST_DATA_VOLUME_TYPE='',
        )
        dd = docker_driver.DockerDriver(logger, config)
        dd._ap = DockerDriverAccessMock(config)

        return dd

    @mock_open_context
    def test_spawn_one_host(self):
        dd = self.create_docker_driver()
        ddam = dd._get_ap()

        # check that a host gets created
        cur_ts = 1000000
        dd._do_housekeep(token='foo', cur_ts=cur_ts)
        self.assertEquals(len(ddam.oss_mock.servers), 1)
        hosts_data = ddam.json_data['/tmp/docker_driver.json']
        host = hosts_data[0]
        self.assertEquals(host['state'], DD_STATE_SPAWNED)
        self.assertEquals(host['spawn_ts'], cur_ts)

        # check that the new host gets activated
        cur_ts += 60
        dd._do_housekeep(token='foo', cur_ts=cur_ts)
        self.assertEquals(len(ddam.oss_mock.servers), 1)
        hosts_data = ddam.json_data['/tmp/docker_driver.json']
        host = hosts_data[0]
        self.assertEquals(host['state'], DD_STATE_ACTIVE)

        # check that we don't scale up if there are no instances
        cur_ts += 60
        dd._do_housekeep(token='foo', cur_ts=cur_ts)
        self.assertEquals(len(dd._ap.oss_mock.servers), 1)

    @mock_open_context
    def test_do_not_spawn_if_not_used(self):
        dd = self.create_docker_driver()
        ddam = dd._get_ap()

        # spawn a host
        cur_ts = 1000000
        dd._do_housekeep(token='foo', cur_ts=cur_ts)

        # fast forward time past lifetime, but when the host is not used the lifetime should not tick
        cur_ts += 60 + docker_driver.DD_HOST_LIFETIME
        dd._do_housekeep(token='foo', cur_ts=cur_ts)
        self.assertEquals(len(ddam.oss_mock.servers), 1)

    @mock_open_context
    def test_spawn_activate_remove(self):
        dd = self.create_docker_driver()
        ddam = dd._get_ap()

        # spawn a host and activate it
        cur_ts = 1000000
        dd._do_housekeep(token='foo', cur_ts=cur_ts)
        cur_ts += 60
        dd._do_housekeep(token='foo', cur_ts=cur_ts)
        self.assertEquals(len(ddam.oss_mock.servers), 1)
        host_file_data = ddam.json_data['/tmp/docker_driver.json']
        self.assertSetEqual({x['state'] for x in host_file_data}, {DD_STATE_ACTIVE})

        # manipulate the host data a bit so that the host is marked as used
        host_file_data[0]['lifetime_tick_ts'] = cur_ts

        # fast forward time past host lifetime, should have one active and one spawned
        cur_ts += 60 + docker_driver.DD_HOST_LIFETIME
        dd._do_housekeep(token='foo', cur_ts=cur_ts)
        self.assertEquals(len(ddam.oss_mock.servers), 2)
        host_file_data = ddam.json_data['/tmp/docker_driver.json']
        self.assertSetEqual({x['state'] for x in host_file_data}, {DD_STATE_ACTIVE, DD_STATE_SPAWNED})

        # next tick: should have two active
        cur_ts += 60
        dd._do_housekeep(token='foo', cur_ts=cur_ts)
        self.assertEquals(len(ddam.oss_mock.servers), 2)
        host_file_data = ddam.json_data['/tmp/docker_driver.json']
        self.assertSetEqual({x['state'] for x in host_file_data}, {DD_STATE_ACTIVE, DD_STATE_ACTIVE})

        # next tick: should have one inactive, one active
        cur_ts += 60
        dd._do_housekeep(token='foo', cur_ts=cur_ts)
        self.assertEquals(len(ddam.oss_mock.servers), 2)
        host_file_data = ddam.json_data['/tmp/docker_driver.json']
        self.assertSetEqual({x['state'] for x in host_file_data}, {DD_STATE_INACTIVE, DD_STATE_ACTIVE})

        # last tick: should have one active
        cur_ts += 60
        dd._do_housekeep(token='foo', cur_ts=cur_ts)
        self.assertEquals(len(ddam.oss_mock.servers), 1)
        host_file_data = ddam.json_data['/tmp/docker_driver.json']
        self.assertSetEqual({x['state'] for x in host_file_data}, {DD_STATE_ACTIVE})

    @mock_open_context
    def test_provision_deprovision(self):
        dd = self.create_docker_driver()
        ddam = dd._get_ap()

        # spawn a host and activate it
        cur_ts = 1000000
        dd._do_housekeep(token='foo', cur_ts=cur_ts)
        cur_ts += 60
        dd._do_housekeep(token='foo', cur_ts=cur_ts)

        # spawn an instance and destroy it
        ddam.pbc_mock.add_instance_data('1001')
        dd._do_provision(token='foo', instance_id='1001', cur_ts=cur_ts)
        dd._do_deprovision(token='foo', instance_id='1001')

    @mock_open_context
    def test_double_deprovision(self):
        dd = self.create_docker_driver()
        ddam = dd._get_ap()

        # spawn a host and activate it
        cur_ts = 1000000
        dd._do_housekeep(token='foo', cur_ts=cur_ts)
        cur_ts += 60
        dd._do_housekeep(token='foo', cur_ts=cur_ts)

        # spawn an instance and destroy it twice, should not blow up
        ddam.pbc_mock.add_instance_data('1001')
        dd._do_provision(token='foo', instance_id='1001', cur_ts=cur_ts)
        dd._do_deprovision(token='foo', instance_id='1001')
        # because base driver is bypassed in tests, instance state has to be set manually
        ddam.pbc_mock.do_instance_patch('1001', dict(state='deleted'))
        dd._do_deprovision(token='foo', instance_id='1001')

    @mock_open_context
    def test_double_deprovision_404(self):
        dd = self.create_docker_driver()
        ddam = dd._get_ap()

        # spawn a host and activate it
        cur_ts = 1000000
        dd._do_housekeep(token='foo', cur_ts=cur_ts)
        cur_ts += 60
        dd._do_housekeep(token='foo', cur_ts=cur_ts)

        # spawn an instance and destroy it twice, should not blow up
        ddam.pbc_mock.add_instance_data('1001')
        dd._do_provision(token='foo', instance_id='1001', cur_ts=cur_ts)
        dd._do_deprovision(token='foo', instance_id='1001')
        dd._do_deprovision(token='foo', instance_id='1001')

    @mock_open_context
    def test_scale_up_to_the_limit(self):
        dd = self.create_docker_driver()
        ddam = dd._get_ap()

        # spawn a host and activate it
        cur_ts = 1000000
        dd._do_housekeep(token='foo', cur_ts=cur_ts)
        cur_ts += 60
        dd._do_housekeep(token='foo', cur_ts=cur_ts)

        num_slots = (
            dd.config['DD_HOST_FLAVOR_SLOTS_SMALL'] +
            dd.config['DD_HOST_FLAVOR_SLOTS_LARGE'] * (dd.config['DD_MAX_HOSTS'] - 1)
        )

        # spawn instances up to the limit
        for i in range(0, num_slots):
            ddam.pbc_mock.add_instance_data('%d' % (1000 + i))
            dd._do_provision(token='foo', instance_id='%d' % (1000 + i), cur_ts=cur_ts)
            cur_ts += 60
            dd._do_housekeep(token='foo', cur_ts=cur_ts)

        self.assertEquals(len(ddam.oss_mock.servers), dd.config['DD_MAX_HOSTS'])

        try:
            ddam.pbc_mock.add_instance_data('999')
            dd._do_provision(token='foo', instance_id='999', cur_ts=cur_ts)
            self.fail('pool should have been full')
        except RuntimeWarning:
            pass

    @mock_open_context
    def test_scale_down(self):
        dd = self.create_docker_driver()
        ddam = dd._get_ap()

        # spawn a host and activate it
        cur_ts = 1000000
        dd._do_housekeep(token='foo', cur_ts=cur_ts)
        cur_ts += 60
        dd._do_housekeep(token='foo', cur_ts=cur_ts)

        num_slots = (
            dd.config['DD_HOST_FLAVOR_SLOTS_SMALL'] +
            dd.config['DD_HOST_FLAVOR_SLOTS_LARGE'] * (dd.config['DD_MAX_HOSTS'] - 1)
        )

        # spawn instances up to the limit
        for i in range(0, num_slots):
            ddam.pbc_mock.add_instance_data('%d' % (1000 + i))
            dd._do_provision(token='foo', instance_id='%d' % (1000 + i), cur_ts=cur_ts)
            cur_ts += 60
            dd._do_housekeep(token='foo', cur_ts=cur_ts)

        self.assertEquals(len(ddam.oss_mock.servers), dd.config['DD_MAX_HOSTS'])

        # remove instances
        for i in range(0, num_slots):
            dd._do_deprovision(token='foo', instance_id='%d' % (1000 + i))

        # let logic scale down (3 ticks per host should be enough)
        cur_ts += docker_driver.DD_HOST_LIFETIME
        for i in range(0, dd.config['DD_MAX_HOSTS'] * 3):
            dd._do_housekeep(token='foo', cur_ts=cur_ts)

        self.assertEquals(len(ddam.oss_mock.servers), 1)

    @mock_open_context
    def test_shutdown_mode(self):
        dd = self.create_docker_driver()
        ddam = dd._get_ap()

        # spawn a host and activate it
        cur_ts = 1000000
        dd._do_housekeep(token='foo', cur_ts=cur_ts)
        cur_ts += 60
        dd._do_housekeep(token='foo', cur_ts=cur_ts)

        # set shutdown mode and see that we have scaled down
        dd.config['DD_SHUTDOWN_MODE'] = True
        cur_ts += 60
        dd._do_housekeep(token='foo', cur_ts=cur_ts)
        cur_ts += 60
        dd._do_housekeep(token='foo', cur_ts=cur_ts)

        self.assertEquals(len(ddam.oss_mock.servers), 0)

    @mock_open_context
    def test_inactive_host_with_instances(self):
        dd = self.create_docker_driver()
        ddam = dd._get_ap()

        # spawn a host and activate it
        cur_ts = 1000000
        dd._do_housekeep(token='foo', cur_ts=cur_ts)
        cur_ts += 60
        dd._do_housekeep(token='foo', cur_ts=cur_ts)

        # add an instance
        ddam.pbc_mock.add_instance_data('1000')
        dd._do_provision(token='foo', instance_id='1000', cur_ts=cur_ts)

        # change the state to inactive under the hood (this is possible due to a race
        # between housekeep() and provision())
        host_file_data = ddam.json_data['/tmp/docker_driver.json']
        host_file_data[0]['state'] = DD_STATE_INACTIVE

        for i in range(5):
            cur_ts += 60
            dd._do_housekeep(token='foo', cur_ts=cur_ts)

        self.assertEquals(len(ddam.oss_mock.servers), 2)
        self.assertSetEqual({x['state'] for x in host_file_data}, {DD_STATE_INACTIVE, DD_STATE_ACTIVE})

        # remove the instance and check that the host is removed also
        dd._do_deprovision(token='foo', instance_id='1000')
        for i in range(5):
            cur_ts += 60
            dd._do_housekeep(token='foo', cur_ts=cur_ts)

        self.assertEquals(len(ddam.oss_mock.servers), 1)
        self.assertSetEqual({x['state'] for x in host_file_data}, {DD_STATE_ACTIVE})

    @mock_open_context
    def test_prepare_failing(self):
        dd = self.create_docker_driver()
        ddam = dd._get_ap()

        # spawn a host
        cur_ts = 1000000
        dd._do_housekeep(token='foo', cur_ts=cur_ts)

        # mimic a failure to prepare it
        ddam.failure_mode = True
        cur_ts += 60
        dd._do_housekeep(token='foo', cur_ts=cur_ts)
        host_file_data = ddam.json_data['/tmp/docker_driver.json']
        self.assertSetEqual({x['state'] for x in host_file_data}, {DD_STATE_SPAWNED})

        # recover
        ddam.failure_mode = False
        cur_ts += 60
        dd._do_housekeep(token='foo', cur_ts=cur_ts)
        self.assertSetEqual({x['state'] for x in host_file_data}, {DD_STATE_ACTIVE})

    @mock_open_context
    def test_prepare_failing_max_retries(self):
        dd = self.create_docker_driver()
        ddam = dd._get_ap()

        # spawn a host
        cur_ts = 1000000
        dd._do_housekeep(token='foo', cur_ts=cur_ts)

        # mimic a failure to prepare it
        ddam.failure_mode = True
        for i in range(docker_driver.DD_MAX_HOST_ERRORS + 1):
            cur_ts += 60
            dd._do_housekeep(token='foo', cur_ts=cur_ts)

        host_file_data = ddam.json_data['/tmp/docker_driver.json']
        self.assertSetEqual({x['state'] for x in host_file_data}, {DD_STATE_INACTIVE})

        ddam.failure_mode = False
        cur_ts += 60
        dd._do_housekeep(token='foo', cur_ts=cur_ts)
        self.assertEqual(len(host_file_data), 0)

        for i in range(2):
            cur_ts += 60
            dd._do_housekeep(token='foo', cur_ts=cur_ts)

        self.assertSetEqual({x['state'] for x in host_file_data}, {DD_STATE_ACTIVE})

    @mock_open_context
    def test_docker_comm_probs(self):
        dd = self.create_docker_driver()
        ddam = dd._get_ap()

        # spawn a host and activate it
        cur_ts = 1000000
        dd._do_housekeep(token='foo', cur_ts=cur_ts)
        cur_ts += 60
        dd._do_housekeep(token='foo', cur_ts=cur_ts)

        ddam.pbc_mock.add_instance_data('1000')

        # mimic a docker comm failure
        ddam.failure_mode = True
        try:
            dd._do_provision(token='foo', instance_id='1000', cur_ts=cur_ts)
            self.fail('should have raised an error')
        except:
            pass

        ddam.failure_mode = False
        dd._do_provision(token='foo', instance_id='1000', cur_ts=cur_ts)
        ddam.failure_mode = True

        ddam.failure_mode = True
        try:
            dd._do_deprovision(token='foo', instance_id='1000')
            self.fail('should have raised an error')
        except:
            pass

        ddam.failure_mode = False
        dd._do_deprovision(token='foo', instance_id='1000')
