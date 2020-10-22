import logging
import os
import signal
import traceback
from random import randrange
from time import sleep

from pebbles.client import PBClient
from pebbles.config import BaseConfig
from pebbles.models import Instance
from pebbles.utils import init_logging, load_cluster_config, find_driver_class


class Worker:

    def __init__(self, conf):
        self.config = conf
        self.api_key = conf['SECRET_KEY']
        self.api_base_url = conf['INTERNAL_API_BASE_URL']
        self.client = PBClient(None, self.api_base_url)
        self.client.login('worker@pebbles', self.api_key)
        self.id = os.environ['WORKER_ID'] if 'WORKER_ID' in os.environ.keys() else 'worker-%s' % randrange(100, 2 ** 32)
        self.terminate = False
        # Wire our handler to SIGTERM for controlled pod shutdowns
        signal.signal(signal.SIGTERM, self.handle_signals)

        self.clusters = {}
        self.cluster_config = load_cluster_config()

    def handle_signals(self, signum, frame):
        """
        Callback function for graceful shutdown. Here we handle signal SIGTERM, sent by Kubernetes when
        pod is being terminated, to break out of main loop as soon as work has finished
        """
        logging.info('got signal %s frame %s, terminating worker' % (signum, frame))
        self.terminate = True

    def get_driver(self, cluster_name):
        """create driver instance for given cluster"""
        cluster = None
        for c in self.cluster_config['clusters']:
            if c.get('name') == cluster_name:
                cluster = c
                break
        if cluster is None:
            raise RuntimeWarning('No matching cluster in configuration for %s' % cluster_name)

        # check cache
        if 'driver_instance' in cluster.keys():
            # we found an existing instance, use that if it is still valid
            driver_instance = cluster.get('driver_instance')
            if not driver_instance.is_expired():
                return driver_instance

        # create the driver by finding out the class and creating an instance
        driver_class = find_driver_class(cluster.get('driver'))
        if not driver_class:
            raise RuntimeWarning('No matching driver %s found for %s' % (cluster.get('driver'), cluster_name))

        # create and instance and populate the cache
        driver_instance = driver_class(logging.getLogger(), self.config, cluster)
        cluster['driver_instance'] = driver_instance

        return driver_instance

    def update_instance(self, instance):
        logging.debug('updating %s' % instance)
        instance_id = instance['id']
        environment = self.client.get_instance_environment(instance_id)
        cluster_name = environment.get('cluster')
        if cluster_name is None:
            logging.warning('Cluster/driver config for the instance %s is not found' % instance.get('name'))
        driver_instance = self.get_driver(cluster_name)
        driver_instance.update(self.client.token, instance_id)

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

        # check if we are being terminated and drop out of the loop
        while not self.terminate:
            logging.debug('worker main loop')
            self.client.check_and_refresh_session('worker@pebbles', self.api_key)

            # we query all non-deleted instances
            instances = self.client.get_instances()

            # extract instances that are waiting to be provisioned
            queueing_instances = filter(lambda x: x['state'] == Instance.STATE_QUEUEING, instances)
            # extract instances that are starting asynchronously
            starting_instances = filter(lambda x: x['state'] == Instance.STATE_STARTING, instances)
            # extract expired instances
            expired_instances = filter(
                lambda x: x['to_be_deleted'] or (x['lifetime_left'] == 0 and x['maximum_lifetime']),
                instances
            )

            # process expired and queueing instances
            processed_instances = list(queueing_instances) + list(starting_instances) + list(expired_instances)

            if len(processed_instances):
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

                    # process instance and release the lock
                    try:
                        self.process_instance(instance)
                    except Exception as e:
                        logging.warning(e)
                        logging.debug(traceback.format_exc().splitlines()[-5:])
                    finally:
                        self.client.release_lock(instance.get('id'), self.id)

            # sleep for a random amount to avoid synchronization between workers
            # while waiting, check for termination flag every second
            for i in range(randrange(2, 5)):
                if self.terminate:
                    break
                sleep(1)


if __name__ == '__main__':

    if 'REMOTE_DEBUG_SERVER' in os.environ:
        print('trying to connect to remote debug server at %s' % os.environ['REMOTE_DEBUG_SERVER'])
        import pydevd_pycharm

        pydevd_pycharm.settrace(os.environ['REMOTE_DEBUG_SERVER'], port=12345, stdoutToServer=True, stderrToServer=True,
                                suspend=False)
        print('Worker: connected to remote debug server at %s' % os.environ['REMOTE_DEBUG_SERVER'])

    config = BaseConfig()

    init_logging(config, 'worker')

    worker = Worker(config)
    logging.getLogger().name = worker.id

    try:
        worker.run()
    except Exception as e:
        logging.critical('worker exiting due to an error', exc_info=e)

    logging.info('worker shutting down')
