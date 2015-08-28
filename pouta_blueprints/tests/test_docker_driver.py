import json
import logging
import pouta_blueprints.drivers.provisioning.docker_driver as docker_driver

from pouta_blueprints.tests.base import BaseTestCase

logging.basicConfig()
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


class OpenStackServiceMock(object):
    def __init__(self, config):
        self.spawn_count = 0
        self.servers = []

    def provision_instance(self, display_name, image_name, flavor_name, key_name, extra_sec_groups,
                           master_sg_name=None):
        self.spawn_count += 1
        res = dict(
            server_id='%s' % self.spawn_count
        )
        res['ip'] = dict(
            private_ip='192.168.1.%d' % self.spawn_count,
            public_ip='172.16.0.%d' % self.spawn_count,
        )
        self.servers.append(res)

        return res

    def deprovision_instance(self, instance_id, name=None, error_if_not_exists=False):
        self.servers = [x for x in self.servers if str(x['server_id']) != str(instance_id)]

    def upload_key(self, key_name, key_file):
        pass

    def delete_key(self, key_name):
        pass


class DockerClientMock(object):
    def __init__(self):
        self._containers = []
        self.spawn_count = 0

    def pull(self, image):
        pass

    def containers(self):
        return self._containers[:]

    def create_container(self, **kwargs):
        self.spawn_count += 1
        container = dict(
            Id='%s' % self.spawn_count
        )
        self._containers.append(container)
        return container

    def start(self, container_id, **kwargs):
        pass

    def remove_container(self, container_id, **kwargs):
        pass

    def port(self, *args):
        return [{'HostPort': 32566}]


class PBClientMock(object):
    def __init__(self):
        self.instance_data = {
            '1001': dict(
                id='1001',
                name='pb-%s' % 1001,
                state='starting',
                blueprint_id='bp-01',
            )
        }

        self.blueprint_data = {
            'bp-01': dict(
                id='bp-01',
                name='test blueprint 01',
                config=dict(
                    docker_image='csc/test_image',
                    internal_port=8888,
                ),
            )
        }

    def get_instance_description(self, instance_id):
        return self.instance_data[instance_id]

    def get_blueprint_description(self, blueprint_id):
        return self.blueprint_data[blueprint_id]

    def do_instance_patch(self, instance_id, payload):
        data = self.instance_data[instance_id]
        data.update(payload)
        if 'instance_data' in data.keys() and isinstance(data['instance_data'], basestring):
            data['instance_data'] = json.loads(data['instance_data'])


class DockerDriverAccessMock(object):
    def __init__(self, config):
        self.json_data = {}
        self.oss_mock = OpenStackServiceMock(config)
        self.dc_mock = DockerClientMock()
        self.pbc_mock = PBClientMock()
        self.shutdown_mode = False

    def load_json(self, data_file, default):
        return self.json_data.get(data_file, default)

    def save_as_json(self, data_file, data):
        self.json_data[data_file] = data

    def is_shutdown_mode(self):
        return self.shutdown_mode

    def get_docker_client(self, docker_url):
        return self.dc_mock

    def get_openstack_service(self, config):
        return self.oss_mock

    def get_pb_client(self, token, base_url, ssl_verify):
        return self.pbc_mock

    @staticmethod
    def run_ansible_on_host(host, custom_logger):
        pass

    def __repr__(self):
        res = dict(
            json_data=self.json_data,
            oss_mock='%s' % self.oss_mock
        )
        return json.dumps(res)


