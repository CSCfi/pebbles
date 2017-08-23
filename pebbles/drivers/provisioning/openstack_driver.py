""" ToDo: document OpenStack driver on user level here.
"""
import json

from pebbles.services.openstack_service import OpenStackService
from pebbles.drivers.provisioning import base_driver
from pebbles.client import PBClient
from pebbles.models import Instance
from pebbles.utils import parse_ports_string

SLEEP_BETWEEN_POLLS = 3
POLL_MAX_WAIT = 180


class OpenStackDriver(base_driver.ProvisioningDriverBase):
    """ ToDo: document Openstack driver on developer/sysadmin level here.
    """
    def get_oss(self):
        return OpenStackService({'M2M_CREDENTIAL_STORE': self.config['M2M_CREDENTIAL_STORE']})

    def get_configuration(self):
        from pebbles.drivers.provisioning.openstack_driver_config import CONFIG
        oss = self.get_oss()

        images = [x.name for x in oss.list_images()]
        flavors = [x.name for x in oss.list_flavors()]

        config = CONFIG.copy()
        config['schema']['properties']['image']['enum'] = images
        config['schema']['properties']['flavor']['enum'] = flavors

        return config

    def get_running_instance_logs(self, token, instance_id):
        running_log_uploader = self.create_prov_log_uploader(token, instance_id, log_type='running')
        running_log_uploader.info('Cannot get running logs. This feature has not been implemented for the OpenStackDriver yet')

    def do_update_connectivity(self, token, instance_id):
        oss = self.get_oss()
        pbclient = PBClient(token, self.config['INTERNAL_API_BASE_URL'], ssl_verify=False)
        instance = pbclient.get_instance_description(instance_id)
        instance_data = instance['instance_data']
        security_group_id = instance_data['security_group_id']

        blueprint_config = pbclient.get_blueprint_description(instance['blueprint_id'])
        config = blueprint_config['full_config']

        # Delete all existing rules and add the rules using the input port string
        oss.clear_security_group_rules(security_group_id)

        ports_str = config['exposed_ports']
        if not ports_str:
            ports_str = '22'  # If the input port string is empty then use 22 as the default port
        ports_list = parse_ports_string(ports_str)

        for ports in ports_list:
            from_port = ports[0]
            to_port = ports[1]

            oss.create_security_group_rule(
                security_group_id,
                from_port=from_port,
                to_port=to_port,
                cidr="%s/32" % instance['client_ip'],
                ip_protocol='tcp',
                group_id=None
            )

    def do_provision(self, token, instance_id):
        self.logger.debug("do_provision %s" % instance_id)

        pbclient = PBClient(token, self.config['INTERNAL_API_BASE_URL'], ssl_verify=False)
        instance = pbclient.get_instance_description(instance_id)

        instance_name = instance['name']
        instance_user = instance['user_id']

        # fetch config
        blueprint_config = pbclient.get_blueprint_description(instance['blueprint_id'])
        config = blueprint_config['full_config']

        log_uploader = self.create_prov_log_uploader(token, instance_id, log_type='provisioning')
        log_uploader.info("Provisioning OpenStack instance (%s)\n" % instance_id)

        ports_str = config['exposed_ports']
        if ports_str:
            try:
                parse_ports_string(ports_str)
            except:
                error = 'Incorrect exposed ports definition in blueprint'
                error_body = {'state': Instance.STATE_FAILED, 'error_msg': error}
                pbclient.do_instance_patch(instance_id, error_body)
                self.logger.debug(error)
                raise RuntimeError(error)

        # fetch user public key
        key_data = pbclient.get_user_key_data(instance_user).json()
        if not key_data:
            error = 'user\'s public key is missing'
            error_body = {'state': Instance.STATE_FAILED, 'error_msg': error}
            pbclient.do_instance_patch(instance_id, error_body)
            self.logger.debug(error)
            raise RuntimeError(error)

        oss = self.get_oss()

        result = oss.provision_instance(
            instance_name,
            config['image'],
            config['flavor'],
            public_key=key_data[0]['public_key'],
            userdata=config.get('userdata'))

        if 'error' in result:
            log_uploader.warn('Provisioning failed %s' % result['error'])
            return

        ip = result['address_data']['public_ip']
        instance_data = {
            'server_id': result['server_id'],
            'floating_ip': ip,
            'allocated_from_pool': result['address_data']['allocated_from_pool'],
            'security_group_id': result['security_group'],
            'endpoints': [
                {'name': 'SSH', 'access': 'ssh cloud-user@%s' % ip},
            ]
        }
        log_uploader.info("Publishing server data\n")
        pbclient.do_instance_patch(
            instance_id,
            {'instance_data': json.dumps(instance_data), 'public_ip': ip})
        log_uploader.info("Provisioning complete\n")

    def do_deprovision(self, token, instance_id):
        log_uploader = self.create_prov_log_uploader(token, instance_id, log_type='deprovisioning')
        log_uploader.info("Deprovisioning instance %s\n" % instance_id)
        pbclient = PBClient(token, self.config['INTERNAL_API_BASE_URL'], ssl_verify=False)
        oss = self.get_oss()
        instance = pbclient.get_instance_description(instance_id)
        instance_data = instance['instance_data']
        if 'server_id' not in instance_data:
            log_uploader.info("Skipping, no server id in instance data")
            return

        server_id = instance_data['server_id']

        log_uploader.info("Destroying server instance . . ")
        oss.deprovision_instance(server_id)
        log_uploader.info("Deprovisioning ready\n")

    def do_housekeep(self, token):
        pass
