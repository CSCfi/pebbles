import json
import time
import uuid
from docker.tls import TLSConfig
import os
from requests import ConnectionError
from pouta_blueprints.client import PBClient
from pouta_blueprints.drivers.provisioning import base_driver
import docker
from pouta_blueprints.services.openstack_service import OpenStackService
from lockfile import locked

import ansible.runner
import ansible.playbook
import ansible.inventory
from ansible import callbacks
from ansible import utils

DD_STATE_SPAWNED = 'spawned'
DD_STATE_PREPARED = 'prepared'
DD_STATE_ACTIVE = 'active'
DD_STATE_INACTIVE = 'inactive'
DD_STATE_REMOVED = 'removed'

DD_HOST_LIFETIME = 900
DD_CONTAINERS_PER_HOST = 4


class DockerDriver(base_driver.ProvisioningDriverBase):
    def get_configuration(self):
        from pouta_blueprints.drivers.provisioning.docker_driver_config import CONFIG

        config = CONFIG.copy()

        return config

    @staticmethod
    def get_docker_client(docker_url):
        # TODO: fix certificate/runtime path
        # TODO: figure out why server verification does not work (crls?)
        tls_config = TLSConfig(
            client_cert=(
                '/webapps/pouta_blueprints/run/client_cert.pem', '/webapps/pouta_blueprints/run/client_key.pem'),
            #            ca_cert='/webapps/pouta_blueprints/run/ca_cert.pem',
            verify=False,
        )
        dc = docker.Client(base_url=docker_url, tls=tls_config)

        return dc

    def do_update_connectivity(self, token, instance_id):
        self.logger.warning('do_update_connectivity not implemented')

    @locked('/webapps/pouta_blueprints/run/docker_driver_provisioning')
    def do_provision(self, token, instance_id):
        self.logger.debug("do_provision %s" % instance_id)
        pbclient = PBClient(token, self.config['INTERNAL_API_BASE_URL'], ssl_verify=False)

        instance = pbclient.get_instance_description(instance_id)

        dh = self._select_host()

        dc = self.get_docker_client(dh['docker_url'])

        container_name = instance['name']

        config = {
            'image': 'jupyter/minimal',
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

        pbclient.do_instance_patch(
            instance_id,
            {'public_ip': public_ip, 'instance_data': json.dumps(instance_data)}
        )

        self.logger.debug("do_provision done for %s" % instance_id)

    @locked('/webapps/pouta_blueprints/run/docker_driver_provisioning')
    def do_deprovision(self, token, instance_id):
        self.logger.debug("do_deprovision %s" % instance_id)

        pbclient = PBClient(token, self.config['INTERNAL_API_BASE_URL'], ssl_verify=False)
        instance = pbclient.get_instance_description(instance_id)

        if instance['state'] == 'deleted':
            self.logger.debug("do_deprovision: instance already deleted %s" % instance_id)
            return

        try:
            docker_url = instance['instance_data']['docker_url']
        except KeyError:
            self.logger.info('no docker url for instance %s, assuming provisioning has failed' % instance_id)
            return

        dc = self.get_docker_client(docker_url)

        container_name = instance['name']

        dc.remove_container(container_name, force=True)

        self.logger.debug("do_deprovision done for %s" % instance_id)

    @locked('/webapps/pouta_blueprints/run/docker_driver_housekeep')
    def do_housekeep(self, token):
        hosts = self._get_hosts()

        # find just spawned hosts
        spawned_hosts = [x for x in hosts if x['state'] == DD_STATE_SPAWNED]
        if len(spawned_hosts):
            for host in spawned_hosts:
                self.logger.info('do_housekeep() preparing host %s' % host['id'])
                self._prepare_host(host)
                host['state'] = DD_STATE_PREPARED
            self._save_hosts(hosts)
            return

        # find prepared hosts, make them active
        # TODO: do we really need this?
        prepared_hosts = [x for x in hosts if x['state'] == DD_STATE_PREPARED]
        if len(prepared_hosts):
            for host in prepared_hosts:
                self.logger.info('do_housekeep(): activating host %s' % host['id'])
                host['state'] = DD_STATE_ACTIVE
            self._save_hosts(hosts)
            return

        # find active hosts
        active_hosts = [x for x in hosts if x['state'] == DD_STATE_ACTIVE]

        # if there are no active hosts, spawn one
        if len(active_hosts) == 0:
            new_host = self._spawn_host()
            self.logger.info('do_housekeep(): no active hosts, spawned a new host %s' % new_host['id'])
            hosts.append(new_host)
            self._save_hosts(hosts)
            return

        # if there is little space, spawn a new container
        hosts_with_space = [x for x in active_hosts if x['num_instances'] < DD_CONTAINERS_PER_HOST - 1]
        if len(hosts_with_space) == 0:
            new_host = self._spawn_host()
            self.logger.info('do_housekeep(): little space, spawned a new host %s' % new_host['id'])
            hosts.append(new_host)
            self._save_hosts(hosts)
            return

        # mark old ones inactive
        for host in active_hosts:
            if host['spawn_ts'] < time.time() - DD_HOST_LIFETIME:
                self.logger.info('do_housekeep(): making host %s inactive' % host['id'])
                host['state'] = DD_STATE_INACTIVE

        # remove inactive hosts that have no instances on them
        for host in hosts:
            if host['state'] != DD_STATE_INACTIVE:
                continue
            if host['num_instances'] == 0:
                self.logger.info('do_housekeep(): removing host %s' % host['id'])
                self._remove_host(host)
                hosts.remove(host)
                self._save_hosts(hosts)
            else:
                self.logger.debug('do_housekeep(): inactive host %s still has %d instances' %
                                  (host['id'], host['num_instances']))

    def _select_host(self):
        hosts = self._get_hosts()
        active_hosts = [x for x in hosts if x['state'] == DD_STATE_ACTIVE]
        active_hosts = sorted(active_hosts, key=lambda x: -x['spawn_ts'])

        selected_host = None
        for host in active_hosts:
            if host['num_instances'] < DD_CONTAINERS_PER_HOST:
                selected_host = host
                break
        if not selected_host:
            raise RuntimeWarning('_select_host(): no space left, active hosts:%s' % active_hosts)

        self.logger.debug("_select_host(): %d total active, selected %s" % (len(active_hosts), selected_host))
        return selected_host

    def _get_hosts(self):
        self.logger.debug("_get_hosts")

        data_file = '%s/%s' % (self.config['INSTANCE_DATA_DIR'], 'docker_driver.json')

        if os.path.exists(data_file):
            with open(data_file, 'r') as df:
                hosts = json.load(df)
        else:
            hosts = []

        # populate hosts with container data
        for host in hosts:
            if host['state'] not in (DD_STATE_ACTIVE, DD_STATE_INACTIVE):
                self.logger.debug('_get_hosts(): skipping container data fetching for %s' % host['id'])
                continue
            dc = self.get_docker_client(host['docker_url'])
            try:
                containers = dc.containers()
                host['num_instances'] = len(containers)
                self.logger.debug('_get_hosts(): found %d instances on %s' % (len(containers), host['id']))
            except ConnectionError:
                self.logger.warning('_get_hosts(): updating number of instances failed for %s' % host['id'])

        return hosts

    def _save_hosts(self, hosts):
        self.logger.debug("_save_hosts")

        data_file = '%s/%s' % (self.config['INSTANCE_DATA_DIR'], 'docker_driver.json')
        if os.path.exists(data_file):
            os.rename(data_file, '%s.%s' % (data_file, int(time.time())))
        with open(data_file, 'w') as df:
            json.dump(hosts, df)

    def _spawn_host(self):
        return self._spawn_host_os_service()

    def _spawn_host_dummy(self):
        self.logger.debug("_spawn_host")
        return {
            'id': uuid.uuid4().hex,
            'provider_id': uuid.uuid4().hex,
            'docker_url': 'https://192.168.44.152:2376',
            'public_ip': '86.50.169.98',
            'spawn_ts': int(time.time()),
            'state': DD_STATE_SPAWNED,
            'num_instances': 0,
        }

    def _spawn_host_os_service(self):
        self.logger.debug("_spawn_host_os_service")

        config = {
            'image': 'CentOS-7.0',
            'flavor': 'mini',
            'key': 'pb_dockerdriver',
            '': '',
        }
        instance_name = 'pb_dd_%s' % uuid.uuid4().hex
        image_name = config['image']
        flavor_name = config['flavor']
        key_name = config['key']

        oss = OpenStackService({'M2M_CREDENTIAL_STORE': self.config['M2M_CREDENTIAL_STORE']})

        # make sure the our key is in openstack
        oss.upload_key(key_name, '/home/pouta_blueprints/.ssh/id_rsa.pub')

        # run actual provisioning
        res = oss.provision_instance(
            display_name=instance_name,
            image_name=image_name,
            flavor_name=flavor_name,
            key_name=key_name,
            master_sg_name='pb_server'
        )

        self.logger.debug("_spawn_host_os_service: spawned %s" % res)

        return {
            'id': instance_name,
            'provider_id': res['server_id'],
            'docker_url': 'https://%s:2376' % res['ip']['private_ip'],
            'public_ip': res['ip']['public_ip'],
            'private_ip': res['ip']['private_ip'],
            'spawn_ts': int(time.time()),
            'state': DD_STATE_SPAWNED,
            'num_instances': 0,
        }

    def _prepare_host(self, host):
        self.logger.debug("_prepare_host")

        # global verbosity for debugging e.g. ssh problems with ansible. ugly.
        utils.VERBOSITY = 4

        # set up ansible inventory for the host
        a_host = ansible.inventory.host.Host(name=host['id'])
        a_host.set_variable('ansible_ssh_host', host['private_ip'])

        a_group = ansible.inventory.group.Group(name='notebook_host')
        a_group.add_host(a_host)

        a_inventory = ansible.inventory.Inventory(host_list=[host['private_ip']])
        a_inventory.add_group(a_group)

        stats = callbacks.AggregateStats()
        playbook_cb = callbacks.PlaybookCallbacks(verbose=utils.VERBOSITY)
        runner_cb = callbacks.PlaybookRunnerCallbacks(stats, verbose=utils.VERBOSITY)

        self.logger.debug("_prepare_host(): running ansible")
        pb = ansible.playbook.PlayBook(
            playbook="/webapps/pouta_blueprints/source/ansible/notebook_playbook.yml",
            stats=stats,
            callbacks=playbook_cb,
            runner_callbacks=runner_cb,
            inventory=a_inventory,
            remote_user='cloud-user',
        )

        pb_res = pb.run()

        self.logger.debug(json.dumps(pb_res, sort_keys=True, indent=4, separators=(',', ': ')))

        for host_name in pb_res.keys():
            host_data = pb_res[host_name]
            if host_data.get('unreachable', 0) + host_data.get('failures', 0) > 0:
                raise RuntimeError('_prepare_host failed')

        self.logger.debug("_prepare_host(): pulling docker image")
        dc = self.get_docker_client(host['docker_url'])
        dc.pull('jupyter/minimal')

    def _remove_host(self, host):
        self.logger.debug("_remove_host")
        self._remove_host_os_service(host)

    def _remove_host_os_service(self, host):
        self.logger.debug("_remove_host_os_service")
        oss = OpenStackService({'M2M_CREDENTIAL_STORE': self.config['M2M_CREDENTIAL_STORE']})
        oss.deprovision_instance(host['provider_id'], host['id'])

    def _check_host(self, host):
        self.logger.debug("_check_host %s" % host)
        self.logger.warning("_check_host not implemented")
