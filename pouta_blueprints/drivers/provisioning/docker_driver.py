import json
from novaclient.v2 import client
from pouta_blueprints.drivers.provisioning import base_driver
import docker

SLEEP_BETWEEN_POLLS = 3
POLL_MAX_WAIT = 180


class DockerDriver(base_driver.ProvisioningDriverBase):
    def get_openstack_nova_client(self):
        openstack_env = self.create_openstack_env()
        if not openstack_env:
            return None

        os_username = openstack_env['OS_USERNAME']
        os_password = openstack_env['OS_PASSWORD']
        os_tenant_name = openstack_env['OS_TENANT_NAME']
        os_auth_url = openstack_env['OS_AUTH_URL']

        return client.Client(os_username, os_password, os_tenant_name, os_auth_url, service_type="compute")

    def get_configuration(self):
        from pouta_blueprints.drivers.provisioning.docker_driver_config import CONFIG

        config = CONFIG.copy()

        return config

    def do_update_connectivity(self, token, instance_id):
        self.logger.warning('do_update_connectivity not implemented')

    def do_provision(self, token, instance_id):
        self.logger.debug("do_provision %s" % instance_id)

        instance = self.get_instance_description(token, instance_id)

        dh = self._select_host()
        self.logger.debug('selected host %s' % dh)

        dc = docker.Client(dh['docker_url'])

        container_name = instance['name']

        config = {
            'image': 'jupyter/demo',
            'name': container_name
        }
        dc.pull(config['image'])

        res = dc.create_container(**config)
        container_id = res['Id']
        self.logger.info("created container '%s' (id: %s)", container_name, container_id)

        dc.start(container_id, publish_all_ports=True)
        self.logger.info("started container '%s'", container_name)

        public_ip = dh['public_ip']
        # get the public port
        res = dc.port(container_id, 8888)
        public_port = res[0]['HostPort']

        instance_data = {
            'endpoints': [
                {'name': 'http', 'access': 'http://%s:%s' % (public_ip, public_port)},
            ],
            'docker_url': dh['docker_url']
        }

        self.do_instance_patch(
            token,
            instance_id,
            {'public_ip': public_ip, 'instance_data': json.dumps(instance_data)}
        )

        self.logger.debug("do_provision done for %s" % instance_id)

    def do_deprovision(self, token, instance_id):
        self.logger.debug("do_deprovision %s" % instance_id)

        instance = self.get_instance_description(token, instance_id)
        docker_url = instance['instance_data']['docker_url']

        dc = docker.Client(docker_url)

        container_name = instance['name']

        dc.remove_container(container_name, force=True)

        self._check_hosts()

        self.logger.debug("do_deprovision done for %s" % instance_id)

    def _select_host(self):
        # TODO: implement a dynamic pool of hosts
        hosts = self._get_hosts()
        return hosts[0]

    def _get_hosts(self):
        self.logger.debug("_get_hosts")
        return [
            {
                'docker_url': 'tcp://localhost:12375',
                'public_ip': '86.50.169.98',
            }
        ]

    def _spawn_host(self):
        self.logger.debug("_spawn_host")
        self.logger.warning("_spawn_host not implemented")

    def _remove_host(self):
        self.logger.debug("_remove_host")
        self.logger.warning("_remove_host not implemented")

    def _check_host(self, host):
        self.logger.debug("_check_host %s" % host)
        self.logger.warning("_check_host not implemented")
