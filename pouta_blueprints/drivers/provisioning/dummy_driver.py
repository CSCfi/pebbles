import json
from random import randint

import os

from pouta_blueprints.drivers.provisioning import base_driver
from pouta_blueprints.client import PBClient


class DummyDriver(base_driver.ProvisioningDriverBase):
    def get_configuration(self):
        from pouta_blueprints.drivers.provisioning.dummy_driver_config import CONFIG

        return CONFIG

    def do_update_connectivity(self, token, instance_id):
        pass

    def do_provision(self, token, instance_id):
        pbclient = PBClient(token, self.config['INTERNAL_API_BASE_URL'], ssl_verify=False)

        instance = pbclient.get_instance_description(instance_id)
        cluster_name = instance['name']

        instance_dir = '%s/%s' % (self.config['INSTANCE_DATA_DIR'], cluster_name)

        # will fail if there is already a directory for this instance
        os.makedirs(instance_dir)

        # fetch config for this cluster
        # config = self.get_blueprint_description(token, instance['blueprint_id'])

        # fetch user public key and save it
        key_data = pbclient.get_user_key_data(instance['user']['id']).json()
        user_key_file = '%s/userkey.pub' % instance_dir
        if not key_data:
            error_body = {'state': 'failed', 'error_msg': 'user\'s public key is missing'}
            pbclient.do_instance_patch(instance_id, error_body)
            raise RuntimeError("User's public key missing")

        with open(user_key_file, 'w') as kf:
            kf.write(key_data[0]['public_key'])

        uploader = self.create_prov_log_uploader(token, instance_id, log_type='provisioning')

        self.logger.info('faking provisioning')
        cmd = 'time ping -c 10 localhost'
        self.run_logged_process(cmd=cmd, cwd=instance_dir, shell=True, log_uploader=uploader)
        public_ip = '%s.%s.%s.%s' % (randint(1, 254), randint(1, 254), randint(1, 254), randint(1, 254))
        instance_data = {
            'endpoints': [
                {'name': 'SSH', 'access': 'ssh cloud-user@%s' % public_ip},
                {'name': 'Some Web Interface', 'access': 'http://%s/service-x' % public_ip},
            ]
        }
        pbclient.do_instance_patch(
            instance_id,
            {
                'public_ip': public_ip, 'instance_data': json.dumps(instance_data)
            }
        )

    def do_deprovision(self, token, instance_id):
        pbclient = PBClient(token, self.config['INTERNAL_API_BASE_URL'], ssl_verify=False)

        instance = pbclient.get_instance_description(instance_id)
        cluster_name = instance['name']

        instance_dir = '%s/%s' % (self.config['INSTANCE_DATA_DIR'], cluster_name)

        uploader = self.create_prov_log_uploader(token, instance_id, log_type='deprovisioning')

        self.logger.info('faking deprovisioning')
        cmd = 'time ping -c 5 localhost'
        self.run_logged_process(cmd=cmd, cwd=instance_dir, shell=True, log_uploader=uploader)

        # use instance id as a part of the name to make tombstones always unique
        os.rename(instance_dir, '%s.deleted.%s' % (instance_dir, instance_id))
