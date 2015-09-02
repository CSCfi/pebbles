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

DD_STATE_SPAWNED = 'spawned'
DD_STATE_ACTIVE = 'active'
DD_STATE_INACTIVE = 'inactive'
DD_STATE_REMOVED = 'removed'

DD_HOST_LIFETIME = 600
DD_HOST_LIFETIME_LOW = 60

DD_PROVISION_RETRIES = 10
DD_PROVISION_RETRY_SLEEP = 30
DD_MAX_HOST_ERRORS = 5

DD_RUNTIME_PATH = '/webapps/pouta_blueprints/run'


class DockerDriverAccessProxy(object):
    @staticmethod
    def is_shutdown_mode():
        return os.path.exists('%s/docker_driver_shutdown' % DD_RUNTIME_PATH)

    @staticmethod
    def save_as_json(data_file, data):
        if os.path.exists(data_file):
            ts = int(time.time())
            os.rename(data_file, '%s.%s' % (data_file, ts - ts % 3600))

            with open(data_file, 'w') as df:
                json.dump(data, df)

    @staticmethod
    def get_docker_client(docker_url):
        # TODO: figure out why server verification does not work (crls?)
        tls_config = TLSConfig(
            client_cert=(
                '%s/client_cert.pem' % DD_RUNTIME_PATH, '%s/client_key.pem' % DD_RUNTIME_PATH),
            #   ca_cert='%s/ca_cert.pem' % DD_RUNTIME_PATH,
            verify=False,
        )
        dc = docker.Client(base_url=docker_url, tls=tls_config)

        return dc

    @staticmethod
    def load_json(data_file, default):
        if os.path.exists(data_file):
            with open(data_file, 'r') as df:
                return json.load(df)
        else:
            return default

    @staticmethod
    def get_openstack_service(config):
        return OpenStackService(config)

    @staticmethod
    def get_pb_client(token, api_base_url, ssl_verify):
        return PBClient(token, api_base_url, ssl_verify)

    @staticmethod
    def run_ansible_on_host(host, logger):
        import ansible.runner
        import ansible.playbook
        import ansible.inventory
        from ansible import callbacks
        from ansible import utils

        # global verbosity for debugging e.g. ssh problems with ansible. ugly.
        # utils.VERBOSITY = 4

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

        logger.debug("_prepare_host(): running ansible")
        pb = ansible.playbook.PlayBook(
            playbook="/webapps/pouta_blueprints/source/ansible/notebook_playbook.yml",
            stats=stats,
            callbacks=playbook_cb,
            runner_callbacks=runner_cb,
            inventory=a_inventory,
            remote_user='cloud-user',
        )

        pb_res = pb.run()

        logger.debug(json.dumps(pb_res, sort_keys=True, indent=4, separators=(',', ': ')))

        for host_name in pb_res.keys():
            host_data = pb_res[host_name]
            if host_data.get('unreachable', 0) + host_data.get('failures', 0) > 0:
                raise RuntimeError('run_ansible_on_host(%s) failed' % host['id'])


