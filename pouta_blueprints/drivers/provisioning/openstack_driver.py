import time
import json

from pouta_blueprints.services.openstack_service import OpenStackService
from pouta_blueprints.drivers.provisioning import base_driver
from pouta_blueprints.client import PBClient
from pouta_blueprints.models import Instance

SLEEP_BETWEEN_POLLS = 3
POLL_MAX_WAIT = 180


class OpenStackDriver(base_driver.ProvisioningDriverBase):
    def get_configuration(self):
        from pouta_blueprints.drivers.provisioning.openstack_driver_config import CONFIG
        oss = OpenStackService({'M2M_CREDENTIAL_STORE': self.config['M2M_CREDENTIAL_STORE']})

        images = [x.name for x in oss.list_images()]
        flavors = [x.name for x in oss.list_flavors()]

        config = CONFIG.copy()
        config['schema']['properties']['image']['enum'] = images
        config['schema']['properties']['flavor']['enum'] = flavors

        return config

    def do_update_connectivity(self, token, instance_id):
        oss = OpenStackService({'M2M_CREDENTIAL_STORE': self.config['M2M_CREDENTIAL_STORE']})
        pbclient = PBClient(token, self.config['INTERNAL_API_BASE_URL'], ssl_verify=False)
        instance = pbclient.get_instance_description(instance_id)
        instance_data = instance['instance_data']
        server_id = instance_data['server_id']
        security_group_id = instance_data['security_group_id']

        nc = self.get_openstack_nova_client()
        nc.servers.get(server_id)
        sg = nc.security_groups.get(security_group_id)

        # As currently only single firewall rule can be added by the user,
        # first delete all existing rules and add the new one
        oss.clear_security_group_rules(sg.id)
        oss.create_security_group_rule(
            sg.id,
            ip_protocol='tcp',
            from_port=22,
            to_port=22,
            cidr="%s/32" % instance['client_ip'],
            group_id=None
        )

    def do_provision(self, token, instance_id):
        self.logger.debug("do_provision %s" % instance_id)

        prefix = self.config['INSTANCE_NAME_PREFIX']

        pbclient = PBClient(token, self.config['INTERNAL_API_BASE_URL'], ssl_verify=False)
        instance = pbclient.get_instance_description(instance_id)

        instance_name = instance['name']
        instance_user = instance['user_id']

        # fetch config
        blueprint_config = pbclient.get_blueprint_description(instance['blueprint_id'])
        config = blueprint_config['config']

        log_uploader = self.create_prov_log_uploader(token, instance_id, log_type='provisioning')
        log_uploader.info("Provisioning OpenStack instance (%s)\n" % instance_id)

        # fetch user public key
        key_data = pbclient.get_user_key_data(instance_user).json()
        if not key_data:
            error = 'user\'s public key is missing'
            error_body = {'state': Instance.STATE_FAILED, 'error_msg': error}
            pbclient.do_instance_patch(instance_id, error_body)
            self.logger.debug(error)
            raise RuntimeError(error)

        oss = OpenStackService({'M2M_CREDENTIAL_STORE': self.config['M2M_CREDENTIAL_STORE']})

        key_name = '%s%s' % (prefix, instance_user)

        security_group_name = instance_name

        result = oss.provision_instance(
            instance_name,
            config['image'],
            config['flavor'],
            key_name=key_name,
            security_groups=[security_group_name],
            userdata=config.get('userdata'))

        ip = result['ip'].ip
        instance_data = {
            'server_id': result['server'].id,
            'floating_ip': ip,
            'allocated_from_pool': result['ip'].allocated_from_pool,
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
        instance = pbclient.get_instance_description(instance_id)
        instance_data = instance['instance_data']
        server_id = instance_data['server_id']
        nc = self.get_openstack_nova_client()

        log_uploader.info("Destroying server instance . . ")
        try:
            nc.servers.delete(server_id)
        except:
            log_uploader.info("Unable to delete server\n")

        delete_ts = time.time()
        while True:
            try:
                nc.servers.get(server_id)
                log_uploader.info(" . ")
                time.sleep(SLEEP_BETWEEN_POLLS)
            except:
                log_uploader.info("Server instance deleted\n")
                break

            if time.time() - delete_ts > POLL_MAX_WAIT:
                log_uploader.info("Server instance still running, giving up\n")
                break

        if instance_data.get('allocated_from_pool'):
            log_uploader.info("Releasing public IP\n")
            try:
                nc.floating_ips.delete(nc.floating_ips.find(ip=instance_data['floating_ip']).id)
            except:
                log_uploader.info("Unable to release public IP\n")
        else:
            log_uploader.info("Not releasing public IP\n")

        log_uploader.info("Removing security group\n")
        try:
            sg = nc.security_groups.get(server_id)
            nc.security_groups.delete(sg.id)
        except:
            log_uploader.info("Unable to delete security group\n")

        log_uploader.info("Deprovisioning ready\n")

    def do_housekeep(self, token):
        pass
