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
import pouta_blueprints.tasks
from lockfile import locked

DD_STATE_SPAWNED = 'spawned'
DD_STATE_ACTIVE = 'active'
DD_STATE_INACTIVE = 'inactive'
DD_STATE_REMOVED = 'removed'

DD_HOST_LIFETIME = 3600 * 4
DD_HOST_LIFETIME_LOW = 300

DD_PROVISION_RETRIES = 10
DD_PROVISION_RETRY_SLEEP = 30
DD_MAX_HOST_ERRORS = 5

DD_RUNTIME_PATH = '/webapps/pouta_blueprints/run'


class DockerDriverAccessProxy(object):
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
        docker_client = docker.Client(base_url=docker_url, tls=tls_config)

        return docker_client

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

        # the following does not work, have to use the extra_vars instead
        # a_host.set_variable('notebook_host_block_dev_path', '/dev/vdb')

        a_group = ansible.inventory.group.Group(name='notebook_host')
        a_group.add_host(a_host)

        a_inventory = ansible.inventory.Inventory(host_list=[host['private_ip']])
        a_inventory.add_group(a_group)

        stats = callbacks.AggregateStats()
        playbook_cb = callbacks.PlaybookCallbacks(verbose=utils.VERBOSITY)
        runner_cb = callbacks.PlaybookRunnerCallbacks(stats, verbose=utils.VERBOSITY)

        logger.debug("_prepare_host(): running ansible")
        logger.debug('_prepare_host(): inventory hosts %s' % a_inventory.host_list)

        pb = ansible.playbook.PlayBook(
            playbook="/webapps/pouta_blueprints/source/ansible/notebook_playbook.yml",
            stats=stats,
            callbacks=playbook_cb,
            runner_callbacks=runner_cb,
            inventory=a_inventory,
            remote_user='cloud-user',
            extra_vars={'notebook_host_block_dev_path': '/dev/vdc'},
        )

        pb_res = pb.run()

        logger.debug(json.dumps(pb_res, sort_keys=True, indent=4, separators=(',', ': ')))

        for host_name in pb_res.keys():
            host_data = pb_res[host_name]
            if host_data.get('unreachable', 0) + host_data.get('failures', 0) > 0:
                raise RuntimeError('run_ansible_on_host(%s) failed' % host['id'])

    @staticmethod
    def proxy_add_route(route_id, target_url):
        pouta_blueprints.tasks.proxy_add_route.apply_async(
            args=[route_id, target_url],
            queue='proxy_tasks'
        )

    @staticmethod
    def proxy_remove_route(route_id):
        pouta_blueprints.tasks.proxy_remove_route.apply_async(
            args=[route_id],
            queue='proxy_tasks'
        )


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

        # in shutdown mode we bail out right away
        if self.config['DD_SHUTDOWN_MODE']:
            raise RuntimeWarning('Shutdown mode, no provisioning')

        ap = self._get_ap()
        pbclient = ap.get_pb_client(token, self.config['INTERNAL_API_BASE_URL'], ssl_verify=False)

        retries = 0
        while True:
            try:
                instance = pbclient.get_instance_description(instance_id)
                if instance['state'] != 'provisioning':
                    raise RuntimeError('Instance in wrong state for provisioning')

                self._do_provision_locked(token, instance_id, int(time.time()))
                break
            except RuntimeWarning as e:
                retries += 1
                if retries > DD_PROVISION_RETRIES:
                    raise e
                self.logger.warning(
                    "do_provision failed for %s, sleeping and retrying (%d/%d): %s" % (
                        instance_id, retries, DD_PROVISION_RETRIES, e
                    )
                )
                time.sleep(DD_PROVISION_RETRY_SLEEP)

    @locked('%s/docker_driver_provisioning' % DD_RUNTIME_PATH)
    def _do_provision_locked(self, token, instance_id, cur_ts):
        return self._do_provision(token, instance_id, cur_ts)

    def _do_provision(self, token, instance_id, cur_ts):
        ap = self._get_ap()

        pbclient = ap.get_pb_client(token, self.config['INTERNAL_API_BASE_URL'], ssl_verify=False)

        log_uploader = self.create_prov_log_uploader(token, instance_id, log_type='provisioning')

        instance = pbclient.get_instance_description(instance_id)
        log_uploader.info("Provisioning Docker based instance (%s)\n" % instance_id)

        # fetch config
        blueprint = pbclient.get_blueprint_description(instance['blueprint_id'])
        blueprint_config = blueprint['config']

        log_uploader.info("selecting host\n")
        docker_host = self._select_host(blueprint_config['consumed_slots'], cur_ts)

        docker_client = ap.get_docker_client(docker_host['docker_url'])

        container_name = instance['name']
        # password = uuid.uuid4().hex[:16]

        config = {
            'image': blueprint_config['docker_image'],
            'ports': [blueprint_config['internal_port']],
            'name': container_name,
            #            'environment': {'PASSWORD': password},
            'labels': {'slots': '%d' % blueprint_config['consumed_slots']},
            #            'mem_limit': blueprint_config['memory_limit'],
            #            'host_config': {'Memory': 256 * 1024 * 1024},
        }

        log_uploader.info("creating container %s\n" % container_name)
        container = docker_client.create_container(**config)
        container_id = container['Id']

        log_uploader.info("starting container '%s'\n" % container_name)
        docker_client.start(container_id, publish_all_ports=True)

        # public_ip = docker_host['public_ip']

        # get the public port
        ports = docker_client.port(container_id, blueprint_config['internal_port'])
        if len(ports) == 1:
            public_port = ports[0]['HostPort']
        else:
            raise RuntimeError('Expected exactly one mapped port')

        proxy_route = uuid.uuid4().hex

        instance_data = {
            'endpoints': [
                {
                    'name': 'http',
                    'access': 'http://%s:%s/%s' % (
                        self.config['PUBLIC_IPV4'],
                        self.config['PUBLIC_HTTP_PROXY_PORT'],
                        proxy_route
                    )
                },
            ],
            'docker_url': docker_host['docker_url'],
            'proxy_route': proxy_route,
        }

        pbclient.do_instance_patch(
            instance_id,
            {
                #                'public_ip': self.config['PUBLIC_IPV4'],
                'instance_data': json.dumps(instance_data),
            }
        )

        log_uploader.info("adding route\n")
        ap.proxy_add_route(proxy_route, 'http://%s:%s' % (docker_host['private_ip'], public_port))

        self.logger.debug("do_provision done for %s" % instance_id)

    @locked('%s/docker_driver_provisioning' % DD_RUNTIME_PATH)
    def do_deprovision(self, token, instance_id):
        return self._do_deprovision(token, instance_id)

    def _do_deprovision(self, token, instance_id):
        self.logger.debug("do_deprovision %s" % instance_id)

        ap = self._get_ap()

        pbclient = ap.get_pb_client(token, self.config['INTERNAL_API_BASE_URL'], ssl_verify=False)
        instance = pbclient.get_instance_description(instance_id)
        log_uploader = self.create_prov_log_uploader(token, instance_id, log_type='deprovisioning')

        log_uploader.info("Deprovisioning Docker based instance (%s)\n" % instance_id)

        try:
            proxy_route = instance['instance_data']['proxy_route']
            ap.proxy_remove_route(proxy_route)
            log_uploader.info("removed route\n")
        except KeyError:
            self.logger.info("do_deprovision: No proxy route in instance data for %s" % instance_id)

        if instance['state'] == 'deleted':
            self.logger.debug("do_deprovision: instance already deleted %s" % instance_id)
            return

        try:
            docker_url = instance['instance_data']['docker_url']
        except KeyError:
            self.logger.info('no docker url for instance %s, assuming provisioning has failed' % instance_id)
            return

        docker_client = ap.get_docker_client(docker_url)

        container_name = instance['name']

        try:
            docker_client.remove_container(container_name, force=True)
            log_uploader.info("removed container %s\n" % container_name)
        except APIError as e:
            if e.response.status_code == 404:
                self.logger.info('no container found for instance %s, assuming already deleted' % instance_id)
            else:
                raise e

        self.logger.debug("do_deprovision done for %s" % instance_id)

    @staticmethod
    def get_active_hosts(hosts):
        active_hosts = [x for x in hosts if x['state'] == DD_STATE_ACTIVE]
        return active_hosts

    @staticmethod
    def calculate_allocated_slots(hosts):
        num_allocated_slots = sum(x['num_reserved_slots'] for x in hosts)
        return num_allocated_slots

    @staticmethod
    def calculate_free_slots(active_hosts):
        num_free_slots = sum(
            x['num_slots'] - x['num_reserved_slots'] for x in active_hosts
            if x['state'] == DD_STATE_ACTIVE
        )
        return num_free_slots

    @staticmethod
    def calculate_projected_free_slots(hosts):
        num_projected_free_slots = sum(
            x['num_slots'] - x['num_reserved_slots'] for x in hosts
            if x['lifetime_left'] > DD_HOST_LIFETIME_LOW and x['state'] == DD_STATE_ACTIVE
        )
        return num_projected_free_slots

    @locked('%s/docker_driver_housekeep' % DD_RUNTIME_PATH)
    def do_housekeep(self, token):
        return self._do_housekeep(token, int(time.time()))

    # noinspection PyUnusedLocal
    def _do_housekeep(self, token, cur_ts):
        ap = self._get_ap()

        # in shutdown mode we remove the hosts as soon as no instances are running on them
        shutdown_mode = self.config['DD_SHUTDOWN_MODE']
        if shutdown_mode:
            self.logger.info('do_housekeep(): in shutdown mode')

        # fetch host data
        hosts = self._get_hosts(cur_ts)

        self._update_host_lifetimes(hosts, shutdown_mode, cur_ts)

        # find active hosts
        active_hosts = self.get_active_hosts(hosts)

        # find current free slots
        num_free_slots = self.calculate_free_slots(hosts)

        # find projected free slots (only take active hosts with more than a minute to go)
        num_projected_free_slots = self.calculate_projected_free_slots(hosts)

        self.logger.info(
            'do_housekeep(): active hosts: %d, free slots: %d now, %d projected for near future' %
            (len(active_hosts), num_free_slots, num_projected_free_slots)
        )

        # priority one: find just spawned hosts, prepare and activate those
        if self._activate_spawned_hosts(hosts=hosts, cur_ts=cur_ts):
            self.logger.debug('do_housekeep(): activate action taken')

        # priority two: remove inactive hosts that have no instances on them
        elif self._remove_inactive_hosts(hosts=hosts, cur_ts=cur_ts):
            self.logger.debug('do_housekeep(): remove action taken')

        # priority three: if we have less available slots than our target, spawn a new host
        # in shutdown mode we skip this
        elif not shutdown_mode and self._spawn_new_host(hosts=hosts, cur_ts=cur_ts):
            self.logger.debug('do_housekeep(): spawn action taken')

        # finally mark old hosts without instances inactive (one at a time)
        elif self._inactivate_old_hosts(hosts=hosts, cur_ts=cur_ts):
            self.logger.debug('do_housekeep(): inactivate action taken')

        # save host state in the end
        self._save_host_state(hosts, cur_ts)

    # noinspection PyUnusedLocal
    def _activate_spawned_hosts(self, hosts, cur_ts):
        spawned_hosts = [x for x in hosts if x['state'] == DD_STATE_SPAWNED]
        for host in spawned_hosts:
            self.logger.info('do_housekeep(): preparing host %s' % host['id'])
            try:
                self._prepare_host(host)
                host['state'] = DD_STATE_ACTIVE
                self.logger.info('do_housekeep(): host %s now active' % host['id'])
            except Exception as e:
                self.logger.info('do_housekeep(): preparing host %s failed, %s' % (host['id'], e))
                host['error_count'] = host.get('error_count', 0) + 1
                if host['error_count'] > DD_MAX_HOST_ERRORS:
                    self.logger.warn('do_housekeep(): maximum error count exceeded for host %s' % host['id'])
                    host['state'] = DD_STATE_INACTIVE
            return True

        return False

    # noinspection PyUnusedLocal
    def _remove_inactive_hosts(self, hosts, cur_ts):
        inactive_hosts = [x for x in hosts if x['state'] == DD_STATE_INACTIVE]
        for host in inactive_hosts:
            if host['num_reserved_slots'] == 0:
                self.logger.info('do_housekeep(): removing host %s' % host['id'])
                self._remove_host(host)
                hosts.remove(host)
                return True
            else:
                self.logger.debug('do_housekeep(): inactive host %s still has %d reserved slots' %
                                  (host['id'], host['num_reserved_slots']))

        return False

    def _spawn_new_host(self, hosts, cur_ts):
        # find projected free slots (only take active hosts with more than a minute to go)
        num_projected_free_slots = self.calculate_projected_free_slots(hosts)
        num_allocated_slots = self.calculate_allocated_slots(hosts)

        if num_projected_free_slots < self.config['DD_FREE_SLOT_TARGET']:
            if len(hosts) < self.config['DD_MAX_HOSTS']:
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
                return True
            else:
                self.logger.info('do_housekeep(): too few free slots, but host limit reached')

        return False

    # noinspection PyUnusedLocal
    def _inactivate_old_hosts(self, hosts, cur_ts):
        active_hosts = self.get_active_hosts(hosts)
        for host in active_hosts:
            if host['lifetime_left'] == 0 and host['num_reserved_slots'] == 0:
                self.logger.info('do_housekeep(): making host %s inactive' % host['id'])
                host['state'] = DD_STATE_INACTIVE
                return True

        return False

    def _update_host_lifetimes(self, hosts, shutdown_mode, cur_ts):
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

    def _select_host(self, slots, cur_ts):
        hosts = self._get_hosts(cur_ts)
        active_hosts = self.get_active_hosts(hosts)

        # first try to use the oldest active host with space and lifetime left
        active_hosts = sorted(active_hosts, key=lambda entry: entry['spawn_ts'])
        selected_host = None
        for host in active_hosts:
            if host['lifetime_left'] > DD_HOST_LIFETIME_LOW and host['num_slots'] - host['num_reserved_slots'] >= slots:
                selected_host = host
                break
        if not selected_host:
            # try to use any active host with space
            for host in active_hosts:
                if host['num_slots'] - host['num_reserved_slots'] >= slots:
                    selected_host = host
                    break

        if not selected_host:
            raise RuntimeWarning('_select_host(): no space left, active hosts: %s' % active_hosts)

        self.logger.debug("_select_host(): %d total active, selected %s" % (len(active_hosts), selected_host))
        return selected_host

    def _get_hosts(self, cur_ts):
        ap = self._get_ap()

        data_file = '%s/%s' % (self.config['INSTANCE_DATA_DIR'], 'docker_driver.json')

        hosts = ap.load_json(data_file, [])

        # populate hosts with container data
        for host in hosts:
            if host['state'] not in (DD_STATE_ACTIVE, DD_STATE_INACTIVE):
                self.logger.debug('_get_hosts(): skipping container data fetching for %s' % host['id'])
                continue
            docker_client = ap.get_docker_client(host['docker_url'])
            try:
                # update the number of reserved slots
                containers = docker_client.containers()
                host['num_reserved_slots'] = sum(int(cont['Labels'].get('slots', 1)) for cont in containers)
                self.logger.debug('_get_hosts(): found %d instances with %d slots on %s' %
                                  (len(containers), host['num_reserved_slots'], host['id']))

                # update the accumulative usage
                usage = host.get('usage', 0)
                usage += host['num_reserved_slots']
                host['usage'] = usage
                # start lifetime ticking
                if usage and not host.get('lifetime_tick_ts', 0):
                    host['lifetime_tick_ts'] = cur_ts

            except ConnectionError:
                self.logger.warning('_get_hosts(): updating number of instances failed for %s' % host['id'])

        return hosts

    def _save_host_state(self, hosts, cur_ts):
        ap = self._get_ap()
        data_file = '%s/%s' % (self.config['INSTANCE_DATA_DIR'], 'docker_driver.json')
        ap.save_as_json(data_file, hosts)

    def _spawn_host(self, cur_ts, ramp_up=False):
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
            master_sg_name=self.config['DD_HOST_MASTER_SG'],
            extra_sec_groups=[x.strip() for x in self.config['DD_HOST_EXTRA_SGS'].split()],
            allocate_public_ip=False,
            root_volume_size=0,
            data_volume_size=flavor_slots * 4,
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
            'num_reserved_slots': 0,
            'num_slots': flavor_slots,
        }

    def _prepare_host(self, host):
        ap = self._get_ap()

        ap.run_ansible_on_host(host, self.logger)

        docker_client = ap.get_docker_client(host['docker_url'])

        dconf = self.get_configuration()

        for image_name in dconf['schema']['properties']['docker_image']['enum']:
            filename = '%s/%s.img' % ('/images', image_name.replace('/', '.'))
            self.logger.debug("_prepare_host(): uploading image %s from file %s" % (image_name, filename))
            with open(filename, 'r') as img_file:
                docker_client.load_image(img_file)

    def _remove_host(self, host):
        self.logger.debug("_remove_host()")
        oss = self._get_ap().get_openstack_service({'M2M_CREDENTIAL_STORE': self.config['M2M_CREDENTIAL_STORE']})
        oss.deprovision_instance(host['provider_id'], host['id'])
