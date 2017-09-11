"""

DockerDriver maintains a pool of hosts running Docker and starts containers on
one host.

For safety reasons and to avoid stuck situations the hosts expire after 4
hours and are respawned after the last container on them has been removed.

An important concept to DD are **slots**. A slot is roughly 512MB of memory
and it is used to assign containers to **pool hosts**. A pool host has a
number of slots and the driver won't assign any more containers to a host that
doesn't have the slots for it.

The system maintains a number of hosts to reach DD_FREE_SLOT_TARGET unless
DD_SHUTDOWN_MODE is True, in which case it waits for all containers on a host
to finish and then shuts down the host.

DockerDriver configurations are available via the UI admin dashboard under
"Driver Configs".

+----------------------------+--------------------------------------------------------------+
| Config                     | Description                                                  |
+----------------------------+--------------------------------------------------------------+
| DD_FREE_SLOT_TARGET        | Number of "slots" the system should have available           |
+----------------------------+--------------------------------------------------------------+
| DD_HOST_DATA_VOLUME_DEVICE | ToDo                                                         |
+----------------------------+--------------------------------------------------------------+
| DD_HOST_DATA_VOLUME_FACTOR | ToDo                                                         |
+----------------------------+--------------------------------------------------------------+
| DD_HOST_DATA_VOLUME_TYPE   |                                                              |
+----------------------------+--------------------------------------------------------------+
| DD_HOST_EXTRA_SGS          | Extra security groups (name) to add to the hosts.            |
|                            | Note that security group must exist in tenant!               |
+----------------------------+--------------------------------------------------------------+
| DD_HOST_FLAVOR_NAME_LARGE  | OpenStack flavor of a large host.                            |
+----------------------------+--------------------------------------------------------------+
| DD_HOST_FLAVOR_NAME_SMALL  | OpenStack flavor of a small host.                            |
+----------------------------+--------------------------------------------------------------+
| DD_HOST_FLAVOR_SLOTS_LARGE | How many slots a large instance provides                     |
+----------------------------+--------------------------------------------------------------+
| DD_HOST_FLAVOR_SLOTS_SMALL | How many slots a small instance provides                     |
+----------------------------+--------------------------------------------------------------+
| DD_HOST_IMAGE              | The image a host should have                                 |
+----------------------------+--------------------------------------------------------------+
| DD_HOST_MASTER_SG          | The security group that the pebbles instance is on.          |
|                            | A security group rule is created to allow traffic from       |
|                            | this security group to the pool host.                        |
+----------------------------+--------------------------------------------------------------+
| DD_HOST_NETWORK            | UUID of the network to which the pool host should be added.  |
|                            | Can be "auto" if there is only one network in a tenant.      |
+----------------------------+--------------------------------------------------------------+
| DD_MAX_HOSTS               | Do not spawn more than this many hosts.                      |
+----------------------------+--------------------------------------------------------------+
| DD_HOST_ROOT_VOLUME_SIZE   | How large a volume to create to the hosts                    |
+----------------------------+--------------------------------------------------------------+
| DD_SHUTDOWN_MODE           | Stop all hosts when they become free.                        |
+----------------------------+--------------------------------------------------------------+
"""

import json
import time
import uuid
from docker.errors import APIError
from docker.tls import TLSConfig
from docker.utils import parse_bytes
import os
import sys
from requests import ConnectionError
from requests.exceptions import ReadTimeout
from pebbles.client import PBClient
from pebbles.drivers.provisioning import base_driver
import docker
from pebbles.models import Instance
from pebbles.services.openstack_service import OpenStackService
import pebbles.tasks
from lockfile import locked, LockTimeout
import socket

DD_STATE_SPAWNED = 'spawned'
DD_STATE_ACTIVE = 'active'
DD_STATE_INACTIVE = 'inactive'
DD_STATE_REMOVED = 'removed'

DD_HOST_LIFETIME = 3600 * 4
DD_HOST_LIFETIME_LOW = 300

DD_PROVISION_RETRIES = 10
DD_PROVISION_RETRY_SLEEP = 30
DD_MAX_HOST_ERRORS = 5

