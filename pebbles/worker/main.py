import logging
from time import sleep

from pebbles.client import PBClient
from pebbles.config import BaseConfig
from pebbles.drivers.provisioning.dummy_driver import DummyDriver
from pebbles.models import Instance


class Worker:

    def __init__(self, config):
        self.config = config
        self.api_key = config['SECRET_KEY']
        self.api_base_url = config['INTERNAL_API_BASE_URL']
        self.client = PBClient(None, self.api_base_url)
        self.client.login('worker@pebbles', self.api_key)


    def update_instance(self, instance):
        logging.info('updating %s' % instance)
        instance_id = instance['id']
        blueprint = self.client.get_instance_parent_data(instance_id)
        plugin_id = blueprint['plugin']
        plugin_name = self.client.get_plugin_data(plugin_id)['name']

        if (plugin_name == 'DummyDriver'):
            dd = DummyDriver(logging.getLogger(), self.config)
            dd.update(self.client.token, instance_id)

    def process_instance(self, instance):
         # check if we need to deprovision the instance
        if instance.get('state') in [Instance.STATE_RUNNING]:
            if not instance.get('lifetime_left') and instance.get('maximum_lifetime'):
                logging.info(
                    'deprovisioning triggered for %s (reason: maximum lifetime exceeded)' % instance.get('id'))
                self.client.do_instance_patch(instance['id'], {'to_be_deleted': True})

        self.update_instance(instance)

    def run(self):

        while True:
            logging.info('worker main loop')
            instances = self.client.get_instances()
            for instance in instances:
                self.process_instance(instance)

            sleep(10)


if __name__ == '__main__':
    config = BaseConfig()
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    worker = Worker(config)
    worker.run()
