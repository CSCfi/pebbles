import json
import time
import uuid
import novaclient
import os
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

    def do_housekeep(self, token):
        hosts = self._get_hosts()

        # find active hosts
        active_hosts = [x for x in hosts if x['is_active']]

        # if there are no active hosts, spawn one
        if len(active_hosts) == 0:
            new_host = self._spawn_host(token)
            self.logger.info('do_housekeep() spawned a new host %s' % new_host['id'])
            hosts.append(new_host)
            self._save_hosts(hosts)
            return

        # mark old ones inactive
        for host in active_hosts:
            if host['spawn_ts'] < time.time() - 300:
                self.logger.info('do_housekeep() making host %s inactive' % host['id'])
                host['is_active'] = False

        # remove inactive hosts that have no instances on them
        for host in hosts:
            if host['is_active']:
                continue
            if host['num_instances'] == 0:
                self.logger.info('do_housekeep() removing host %s' % host['id'])
                self._remove_host(host)
                hosts.remove(host)
                self._save_hosts(hosts)
            else:
                self.logger.debug('do_housekeep() inactive host %s still has %d instances' %
                                  (host['id'], host['num_instances']))

    def _select_host(self):
        hosts = self._get_hosts()
        return hosts[0]

    def _get_hosts(self):
        self.logger.debug("_get_hosts")

        data_file = '%s/%s' % (self.config['INSTANCE_DATA_DIR'], 'docker_driver.json')

        if os.path.exists(data_file):
            with open(data_file, 'r') as df:
                hosts = json.load(df)
        else:
            hosts = []

        return hosts

    def _save_hosts(self, hosts):
        self.logger.debug("_save_hosts")

        data_file = '%s/%s' % (self.config['INSTANCE_DATA_DIR'], 'docker_driver.json')
        if os.path.exists(data_file):
            os.rename(data_file, '%s.%s' % (data_file, int(time.time())))
        with open(data_file, 'w') as df:
            json.dump(hosts, df)

    def _spawn_host(self, token):
        self.logger.debug("_spawn_host")
        return {
            'id': uuid.uuid4().hex,
            'provider_id': uuid.uuid4().hex,
            'docker_url': 'tcp://localhost:12375',
            'public_ip': '86.50.169.98',
            'spawn_ts': int(time.time()),
            'is_active': True,
            'num_instances': 0,
        }

    def _spawn_host_os(self, token):
        self.logger.debug("_spawn_host_os")

        instance_name = uuid.uuid4().hex

        nc = self.get_openstack_nova_client()
        config = {
            'image': 'Ubuntu-14.04',
            'flavor': 'small',
            '': '',
        }
        image_name = config['image']

        try:
            image = nc.images.find(name=image_name)
        except novaclient.exceptions.NotFound:
            error = 'requested image %s not found' % image_name
            self.logger.warning(error)
            raise RuntimeError(error)

        flavor_name = config['flavor']
        try:
            flavor = nc.flavors.find(name=flavor_name)
        except novaclient.exceptions.NotFound:
            error = 'requested flavor %s not found' % flavor_name
            self.logger.warning(error)
            raise RuntimeError(error)

        prefix = self.config['INSTANCE_NAME_PREFIX']
        key_name = '%s%s' % (prefix, 'docker_driver')
        try:
            private_key = nc.keypairs.create(key_name)
            with open('%s/%s' % (self.config['INSTANCE_DATA_DIR'], key_name)) as pk_file:
                pk_file.write(private_key)
        except:
            self.logger.debug('conflict: public key already exists')
            self.logger.debug('conflict: using existing key (%s)' % key_name)

        security_group_name = 'default'

        server = nc.servers.create(
            instance_name,
            image,
            flavor,
            key_name=key_name,
            security_groups=[security_group_name],
            userdata=config.get('userdata'))

        while nc.servers.get(server.id).status is "BUILDING" or not nc.servers.get(server.id).networks:
            self.logger.debug("waiting for server to come up")
            time.sleep(SLEEP_BETWEEN_POLLS)

        ips = nc.floating_ips.findall(instance_id=None)
        allocated_from_pool = False
        if not ips:
            self.logger.info("No allocated free IPs left, trying to allocate one\n")
            try:
                ip = nc.floating_ips.create(pool="public")
                allocated_from_pool = True
            except novaclient.exceptions.ClientException as e:
                self.logger.info("Cannot allocate IP, quota exceeded?\n")
                raise e
        else:
            ip = ips[0]

        self.logger.info("Got IP %s\n" % ip.ip)

        server.add_floating_ip(ip)

        return {
            'id': instance_name,
            'provider_id': server.id,
            'docker_url': 'tcp://localhost:12375',
            'public_ip': ip.ip,
            'public_ip_allocated_from_pool': allocated_from_pool,
            'spawn_ts': int(time.time()),
            'is_active': True,
            'num_instances': 0,
        }

    def _remove_host(self, host):
        self.logger.debug("_remove_host")
        self.logger.warning("_remove_host not implemented")

    def _check_host(self, host):
        self.logger.debug("_check_host %s" % host)
        self.logger.warning("_check_host not implemented")