DD_RUNTIME_PATH = '/webapps/pebbles/run'
DD_IMAGE_DIRECTORY = '/images'

DD_CLIENT_TIMEOUT = 180  # seconds

PEBBLES_SSH_KEY_LOCATION = '/home/pebbles/.ssh/id_rsa'

NAMESPACE = "DockerDriver"
KEY_PREFIX_POOL = "pool_vm"
KEY_CONFIG = "backend_config"


class DockerDriverAccessProxy(object):
    """
    An abstract layer for executing external processes by docker driver.
    This also helps in unit testing of the driver with mock objects.
    """
    @staticmethod
    def get_docker_client(docker_url):
        # TODO: figure out why server verification does not work (crls?)
        tls_config = TLSConfig(
            client_cert=(
                '%s/client_cert.pem' % DD_RUNTIME_PATH, '%s/client_key.pem' % DD_RUNTIME_PATH),
            #   ca_cert='%s/ca_cert.pem' % DD_RUNTIME_PATH,
            verify=False,
        )
        docker_client = docker.Client(base_url=docker_url, tls=tls_config, timeout=DD_CLIENT_TIMEOUT)

        return docker_client

    @staticmethod
    def get_openstack_service(config):
        return OpenStackService(config)

    @staticmethod
    def get_pb_client(token, api_base_url, ssl_verify):
        """
        Get a custom client for interacting with external REST APIs
        Parameters:
        token - the authentication token required by the api
        api_base_url - the base url for the api
        ssl_verify . flag to check SSL certificates on the api requests
        """
        return PBClient(token, api_base_url, ssl_verify)

    @classmethod
    def load_records(cls, token, url):
        """ Loads the pool vm host state from the database through REST API
            There can be multiple pool vms at a time (in different states)
        """
        pbclient = cls.get_pb_client(token, url, ssl_verify=False)
        namespaced_records = pbclient.get_namespaced_keyvalues({'namespace': NAMESPACE, 'key': KEY_PREFIX_POOL})
        hosts = []
        for ns_record in namespaced_records:
            hosts.append(ns_record['value'])
        return hosts

    @classmethod
    def save_records(cls, token, url, hosts):
        """Saves the pool vm host state in the database via REST API
        """
        pbclient = cls.get_pb_client(token, url, ssl_verify=False)
        for host in hosts:
            _key = '%s_%s' % (KEY_PREFIX_POOL, host['id'])
            payload = {
                'namespace': NAMESPACE,
                'key': _key,
                'schema': {}
            }
            if host.get('state') in [DD_STATE_SPAWNED, DD_STATE_ACTIVE, DD_STATE_INACTIVE]:  # POST or PUT
                payload['value'] = host
                pbclient.create_or_modify_namespaced_keyvalue(NAMESPACE, _key, payload)
            elif host.get('state') == DD_STATE_REMOVED:  # DELETE
                pbclient.delete_namespaced_keyvalue(NAMESPACE, _key)

    @classmethod
    def load_driver_config(cls, token, url):
        """ Loads the driver config from the database through REST API
            There will always be one config for the driver
        """
        pbclient = cls.get_pb_client(token, url, ssl_verify=False)
        namespaced_record = pbclient.get_namespaced_keyvalue(NAMESPACE, KEY_CONFIG)
        driver_config = namespaced_record['value']
        return driver_config

    @staticmethod
    def run_ansible_on_host(host, logger, driver_config):
        from ansible.plugins.callback import CallbackBase
        # A rough logger that logs dict messages to standard logger

        class ResultCallback(CallbackBase):

            def __init__(self):
                super(ResultCallback, self).__init__()

            def v2_runner_on_ok(self, result, **kwargs):
                self.log('ok :' + str(result._result))

            def v2_runner_on_failed(self, result, **kwargs):
                warnings = result._result['warnings']
                error = result._result['stderr']
                if warnings:
                    self.log('warning : ' + str(result._result))
                elif error:
                    self.log('error : ' + str(result._result), info=True)

            def v2_runner_on_skipped(self, result, **kwargs):
                self.log('skipped : ' + str(result._result))

            def v2_runner_on_unreachable(self, result, **kwargs):
                self.log('unreachable : ' + str(result._result), info=True)

            def v2_playbook_on_no_hosts_matched(self, *args, **kwargs):
                self.log('no hosts matched!')

            def v2_playbook_on_no_hosts_remaining(self, *args, **kwargs):
                self.log('NO MORE HOSTS LEFT')

            def v2_playbook_on_task_start(self, task, **kwargs):
                self.log('starting task: ' + str(task))

            def v2_playbook_on_start(self, playbook, **kwargs):
                self.log('starting playbook' + str(playbook), info=True)

            def v2_playbook_on_play_start(self, play, **kwargs):
                self.log('starting play' + str(play), info=True)

            def v2_playbook_on_stats(self, stats, info=True, **kwargs):
                self.log('STATS FOR PLAY')
                hosts = sorted(stats.processed.keys())
                hosts.extend(stats.failures.keys())
                hosts.extend(stats.dark.keys())
                hosts.extend(stats.changed.keys())
                hosts.extend(stats.skipped.keys())
                hosts.extend(stats.ok.keys())
                for h in hosts:
                    t = stats.summarize(h)
                    self.log(str(t))

            def log(self, param, info=False):
                if not info:
                    logger.debug(str(param))
                else:
                    logger.info(str(param))

        from ansible.parsing.dataloader import DataLoader
        from ansible.inventory import Inventory, Group, Host
        from ansible.executor import playbook_executor
        from ansible.vars import VariableManager
        from collections import namedtuple

        Options = namedtuple(
            'Options',
            [
                'connection',
                'module_path',
                'forks',
                'become',
                'become_method',
                'become_user',
                'check',
                'ansible_user',
                'listhosts',
                'listtasks',
                'listtags',
                'syntax',
                'ssh_private_key_file',
                'host_key_checking'
            ]
        )

        options = Options(
            connection='ssh',
            become=True,
            become_method='sudo',
            become_user='root',
            check=False,
            module_path=None,
            forks=100,
            ansible_user='cloud-user',
            listhosts=False,
            listtasks=False,
            listtags=False,
            syntax=False,
            ssh_private_key_file=PEBBLES_SSH_KEY_LOCATION,
            host_key_checking=False
        )

        variable_manager = VariableManager()
        loader = DataLoader()

        a_host = Host(name=host['private_ip'])
        a_host.set_variable('ansible_host', host['private_ip'])
        a_group = Group(name='notebook_host')
        a_group.add_host(a_host)
        inventory = Inventory(loader=loader, variable_manager=variable_manager, host_list=[host['private_ip']])
        inventory.add_group(a_group)
        variable_manager.set_inventory(inventory)
        logger.debug('HOST:')
        logger.debug(a_host.serialize()	)
        logger.debug('HOSTs from inventory:')
        # for some reason setting these before adding the host to inventory didn't work so well
        # ToDo: read up on variable_manager and figure out a more elegant way to set the variables
        for h_ in inventory.get_hosts():
            h_.set_variable('ansible_user', 'cloud-user')
            h_.set_variable('ansible_ssh_common_args', '-o StrictHostKeyChecking=no')
            h_.set_variable('ansible_ssh_private_key_file', '/home/pebbles/.ssh/id_rsa')
        extra_vars = dict()
        extra_vars['ansible_ssh_extra_args'] = '-o StrictHostKeyChecking=no'

        logger.debug('Setting driver config....')
        if 'DD_HOST_DATA_VOLUME_DEVICE' in driver_config:
            extra_vars['notebook_host_block_dev_path'] = driver_config['DD_HOST_DATA_VOLUME_DEVICE']
        variable_manager.extra_vars = extra_vars
        pb_executor = playbook_executor.PlaybookExecutor(
            playbooks=['/webapps/pebbles/source/ansible/notebook_playbook.yml'],
            inventory=inventory,
            variable_manager=variable_manager,
            loader=loader,
            options=options,
            passwords=None
        )
        rescb = ResultCallback()
        pb_executor._tqm._stdout_callback = rescb

        logger.info('_prepare_host(): running ansible')
        logger.info('_prepare_host(): inventory hosts')
        for h_ in inventory.get_hosts():
            logger.info(h_.serialize())
            logger.info(h_.get_vars())
        pb_executor.run()
        stats = pb_executor._tqm._stats
        run_success = True
        hosts_list = sorted(stats.processed.keys())
        if len(hosts_list) == 0:
            logger.debug('no hosts handled')
        for h in hosts_list:
            t = stats.summarize(h)
            logger.debug(t)
            logger.debug(h)
            if t['unreachable'] > 0 or t['failures'] > 0:
                run_success = False
        if run_success:
                logger.debug('_prepare_host(): run successfull')
        else:
                logger.debug('_prepare_host(): run failed')
        if getattr(pb_executor, '_unreachable_hosts', False):
            logger.debug('UNREACHABLE HOSTS ' + str(pb_executor._unreachable_hosts))
        if getattr(pb_executor, '_failed_hosts', False):
            logger.debug('FAILED_HOSTS ' + str(pb_executor._failed_hosts))
            raise RuntimeError('run_ansible_on_host(%s) failed' % host['id'])
        logger.debug('_prepare_host():  done running ansible')

    @staticmethod
    def proxy_add_route(route_id, target_url, options):
        pebbles.tasks.proxy_add_route.delay(route_id, target_url, options)

    @staticmethod
    def proxy_remove_route(route_id):
        pebbles.tasks.proxy_remove_route.delay(route_id)

    @staticmethod
    def get_image_names():
        return [file_name[:-len('.img')].replace('.', '/', 1)
                for file_name in os.listdir(DD_IMAGE_DIRECTORY)
                if os.path.isfile(os.path.join(DD_IMAGE_DIRECTORY, file_name)) and file_name.endswith('.img')
                ]

    @staticmethod
    def wait_for_port(ip_address, port, max_wait_secs=60):
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(1)
        start = time.time()
        is_port_active = False
        while time.time() - start < max_wait_secs:
            result = s.connect_ex((ip_address, port))
            if result == 0:
                is_port_active = True
                break
            time.sleep(2)
        s.close()
        if not is_port_active:
            raise RuntimeError('Timeout: Could not listen to port')


