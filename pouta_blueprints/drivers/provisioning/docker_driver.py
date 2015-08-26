import json
import time
import uuid
from docker.errors import APIError
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
DD_STATE_ACTIVE = 'active'
DD_STATE_INACTIVE = 'inactive'
DD_STATE_REMOVED = 'removed'

DD_HOST_LIFETIME = 900
DD_MAX_HOSTS = 4
DD_CONTAINERS_PER_HOST = 4
DD_FREE_SLOT_TARGET = 4
DD_PROVISION_RETRIES = 10
DD_PROVISION_RETRY_SLEEP = 30


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

    def do_provision(self, token, instance_id):
        self.logger.debug("do_provision %s" % instance_id)
        retries = 0
        while True:
            try:
                self._do_provision(token, instance_id)
                break
            except RuntimeWarning as e:
                retries += 1
                if retries > DD_PROVISION_RETRIES:
                    raise e
                self.logger.warning(
                    "do_provision failed for %s, sleeping and retrying (%d/%d)" % (
                        instance_id, retries, DD_PROVISION_RETRIES
                    )
                )
                time.sleep(DD_PROVISION_RETRY_SLEEP)

    @locked('/webapps/pouta_blueprints/run/docker_driver_provisioning')
    def _do_provision(self, token, instance_id):
        pbclient = PBClient(token, self.config['INTERNAL_API_BASE_URL'], ssl_verify=False)

        instance = pbclient.get_instance_description(instance_id)

        # fetch config
        blueprint = pbclient.get_blueprint_description(instance['blueprint_id'])
        blueprint_config = blueprint['config']

        dh = self._select_host()

        dc = self.get_docker_client(dh['docker_url'])

        container_name = instance['name']
        password = uuid.uuid4().hex[:16]

        config = {
            'image': blueprint_config['docker_image'],
            'ports': [blueprint_config['internal_port']],
            'name': container_name,
            'mem_limit': blueprint_config['memory_limit'],
            'cpu_shares': 5,
            'environment': {'PASSWORD': password},
        }

        res = dc.create_container(**config)
        container_id = res['Id']
        self.logger.info("created container '%s' (id: %s)", container_name, container_id)

        dc.start(container_id, publish_all_ports=True)
        self.logger.info("started container '%s'", container_name)

        public_ip = dh['public_ip']
        # get the public port
        res = dc.port(container_id, blueprint_config['internal_port'])
        public_port = res[0]['HostPort']

        instance_data = {
            'endpoints': [
                {'name': 'http', 'access': 'http://%s:%s' % (public_ip, public_port)},
                {'name': 'password', 'access': password},
            ],
            'docker_url': dh['docker_url'],
        }

        pbclient.do_instance_patch(
            instance_id,
            {
                'public_ip': public_ip,
                'instance_data': json.dumps(instance_data),
            }
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

        try:
            dc.remove_container(container_name, force=True)
        except APIError as e:
            if e.response.status_code == 404:
                self.logger.info('no container found instance %s, assuming already deleted' % instance_id)
            else:
                raise e

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
                host['state'] = DD_STATE_ACTIVE
            self._save_host_state(hosts)
            return

        # remove inactive hosts that have no instances on them
        inactive_hosts = [x for x in hosts if x['state'] == DD_STATE_INACTIVE]
        for host in inactive_hosts:
            if host['num_instances'] == 0:
                self.logger.info('do_housekeep(): removing host %s' % host['id'])
                self._remove_host(host)
                hosts.remove(host)
                self._save_host_state(hosts)
                return
            else:
                self.logger.debug('do_housekeep(): inactive host %s still has %d instances' %
                                  (host['id'], host['num_instances']))

        # find active hosts
        active_hosts = [x for x in hosts if x['state'] == DD_STATE_ACTIVE]

        # find current free slots
        num_free_slots = sum(DD_CONTAINERS_PER_HOST - x['num_instances'] for x in active_hosts)

        # find projected free slots (only take active hosts with more than 10% lifetime left into account)
        num_projected_free_slots = sum(
            DD_CONTAINERS_PER_HOST - x['num_instances'] for x in active_hosts
            if x['spawn_ts'] < time.time() - (DD_HOST_LIFETIME * 0.9)
        )

        self.logger.info(
            'do_housekeep(): active hosts: %d, free slots: %d now, %d projected for near future' %
            (len(active_hosts), num_free_slots, num_projected_free_slots)
        )

        # if we have less available slots than our target, spawn a new host
        if num_projected_free_slots < DD_FREE_SLOT_TARGET:
            if len(hosts) < DD_MAX_HOSTS:
                new_host = self._spawn_host()
                self.logger.info('do_housekeep(): too few free slots, spawned a new host %s' % new_host['id'])
                hosts.append(new_host)
                self._save_host_state(hosts)
                return
            else:
                self.logger.info('do_housekeep(): too few free slots, but host limit reached')

        # mark old hosts without instances inactive (one at a time)
        for host in active_hosts:
            if host['spawn_ts'] < time.time() - DD_HOST_LIFETIME and host['num_instances'] == 0:
                self.logger.info('do_housekeep(): making host %s inactive' % host['id'])
                host['state'] = DD_STATE_INACTIVE
                self._save_host_state(hosts)
                return

        # no changes to host states, but the number of instances might have changes
        self._save_host_state(hosts)

    def _select_host(self):
        hosts = self._get_hosts()
        active_hosts = [x for x in hosts if x['state'] == DD_STATE_ACTIVE]
        active_hosts = sorted(active_hosts, key=lambda entry: -entry['spawn_ts'])

        selected_host = None
        for host in active_hosts:
            if host['num_instances'] < DD_CONTAINERS_PER_HOST:
                selected_host = host
                break
        if not selected_host:
            raise RuntimeWarning('_select_host(): no space left, active hosts: %s' % active_hosts)

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

    def _save_host_state(self, hosts):
        self.logger.debug("_save_host_state")

        data_file = '%s/%s' % (self.config['INSTANCE_DATA_DIR'], 'docker_driver.json')
        if os.path.exists(data_file):
            ts = int(time.time())
            os.rename(data_file, '%s.%s' % (data_file, ts - ts % 3600))
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
            # 'image': 'CentOS-7.0',
            'image': 'pb_dd_base.20150825',
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
            master_sg_name='pb_server',
            extra_sec_groups=['csc_vpn_all_open', 'csc_ws_all_open'],
        )

        self.logger.debug("_spawn_host_os_service: spawned %s" % res)

        # remove the key from OpenStack
        oss.delete_key(key_name)

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

        for pull_image in ('jupyter/minimal', 'rocker/rstudio'):
            self.logger.debug("_prepare_host(): pulling image %s" % pull_image)
            dc = self.get_docker_client(host['docker_url'])
            dc.pull(pull_image)

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
