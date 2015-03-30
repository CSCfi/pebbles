import time
import os

from novaclient.v2 import client
import novaclient

from pouta_blueprints.drivers.provisioning import base_driver

SLEEP_BETWEEN_POLLS = 3


class OpenStackDriver(base_driver.ProvisioningDriverBase):
    def get_configuration(self):
        from pouta_blueprints.drivers.provisioning.openstack_driver_config import CONFIG

        images = self.run_nova_list('image')
        self.logger.debug('images: %s' % images)

        flavors = self.run_nova_list('flavor')
        self.logger.debug('flavors: %s' % flavors)

        config = CONFIG.copy()
        image_names = [x['Name'] for x in images]
        config['schema']['properties']['image']['enum'] = image_names

        flavor_names = [x['Name'] for x in flavors]
        config['schema']['properties']['flavor']['enum'] = flavor_names

        return config

    def get_openstack_nova_client(self):
        openstack_env = self.create_openstack_env()
        os_username = openstack_env['OS_USERNAME']
        os_password = openstack_env['OS_PASSWORD']
        os_tenant_id = openstack_env['OS_TENANT_ID']
        os_auth_url = openstack_env['OS_AUTH_URL']

        return client.Client(os_username, os_password, os_tenant_id, os_auth_url, service_type="compute")

    def do_update_connectivity(self, token, instance_id):
        instance = self.get_instance_data(token, instance_id)
        instance_data = instance['instance_data']
        instance_name = instance['name']

        client = self.get_openstack_nova_client()
        client.servers.get(instance_data['server_id'])
        sg = client.security_group.find('pb_%s' % instance_name)

        client.security_group_rules.create(
            sg.id,
            ip_protocol='tcp',
            from_port=22,
            to_port=22,
            cidr=instance['client_ip'],
            group_id=None
        )

    def do_provision(self, token, instance_id):
        instance = self.get_instance_data(token, instance_id)
        instance_name = instance['name']
        instance_user = instance['user_id']

        # fetch config for this cluster
        config = self.get_blueprint_description(token, instance['blueprint_id'])

        instance_dir = '%s/%s' % (self.config.INSTANCE_DATA_DIR, instance_name)

        # will fail if there is already a directory for this instance
        os.makedirs(instance_dir)

        # fetch user public key and save it
        key_data = self.get_user_key_data(token, instance_user).json()
        if not key_data:
            error = 'user\'s public key is missing'
            error_body = {'state': 'failed', 'error_msg': error}
            self.do_instance_patch(token, instance_id, error_body)
            self.logger.debug(error)
            raise RuntimeError(error)

        nc = self.get_openstack_nova_client()

        image_name = config['image']
        try:
            image = nc.images.find(name=image_name)
        except novaclient.exceptions.NotFound:
            self.logger.debug('requested image %s not found' % image_name)

        flavor_name = config['flavor']
        try:
            flavor = nc.flavors.find(name=flavor_name)
        except novaclient.exceptions.NotFound:
            self.logger.debug('requested flavor %s not found' % flavor_name)

        key_name = 'pb_%s' % instance_user
        try:
            nc.keypairs.create(key_name, public_key=key_data[0]['public_key'])
        except:
            self.logger.debug('conflict: public key already exists')
            self.logger.debug('conflict: using existing key (pb_%s)' % instance_user)

        security_group_name = "pb_%s" % instance_name
        client.security_groups.create(name=security_group_name)

        server = nc.servers.create(
            'pb_%s' % instance_name,
            image,
            flavor,
            key_name=key_name,
            security_groups=[security_group_name])

        while nc.servers.get(server.id).status is "BUILDING":
            time.sleep(SLEEP_BETWEEN_POLLS)

        ips = nc.floating_ips.findall(instance_id=None)
        if not ips:
            ip = nc.floating_ips.create(pool="public")
        else:
            ip = ips[0]

        server.add_floating_ip(ip)
        instance_data = {
            'server_id': server.id,
            'floating_ip': ip
        }
        self.do_instance_patch(token, instance_id, {'instance_data': instance_data})
        nc.keypairs.delete(key_name)

    def do_deprovision(self, token, instance_id):
        instance = self.get_instance_data(token, instance_id)
        instance_data = instance['instance_data']
        instance_name = instance['name']
        nc = self.get_openstack_nova_client()
        nc.security_groups.delete("pb_%s" % instance_name)
        nc.floating_ips.delete(instance_data['floating_ip'])
