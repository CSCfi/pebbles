import logging
import os
from random import randrange
from time import sleep

from pebbles.client import PBClient
from pebbles.config import BaseConfig
from pebbles.drivers.provisioning.dummy_driver import DummyDriver
from pebbles.drivers.provisioning.kubernetes_local_driver import KubernetesLocalDriver
from pebbles.models import Instance


class Worker:

    def __init__(self, conf):
        self.config = conf
        self.api_key = conf['SECRET_KEY']
        self.api_base_url = conf['INTERNAL_API_BASE_URL']
        self.client = PBClient(None, self.api_base_url)
        self.client.login('worker@pebbles', self.api_key)
        self.id = os.environ['WORKER_ID'] if 'WORKER_ID' in os.environ.keys() else 'worker-%s' % randrange(100, 2 ** 32)

    def update_instance(self, instance):
        logging.info('updating %s' % instance)
        instance_id = instance['id']
        blueprint = self.client.get_instance_parent_data(instance_id)
        plugin_id = blueprint['plugin']
        plugin_name = self.client.get_plugin_data(plugin_id)['name']

        if plugin_name == 'DummyDriver':
            dd = DummyDriver(logging.getLogger(), self.config)
            dd.update(self.client.token, instance_id)

        if plugin_name == 'KubernetesLocalDriver':
            kd = KubernetesLocalDriver(logging.getLogger(), self.config)
            kd.update(self.client.token, instance_id)

    def process_instance(self, instance):
        # check if we need to deprovision the instance
        if instance.get('state') in [Instance.STATE_RUNNING]:
            if not instance.get('lifetime_left') and instance.get('maximum_lifetime'):
                logging.info(
                    'deprovisioning triggered for %s (reason: maximum lifetime exceeded)' % instance.get('id'))
                self.client.do_instance_patch(instance['id'], {'to_be_deleted': True})

        self.update_instance(instance)

    def run(self):
        logging.info('worker "%s" starting' % self.id)

        # TODO:
        # - fetch instance logs
        # - housekeeping

        while True:
            logging.info('worker main loop')

            # sleep for a random amount to avoid synchronization between workers
            sleep(randrange(5, 15))

            # we query all non-deleted instances
            instances = self.client.get_instances()

            # extract instances that are waiting to be provisioned
            queueing_instances = filter(lambda x: x['state'] == Instance.STATE_QUEUEING, instances)
            # extract expired instances
            expired_instances = filter(
                lambda x: x['to_be_deleted'] or (x['lifetime_left'] == 0 and x['maximum_lifetime']),
                instances
            )

            # process expired and queueing instances
            processed_instances = list(queueing_instances) + list(expired_instances)

            if not len(processed_instances):
                continue

            # get locks for instances that are already being processed by another worker
            locks = self.client.query_locks()
            locked_instance_ids = [lock['id'] for lock in locks]

            # delete leftover locks that we own
            for lock in locks:
                if lock['owner'] == self.id:
                    self.client.release_lock(lock['id'], self.id)

            for instance in processed_instances:
                # skip the ones that are already in progress
                if instance['id'] in locked_instance_ids:
                    continue

                # try to obtain a lock. Should we lose the race, the winner takes it
                lock = self.client.obtain_lock(instance.get('id'), self.id)
                if lock is None:
                    continue

                # provision and release the lock
                try:
                    self.process_instance(instance)
                except Exception as e:
                    logging.warning(e)
                finally:
                    self.client.release_lock(instance.get('id'), self.id)


if __name__ == '__main__':

    if 'REMOTE_DEBUG_SERVER' in os.environ:
        print('trying to connect to remote debug server at %s ' % os.environ['REMOTE_DEBUG_SERVER'])
        import pydevd_pycharm

        pydevd_pycharm.settrace(os.environ['REMOTE_DEBUG_SERVER'], port=12345, stdoutToServer=True, stderrToServer=True,
                                suspend=False)
        print('connected to remote debug server at %s ' % os.environ['REMOTE_DEBUG_SERVER'])

    config = BaseConfig()
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    worker = Worker(config)
    worker.run()
