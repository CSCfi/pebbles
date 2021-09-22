import time

from pebbles.client import PBClient
from pebbles.drivers.provisioning import base_driver


class DummyDriver(base_driver.ProvisioningDriverBase):
    """ Dummy driver mostly pretends to be a real driver for system testing
    and development purposes.
    """

    def is_expired(self):
        return False

    @staticmethod
    def get_configuration():
        from pebbles.drivers.provisioning.dummy_driver_config import CONFIG

        return CONFIG

    def do_get_running_logs(self, token, environment_session_id):
        running_log_uploader = self.create_prov_log_uploader(token, environment_session_id, log_type='running')
        running_log_uploader.info('dummy running logs')

    def do_provision(self, token, environment_session_id):
        pbclient = PBClient(token, self.config['INTERNAL_API_BASE_URL'], ssl_verify=False)

        log_uploader = self.create_prov_log_uploader(token, environment_session_id, log_type='provisioning')

        self.logger.info('faking provisioning')
        log_uploader.info('dummy provisioning for 5 seconds\n')
        time.sleep(5)
        log_uploader.info('dummy provisioning completed\n')

        pbclient.do_environment_session_patch(environment_session_id, {'dummy': 'yummy'})

    def do_check_readiness(self, token, environment_session_id):
        # we already 'provision' synchronously, so nothing to do here
        pass

    def do_deprovision(self, token, environment_session_id):
        log_uploader = self.create_prov_log_uploader(token, environment_session_id, log_type='deprovisioning')

        self.logger.info('faking deprovisioning\n')
        log_uploader.info('dummy deprovisioning for 5 seconds\n')
        time.sleep(5)
        log_uploader.info('dummy deprovisioning completed\n')

    def do_housekeep(self, token):
        pass
