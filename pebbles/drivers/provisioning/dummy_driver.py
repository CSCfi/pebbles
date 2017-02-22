import json
from random import randint

import os
import time

from pebbles.drivers.provisioning import base_driver
from pebbles.client import PBClient


class DummyDriver(base_driver.ProvisioningDriverBase):
    """ Dummy driver mostly pretends to be a real driver for system testing
    and development purposes.

    It runs a time-consuming process (ping) using run_logged_process, writes the public SSH
    key to the user for the user to a file and logs from the ping to the right places.
    It reports a random IP address.
    """
    def get_configuration(self):
        from pebbles.drivers.provisioning.dummy_driver_config import CONFIG

        return CONFIG

    def do_update_connectivity(self, token, instance_id):
        pass

    def do_provision(self, token, instance_id):
        pbclient = PBClient(token, self.config['INTERNAL_API_BASE_URL'], ssl_verify=False)

        log_uploader = self.create_prov_log_uploader(token, instance_id, log_type='provisioning')

        self.logger.info('faking provisioning')
        log_uploader.info('dummy provisioning for 5 seconds\n')
        time.sleep(5)
        log_uploader.info('dummy provisioning completed\n')

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

        log_uploader = self.create_prov_log_uploader(token, instance_id, log_type='deprovisioning')

        self.logger.info('faking deprovisioning\n')
        log_uploader.info('dummy deprovisioning for 5 seconds\n')
        time.sleep(5)
        log_uploader.info('dummy deprovisioning completed\n')

        # use instance id as a part of the name to make tombstones always unique
        if os.path.isdir(instance_dir):
            os.rename(instance_dir, '%s.deleted.%s' % (instance_dir, instance_id))

    def do_housekeep(self, token):
        pass