class DockerDriver(base_driver.ProvisioningDriverBase):
    def get_configuration(self):
        from pouta_blueprints.drivers.provisioning.docker_driver_config import CONFIG

        config = CONFIG.copy()

        return config

    def _get_ap(self):
        if not getattr(self, '_ap', None):
            self._ap = DockerDriverAccessProxy()
        return self._ap

    def do_update_connectivity(self, token, instance_id):
        self.logger.warning('do_update_connectivity not implemented')

    def do_provision(self, token, instance_id):
        self.logger.debug("do_provision %s" % instance_id)
        retries = 0
        while True:
            try:
                self._do_provision_locked(token, instance_id, int(time.time()))
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

    @locked('%s/docker_driver_provisioning' % DD_RUNTIME_PATH)
    def _do_provision_locked(self, token, instance_id, cur_ts):
        return self._do_provision(token, instance_id, cur_ts)

    def _do_provision(self, token, instance_id, cur_ts):
        ap = self._get_ap()

        pbclient = ap.get_pb_client(token, self.config['INTERNAL_API_BASE_URL'], ssl_verify=False)

        instance = pbclient.get_instance_description(instance_id)

        # fetch config
        blueprint = pbclient.get_blueprint_description(instance['blueprint_id'])
        blueprint_config = blueprint['config']

        dh = self._select_host(cur_ts)

        dc = ap.get_docker_client(dh['docker_url'])

        container_name = instance['name']
        password = uuid.uuid4().hex[:16]

        config = {
            'image': blueprint_config['docker_image'],
            'ports': [blueprint_config['internal_port']],
            'name': container_name,
            #            'mem_limit': blueprint_config['memory_limit'],
            'cpu_shares': 5,
            'environment': {'PASSWORD': password},
            #            'host_config': {'Memory': 256 * 1024 * 1024},
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

    @locked('%s/docker_driver_provisioning' % DD_RUNTIME_PATH)
    def do_deprovision(self, token, instance_id):
        return self._do_deprovision(token, instance_id)

    def _do_deprovision(self, token, instance_id):
        self.logger.debug("do_deprovision %s" % instance_id)

        ap = self._get_ap()

        pbclient = ap.get_pb_client(token, self.config['INTERNAL_API_BASE_URL'], ssl_verify=False)
        instance = pbclient.get_instance_description(instance_id)

        if instance['state'] == 'deleted':
            self.logger.debug("do_deprovision: instance already deleted %s" % instance_id)
            return

        try:
            docker_url = instance['instance_data']['docker_url']
        except KeyError:
            self.logger.info('no docker url for instance %s, assuming provisioning has failed' % instance_id)
            return

        dc = ap.get_docker_client(docker_url)

        container_name = instance['name']

        try:
            dc.remove_container(container_name, force=True)
        except APIError as e:
            if e.response.status_code == 404:
                self.logger.info('no container found for instance %s, assuming already deleted' % instance_id)
            else:
                raise e

        self.logger.debug("do_deprovision done for %s" % instance_id)

    @locked('%s/docker_driver_housekeep' % DD_RUNTIME_PATH)
    def do_housekeep(self, token):
        return self._do_housekeep(token, int(time.time()))

    # noinspection PyUnusedLocal
    def _do_housekeep(self, token, cur_ts):
        ap = self._get_ap()

        # in shutdown mode we remove the hosts as soon as no instances are running on them
        shutdown_mode = ap.is_shutdown_mode()
        if shutdown_mode:
            self.logger.info('do_housekeep(): in shutdown mode')

        # fetch host data
        hosts = self._get_hosts(cur_ts)

        self._update_host_lifetimes(hosts, shutdown_mode, cur_ts)

        # count allocated slots
        num_allocated_slots = sum(x['num_instances'] for x in hosts)

        # find active hosts
        active_hosts = [x for x in hosts if x['state'] == DD_STATE_ACTIVE]

        # find current free slots
        num_free_slots = sum(x['num_slots'] - x['num_instances'] for x in active_hosts)

        # find projected free slots (only take active hosts with more than a minute to go)
        num_projected_free_slots = sum(
            x['num_slots'] - x['num_instances'] for x in active_hosts
            if x['lifetime_left'] > DD_HOST_LIFETIME_LOW
        )

        self.logger.info(
            'do_housekeep(): active hosts: %d, free slots: %d now, %d projected for near future' %
            (len(active_hosts), num_free_slots, num_projected_free_slots)
        )

        # priority one: find just spawned hosts, prepare and activate those
        spawned_hosts = [x for x in hosts if x['state'] == DD_STATE_SPAWNED]
        for host in spawned_hosts:
            self.logger.info('do_housekeep(): preparing host %s' % host['id'])
            try:
                self._prepare_host(host)
                host['state'] = DD_STATE_ACTIVE
            except Exception as e:
                self.logger.info('do_housekeep(): preparing host %s failed, %s' % (host['id'], e))
                host['error_count'] = host.get('error_count', 0) + 1
                if host['error_count'] > DD_MAX_HOST_ERRORS:
                    self.logger.warn('do_housekeep(): maximum error count exceeded for host %s' % host['id'])
                    host['state'] = DD_STATE_INACTIVE

            self._save_host_state(hosts)
            return

        # priority two: remove inactive hosts that have no instances on them
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

        # priority three: if we have less available slots than our target, spawn a new host
        if num_projected_free_slots < self.config['DD_FREE_SLOT_TARGET']:
            if shutdown_mode:
                self.logger.info('do_housekeep(): too few free slots, but in shutdown mode')
            elif len(hosts) < self.config['DD_MAX_HOSTS']:
                # try to figure out if we need to use the larger flavor
                # if we at some point can get the number of queueing instances that can be used
                if num_allocated_slots > 0:
                    ramp_up = True
                else:
                    ramp_up = False
                self.logger.debug('do_housekeep(): too few free slots, spawning, ramp_up=%s' % ramp_up)
                new_host = self._spawn_host(cur_ts, ramp_up)
                self.logger.info('do_housekeep(): spawned a new host %s' % new_host['id'])
                hosts.append(new_host)
                self._save_host_state(hosts)
                return
            else:
                self.logger.info('do_housekeep(): too few free slots, but host limit reached')

        # finally mark old hosts without instances inactive (one at a time)
        for host in active_hosts:
            if host['lifetime_left'] == 0 and host['num_instances'] == 0:
                self.logger.info('do_housekeep(): making host %s inactive' % host['id'])
                host['state'] = DD_STATE_INACTIVE
                self._save_host_state(hosts)
                return

        # no changes to host states, but the number of instances might have changes
        self._save_host_state(hosts)

    def _update_host_lifetimes(self, hosts, shutdown_mode, cur_ts):
        self.logger.debug("_update_host_lifetimes()")
        # calculate lifetime
        for host in hosts:
            # shutdown mode, try to get rid of all hosts
            if shutdown_mode:
                lifetime = 0
            # if the host has been used or it is a bigger flavor, calculate lifetime normally
            elif host.get('lifetime_tick_ts', 0):
                lifetime = max(DD_HOST_LIFETIME - (cur_ts - host['lifetime_tick_ts']), 0)
            # if the host is the only one and bigger flavor, don't leave it waiting
            elif len(hosts) == 1 and host['num_slots'] == self.config['DD_HOST_FLAVOR_SLOTS_LARGE']:
                host['lifetime_tick_ts'] = cur_ts
                lifetime = DD_HOST_LIFETIME
            # host has not been used
            else:
                lifetime = DD_HOST_LIFETIME

            host['lifetime_left'] = lifetime
            self.logger.debug('do_housekeep(): host %s has lifetime %d' % (host['id'], lifetime))

    def _select_host(self, cur_ts):
        self.logger.debug("_select_host()")
        hosts = self._get_hosts(cur_ts)
        active_hosts = [x for x in hosts if x['state'] == DD_STATE_ACTIVE]

        # first try to use the oldest active host with space and lifetime left
        active_hosts = sorted(active_hosts, key=lambda entry: entry['spawn_ts'])
        selected_host = None
        for host in active_hosts:
            if host['lifetime_left'] > DD_HOST_LIFETIME_LOW and host['num_instances'] < host['num_slots']:
                selected_host = host
                break
        if not selected_host:
            # try to use any active host with space
            for host in active_hosts:
                if host['num_instances'] < host['num_slots']:
                    selected_host = host
                    break

        if not selected_host:
            raise RuntimeWarning('_select_host(): no space left, active hosts: %s' % active_hosts)

        self.logger.debug("_select_host(): %d total active, selected %s" % (len(active_hosts), selected_host))
        return selected_host

    def _get_hosts(self, cur_ts):
        self.logger.debug("_get_hosts()")
        ap = self._get_ap()

        data_file = '%s/%s' % (self.config['INSTANCE_DATA_DIR'], 'docker_driver.json')

        hosts = ap.load_json(data_file, [])

        # populate hosts with container data
        for host in hosts:
            if host['state'] not in (DD_STATE_ACTIVE, DD_STATE_INACTIVE):
                self.logger.debug('_get_hosts(): skipping container data fetching for %s' % host['id'])
                continue
            dc = ap.get_docker_client(host['docker_url'])
            try:
                # update the number of instances
                containers = dc.containers()
                host['num_instances'] = len(containers)
                self.logger.debug('_get_hosts(): found %d instances on %s' % (len(containers), host['id']))
                # update the usage
                usage = host.get('usage', 0)
                usage += len(containers)
                host['usage'] = usage
                # start lifetime ticking
                if usage and not host.get('lifetime_tick_ts', 0):
                    host['lifetime_tick_ts'] = cur_ts

            except ConnectionError:
                self.logger.warning('_get_hosts(): updating number of instances failed for %s' % host['id'])

        return hosts

    def _save_host_state(self, hosts):
        self.logger.debug("_save_host_state()")
        ap = self._get_ap()
        data_file = '%s/%s' % (self.config['INSTANCE_DATA_DIR'], 'docker_driver.json')
        ap.save_as_json(data_file, hosts)

    def _spawn_host(self, cur_ts, ramp_up=False):
        self.logger.debug("_spawn_host()")

        instance_name = 'pb_dd_%s' % uuid.uuid4().hex
        image_name = self.config['DD_HOST_IMAGE']

        if ramp_up:
            flavor_name = self.config['DD_HOST_FLAVOR_NAME_LARGE']
            flavor_slots = self.config['DD_HOST_FLAVOR_SLOTS_LARGE']
        else:
            flavor_name = self.config['DD_HOST_FLAVOR_NAME_SMALL']
            flavor_slots = self.config['DD_HOST_FLAVOR_SLOTS_SMALL']

        key_name = 'pb_dockerdriver'

        oss = self._get_ap().get_openstack_service({'M2M_CREDENTIAL_STORE': self.config['M2M_CREDENTIAL_STORE']})

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
            'spawn_ts': cur_ts,
            'state': DD_STATE_SPAWNED,
            'num_instances': 0,
            'num_slots': flavor_slots,
        }

    def _prepare_host(self, host):
        self.logger.debug("_prepare_host()")

        ap = self._get_ap()

        ap.run_ansible_on_host(host, self.logger)

        dc = ap.get_docker_client(host['docker_url'])

        dconf = self.get_configuration()

        for pull_image in dconf['schema']['properties']['docker_image']['enum']:
            self.logger.debug("_prepare_host(): pulling image %s" % pull_image)
            dc.pull(pull_image)

    def _remove_host(self, host):
        self.logger.debug("_remove_host()")
        oss = self._get_ap().get_openstack_service({'M2M_CREDENTIAL_STORE': self.config['M2M_CREDENTIAL_STORE']})
        oss.deprovision_instance(host['provider_id'], host['id'])