class DockerDriverTestCase(BaseTestCase):
    def setUp(self):
        pass

    def create_docker_driver(self):
        config = dict(
            INSTANCE_DATA_DIR='/tmp',
            M2M_CREDENTIAL_STORE='',
            INTERNAL_API_BASE_URL='bogus',
        )
        dd = docker_driver.DockerDriver(logger, config)
        dd._ap = DockerDriverAccessMock(config)
        return dd

    def test_spawn_one_host(self):
        dd = self.create_docker_driver()
        ddam = dd._get_ap()

        # check that a host gets created
        cur_ts = 1000000
        dd._do_housekeep(token='foo', cur_ts=cur_ts)
        self.assertEquals(len(ddam.oss_mock.servers), 1)
        hosts_data = ddam.json_data['/tmp/docker_driver.json']
        host = hosts_data[0]
        self.assertEquals(host['state'], 'spawned')
        self.assertEquals(host['spawn_ts'], cur_ts)

        # check that the new host gets activated
        cur_ts += 60
        dd._do_housekeep(token='foo', cur_ts=cur_ts)
        self.assertEquals(len(ddam.oss_mock.servers), 1)
        hosts_data = ddam.json_data['/tmp/docker_driver.json']
        host = hosts_data[0]
        self.assertEquals(host['state'], 'active')

        # check that we don't scale up if there are no instances
        cur_ts += 60
        dd._do_housekeep(token='foo', cur_ts=cur_ts)
        self.assertEquals(len(dd._ap.oss_mock.servers), 1)

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
        self.assertSetEqual({x['state'] for x in host_file_data}, {'active'})

        # manipulate the host data a bit so that the host is marked as used
        host_file_data[0]['first_use_ts'] = cur_ts

        # fast forward time past host lifetime, should have one active and one spawned
        cur_ts += 60 + docker_driver.DD_HOST_LIFETIME
        dd._do_housekeep(token='foo', cur_ts=cur_ts)
        self.assertEquals(len(ddam.oss_mock.servers), 2)
        host_file_data = ddam.json_data['/tmp/docker_driver.json']
        self.assertSetEqual({x['state'] for x in host_file_data}, {'active', 'spawned'})

        # next tick: should have two active
        cur_ts += 60
        dd._do_housekeep(token='foo', cur_ts=cur_ts)
        self.assertEquals(len(ddam.oss_mock.servers), 2)
        host_file_data = ddam.json_data['/tmp/docker_driver.json']
        self.assertSetEqual({x['state'] for x in host_file_data}, {'active', 'active'})

        # next tick: should have one inactive, one active
        cur_ts += 60
        dd._do_housekeep(token='foo', cur_ts=cur_ts)
        self.assertEquals(len(ddam.oss_mock.servers), 2)
        host_file_data = ddam.json_data['/tmp/docker_driver.json']
        self.assertSetEqual({x['state'] for x in host_file_data}, {'inactive', 'active'})

        # last tick: should have one active
        cur_ts += 60
        dd._do_housekeep(token='foo', cur_ts=cur_ts)
        self.assertEquals(len(ddam.oss_mock.servers), 1)
        host_file_data = ddam.json_data['/tmp/docker_driver.json']
        self.assertSetEqual({x['state'] for x in host_file_data}, {'active'})

    def test_provision_deprovision(self):
        dd = self.create_docker_driver()

        # spawn a host and activate it
        cur_ts = 1000000
        dd._do_housekeep(token='foo', cur_ts=cur_ts)
        cur_ts += 60
        dd._do_housekeep(token='foo', cur_ts=cur_ts)

        # spawn an instance and destroy it
        dd._do_provision(token='foo', instance_id='1001', cur_ts=cur_ts)
        dd._do_deprovision(token='foo', instance_id='1001')

    def test_double_deprovision(self):
        dd = self.create_docker_driver()

        # spawn a host and activate it
        cur_ts = 1000000
        dd._do_housekeep(token='foo', cur_ts=cur_ts)
        cur_ts += 60
        dd._do_housekeep(token='foo', cur_ts=cur_ts)

        # spawn an instance and destroy it twice, should not blow up
        dd._do_provision(token='foo', instance_id='1001', cur_ts=cur_ts)
        dd._do_deprovision(token='foo', instance_id='1001')
        dd._do_deprovision(token='foo', instance_id='1001')