class DockerDriver(base_driver.ProvisioningDriverBase):
    """ ToDo: document what the docker driver does for an admin/developer here
    """
    def get_configuration(self):
        """ Return the default config values which are needed for the
            plugin creation (via schemaform)
        """
        from pebbles.drivers.provisioning.docker_driver_config import CONFIG

        config = CONFIG.copy()
        image_names = self._get_ap().get_image_names()
        config['schema']['properties']['docker_image']['enum'] = image_names

        return config

    def get_backend_configuration(self):
        """ Return the default values for the variables
            which are needed as a part of backend configuration
        """
        from pebbles.drivers.provisioning.docker_driver_config import BACKEND_CONFIG
        backend_config = BACKEND_CONFIG.copy()
        return backend_config

    def _get_ap(self):
        if not getattr(self, '_ap', None):
            self._ap = DockerDriverAccessProxy()
        return self._ap

    def _set_driver_backend_config(self, token):
        """ Set the driver_config variable for usage in the
            docker driver (i.e. the current class)
        """
        ap = self._get_ap()
        self.driver_config = ap.load_driver_config(token, self.config['INTERNAL_API_BASE_URL'])

    def do_update_connectivity(self, token, instance_id):
        self.logger.warning('do_update_connectivity not implemented')

    def get_running_instance_logs(self, token, instance_id):
        """ Get the logs of the instance which is in running state """
        self.logger.debug("getting container logs for instance id %s" % instance_id)
        ap = self._get_ap()
        running_log_uploader = self.create_prov_log_uploader(token, instance_id, log_type='running')
        pbclient = ap.get_pb_client(token, self.config['INTERNAL_API_BASE_URL'], ssl_verify=False)
        instance = pbclient.get_instance(instance_id)
        container_name = instance['name']

        if 'instance_data' not in instance:
            self.logger.debug('no instance_data found, cannot fetch logs for %s' % instance_id)
            raise RuntimeWarning('Cannot fetch logs for %s' % container_name)

        instance_docker_url = instance['instance_data']['docker_url']
        docker_client = ap.get_docker_client(instance_docker_url)
        container_logs = docker_client.logs(container_name)
        running_log_uploader.info(container_logs)

    def do_provision(self, token, instance_id):
        self._set_driver_backend_config(token)  # set the driver specific config vars from the db
        self.logger.debug("do_provision %s" % instance_id)
        log_uploader = self.create_prov_log_uploader(token, instance_id, log_type='provisioning')

        log_uploader.info("Provisioning Docker based instance (%s)\n" % instance_id)

        # in shutdown mode we bail out right away
        if self.driver_config['DD_SHUTDOWN_MODE']:
            log_uploader.info("system is in shutdown mode, cannot provision new instances\n")
            raise RuntimeWarning('Shutdown mode, no provisioning')

        ap = self._get_ap()
        pbclient = ap.get_pb_client(token, self.config['INTERNAL_API_BASE_URL'], ssl_verify=False)
        lock_id = 'dd_host:%s' % 'global'
        try:
            lock_res = pbclient.obtain_lock(lock_id)
            while not lock_res:
                time.sleep(5)
                lock_res = pbclient.obtain_lock(lock_id)

            try:
                self._do_provision(token, instance_id, int(time.time()))
                return Instance.STATE_RUNNING
            except (RuntimeWarning, ConnectionError) as e:
                self.logger.info('_do_provision() failed for %s due to %s' % (instance_id, e))
                log_uploader.info("provisioning failed, queueing again to retry\n")
                return Instance.STATE_QUEUEING
        finally:
            pbclient.release_lock(lock_id)
            # give proxy and container some time to initialize
            time.sleep(2)

    def _do_provision(self, token, instance_id, cur_ts):
        ap = self._get_ap()

        pbclient = ap.get_pb_client(token, self.config['INTERNAL_API_BASE_URL'], ssl_verify=False)

        log_uploader = self.create_prov_log_uploader(token, instance_id, log_type='provisioning')

        instance = pbclient.get_instance_description(instance_id)

        # fetch config
        blueprint = pbclient.get_blueprint_description(instance['blueprint_id'])
        blueprint_config = blueprint['full_config']

        log_uploader.info("selecting host...")

        docker_hosts = self._select_hosts(blueprint_config['consumed_slots'], token, cur_ts)
        selected_host = docker_hosts[0]

        docker_client = ap.get_docker_client(selected_host['docker_url'])

        log_uploader.info("done\n")

        container_name = instance['name']

        # total_memory is set to 3 times the size of RAM limit
        host_config = docker_client.create_host_config(
            mem_limit=blueprint_config['memory_limit'],
            memswap_limit=parse_bytes(blueprint_config['memory_limit']) * 3,
            publish_all_ports=True,
        )

        proxy_route = uuid.uuid4().hex

        config = {
            'image': blueprint_config['docker_image'],
            'name': container_name,
            'labels': {'slots': '%d' % blueprint_config['consumed_slots']},
            'host_config': host_config,
            'environment': blueprint_config['environment_vars'].split(),
        }
        config['environment'].append(format('INSTANCE_ID=%s' % instance_id))
        config['environment'].append(format('TZ=%s' % 'Asia/Delhi'))

        if len(blueprint_config.get('launch_command', '')):
            launch_command = blueprint_config.get('launch_command').format(
                proxy_path='/%s' % proxy_route
            )
            config['command'] = launch_command

        log_uploader.info("creating container '%s'\n" % container_name)
        container = docker_client.create_container(**config)
        container_id = container['Id']

        log_uploader.info("starting container '%s'\n" % container_name)
        docker_client.start(container_id)

        # get the public port
        ports = docker_client.port(container_id, blueprint_config['internal_port'])
        if len(ports) == 1:
            public_port = ports[0]['HostPort']
            try:
                self._ap.wait_for_port(selected_host['private_ip'], int(public_port))
            except RuntimeError:
                log_uploader.warn("Could not check if the port used in provisioning is listening")

        else:
            raise RuntimeError('Expected exactly one mapped port')

        instance_data = {
            'endpoints': [
                {
                    'name': 'https',
                    'access': 'https://%s:%s/%s' % (
                        self.config['PUBLIC_IPV4'],
                        self.config['EXTERNAL_HTTPS_PORT'],
                        'notebooks/' + proxy_route
                    )
                },
            ],
            'docker_url': selected_host['docker_url'],
            'docker_host_id': selected_host['id'],
            'proxy_route': proxy_route,
        }
        if 'show_password' in blueprint_config and blueprint_config['show_password']:
            instance_data['password'] = instance_id

        pbclient.do_instance_patch(
            instance_id,
            {
                #                'public_ip': self.config['PUBLIC_IPV4'],
                'instance_data': json.dumps(instance_data),
            }
        )

        log_uploader.info("adding route\n")

        options = {}
        proxy_options = blueprint_config.get('proxy_options')
        if proxy_options:
            proxy_rewrite = proxy_options.get('proxy_rewrite')
            proxy_redirect = proxy_options.get('proxy_redirect')
            set_host_header = proxy_options.get('set_host_header')
            bypass_token_authentication = proxy_options.get('bypass_token_authentication')

            if proxy_rewrite:
                options['proxy_rewrite'] = proxy_rewrite
            if proxy_redirect:
                options['proxy_redirect'] = proxy_redirect
            if set_host_header:
                options['set_host_header'] = set_host_header
            if bypass_token_authentication:
                options['bypass_token_authentication'] = instance_id  # rather than a boolean value, send the instance id

        ap.proxy_add_route(
            proxy_route,
            'http://%s:%s' % (selected_host['private_ip'], public_port),
            options
        )
        log_uploader.info("provisioning done for %s\n" % instance_id)

    def do_deprovision(self, token, instance_id):
        ap = self._get_ap()
        pbclient = ap.get_pb_client(token, self.config['INTERNAL_API_BASE_URL'], ssl_verify=False)

        lock_id = 'dd_host:%s' % 'global'
        try:
            lock_res = pbclient.obtain_lock(lock_id)
            while not lock_res:
                time.sleep(5)
                lock_res = pbclient.obtain_lock(lock_id)

            return self._do_deprovision(token, instance_id)
        finally:
            pbclient.release_lock(lock_id)

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

        if instance['state'] == Instance.STATE_DELETED:
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
        except ConnectionError as e:
            self.logger.info('no host found for instance %s, assuming already deleted, exception: %s' %
                             (instance_id, e))

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

    def do_housekeep(self, token):
        try:
            return self._do_housekeep_locked(token)
        except LockTimeout:
            self.logger.info('do_housekeep(): another thread is locking, skipping')

    @locked('%s/docker_driver_housekeep' % DD_RUNTIME_PATH, 1)
    def _do_housekeep_locked(self, token):
        return self._do_housekeep(token, int(time.time()))

    def _do_housekeep(self, token, cur_ts):
        self._set_driver_backend_config(token)  # set the driver specific config vars from the db

        # in shutdown mode we remove the hosts as soon as no instances are running on them
        shutdown_mode = self.driver_config['DD_SHUTDOWN_MODE']
        if shutdown_mode:
            self.logger.info('do_housekeep(): in shutdown mode')

        # fetch host data
        hosts = self._get_hosts(token, cur_ts)

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
        self._save_host_state(hosts, token, cur_ts)

    def _activate_spawned_hosts(self, hosts, cur_ts):
        spawned_hosts = [x for x in hosts if x['state'] == DD_STATE_SPAWNED]
        for host in spawned_hosts:
            self.logger.info('do_housekeep(): preparing host %s' % host['id'])
            try:
                self._prepare_host(host)
                host['state'] = DD_STATE_ACTIVE
                self.logger.info('do_housekeep(): host %s now ACTIVE' % host['id'])
            except Exception as e:
                self.logger.info('do_housekeep(): preparing host %s failed, %s, on line %d' % (host['id'], e, sys.exc_info()[-1].tb_lineno))
                self.logger.error(e)
                host['error_count'] = host.get('error_count', 0) + 1
                if host['error_count'] > DD_MAX_HOST_ERRORS:
                    self.logger.warn('do_housekeep(): maximum error count exceeded for host %s' % host['id'])
                    host['state'] = DD_STATE_INACTIVE
            return True

        return False

    def _remove_inactive_hosts(self, hosts, cur_ts):
        inactive_hosts = [x for x in hosts if x['state'] == DD_STATE_INACTIVE]
        for host in inactive_hosts:
            if host['num_reserved_slots'] == 0:
                self.logger.info('do_housekeep(): REMOVING host %s' % host['id'])
                self._remove_host(host)
                # hosts.remove(host)
                host['state'] = DD_STATE_REMOVED
                return True
            else:
                self.logger.debug('do_housekeep(): inactive host %s still has %d reserved slots' %
                                  (host['id'], host['num_reserved_slots']))

        return False

    def _spawn_new_host(self, hosts, cur_ts):
        # find projected free slots (only take active hosts with more than a minute to go)
        num_projected_free_slots = self.calculate_projected_free_slots(hosts)
        num_allocated_slots = self.calculate_allocated_slots(hosts)

        if num_projected_free_slots < self.driver_config['DD_FREE_SLOT_TARGET']:
            if len(hosts) < self.driver_config['DD_MAX_HOSTS']:
                # try to figure out if we need to use the larger flavor
                # if we at some point can get the number of queueing instances that can be used
                if num_allocated_slots > 0:
                    ramp_up = True
                else:
                    ramp_up = False
                self.logger.debug('do_housekeep(): too few free slots, spawning, ramp_up=%s' % ramp_up)
                new_host = self._spawn_host(cur_ts, ramp_up)
                self.logger.info('do_housekeep(): SPAWNED a new host %s' % new_host['id'])
                hosts.append(new_host)
                return True
            else:
                self.logger.info('do_housekeep(): too few free slots, but host limit reached')

        return False

    def _inactivate_old_hosts(self, hosts, cur_ts):
        active_hosts = self.get_active_hosts(hosts)
        for host in active_hosts:
            if host['lifetime_left'] == 0 and host['num_reserved_slots'] == 0:
                self.logger.info('do_housekeep(): making host %s INACTIVE' % host['id'])
                host['state'] = DD_STATE_INACTIVE
                return True
            if host.get('error_count') > DD_MAX_HOST_ERRORS:
                self.logger.info('do_housekeep(): too many errors, making host %s inactive' % host['id'])
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
            # if the host is the only one and not smaller flavor, don't leave it waiting
            elif len(hosts) == 1 and host['num_slots'] != self.driver_config['DD_HOST_FLAVOR_SLOTS_SMALL']:
                host['lifetime_tick_ts'] = cur_ts
                lifetime = DD_HOST_LIFETIME
            # host has not been used
            else:
                lifetime = DD_HOST_LIFETIME

            host['lifetime_left'] = lifetime
            self.logger.debug('do_housekeep(): host %s has lifetime %d' % (host['id'], lifetime))

    def _select_hosts(self, slots, token, cur_ts):
        """ Select pool vm host for provisioning a container.
            First, oldest active hosts and then the fresh hosts
        """
        hosts = self._get_hosts(token, cur_ts)
        active_hosts = self.get_active_hosts(hosts)

        # first try to use the oldest active host with space and lifetime left
        active_hosts = sorted(active_hosts, key=lambda entry: entry['spawn_ts'])
        selected_hosts = []
        for host in active_hosts:
            is_fresh = host['lifetime_left'] > DD_HOST_LIFETIME_LOW
            has_enough_slots = host['num_slots'] - host['num_reserved_slots'] >= slots
            if is_fresh and has_enough_slots:
                selected_hosts.append(host)
        if len(selected_hosts) == 0:
            # try to use any active host with space
            for host in active_hosts:
                if host['num_slots'] - host['num_reserved_slots'] >= slots:
                    selected_hosts.append(host)

        if len(selected_hosts) == 0:
            self.logger.debug('_select_host(): no space left, %d slots requested,'
                              ' active hosts: %s' % (slots, active_hosts))
            raise RuntimeWarning('_select_host(): no space left for requested %d slots' % slots)

        self.logger.debug("_select_host(): %d total active, %d available" % (len(active_hosts),
                                                                             len(selected_hosts)))
        return selected_hosts

    def _get_hosts(self, token, cur_ts):
        """ Loads the state of the pool vm host through access proxy
        """
        ap = self._get_ap()

        hosts = ap.load_records(token, self.config['INTERNAL_API_BASE_URL'])
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

            except (ConnectionError, ReadTimeout):
                self.logger.warning('_get_hosts(): updating number of instances failed for %s' % host['id'])
                host['error_count'] = host.get('error_count', 0) + 1

        return hosts

    def _save_host_state(self, hosts, token, cur_ts):
        """Saves the state of the pool vm host in the database via access proxy
        """
        ap = self._get_ap()
        ap.save_records(token, self.config['INTERNAL_API_BASE_URL'], hosts)

    def _spawn_host(self, cur_ts, ramp_up=False):
        instance_name = 'pb_dd_%s' % uuid.uuid4().hex
        image_name = self.driver_config['DD_HOST_IMAGE']

        if ramp_up:
            flavor_name = self.driver_config['DD_HOST_FLAVOR_NAME_LARGE']
            flavor_slots = self.driver_config['DD_HOST_FLAVOR_SLOTS_LARGE']
        else:
            flavor_name = self.driver_config['DD_HOST_FLAVOR_NAME_SMALL']
            flavor_slots = self.driver_config['DD_HOST_FLAVOR_SLOTS_SMALL']

        oss = self._get_ap().get_openstack_service({
            'M2M_CREDENTIAL_STORE': self.config['M2M_CREDENTIAL_STORE']
        })

        # run actual provisioning
        res = oss.provision_instance(
            display_name=instance_name,
            image_name=image_name,
            flavor_name=flavor_name,
            public_key=open('/home/pebbles/.ssh/id_rsa.pub').read(),
            master_sg_name=self.driver_config['DD_HOST_MASTER_SG'],
            extra_sec_groups=[x.strip() for x in self.driver_config['DD_HOST_EXTRA_SGS'].split()],
            allocate_public_ip=False,
            root_volume_size=self.driver_config['DD_HOST_ROOT_VOLUME_SIZE'],
            data_volume_size=flavor_slots * self.driver_config['DD_HOST_DATA_VOLUME_FACTOR'],
            data_volume_type=self.driver_config['DD_HOST_DATA_VOLUME_TYPE'],
            nics=self.driver_config.get('DD_HOST_NETWORK', 'auto'),
        )
        if 'error' in res.keys():
            raise RuntimeError('Failed to spawn a new host: %s' % res['error'])

        self.logger.debug("_spawn_host_os_service: spawned %s" % res)
        private_ip = res['address_data']['private_ip']
        public_ip = res['address_data']['public_ip']
        return {
            'id': instance_name,
            'provider_id': res['server_id'],
            'docker_url': 'https://%s:2376' % private_ip,
            'public_ip': public_ip,
            'private_ip': private_ip,
            'spawn_ts': cur_ts,
            'state': DD_STATE_SPAWNED,
            'num_reserved_slots': 0,
            'num_slots': flavor_slots,
            'error_count': 0,
        }

    def _prepare_host(self, host):
        ap = self._get_ap()

        ap.run_ansible_on_host(host, self.logger, self.driver_config)

        docker_client = ap.get_docker_client(host['docker_url'])

        dconf = self.get_configuration()

        for image_name in dconf['schema']['properties']['docker_image']['enum']:
            filename = '%s/%s.img' % (DD_IMAGE_DIRECTORY, image_name.replace('/', '.'))
            self.logger.debug("_prepare_host(): uploading image %s from file %s" % (image_name, filename))
            with open(filename, 'r') as img_file:
                docker_client.load_image(img_file)

    def _remove_host(self, host):
        self.logger.debug("_remove_host()")
        oss = self._get_ap().get_openstack_service({
            'M2M_CREDENTIAL_STORE': self.config['M2M_CREDENTIAL_STORE']
        })
        res = oss.deprovision_instance(host['provider_id'], delete_attached_volumes=True)
        if 'error' in res.keys():
            raise RuntimeError('Failed to remove host %s: %s' % (host['id'], res['error']))
