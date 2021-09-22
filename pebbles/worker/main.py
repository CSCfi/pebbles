import logging
import os
import signal
from random import randrange
from time import sleep

from pebbles.client import PBClient
from pebbles.config import BaseConfig
from pebbles.utils import init_logging, load_cluster_config
from pebbles.worker.controllers import EnvironmentSessionController, ClusterController


class Worker:

    def __init__(self, conf):
        self.config = conf
        self.api_key = conf['SECRET_KEY']
        self.api_base_url = conf['INTERNAL_API_BASE_URL']
        self.client = PBClient(None, self.api_base_url)
        self.client.login('worker@pebbles', self.api_key)
        self.id = os.environ['WORKER_ID'] if 'WORKER_ID' in os.environ.keys() else 'worker-%s' % randrange(100, 2 ** 32)
        self.terminate = False
        # wire our handler to
        # - SIGTERM for controlled pod shutdowns by K8s
        # - SIGALRM for emergency shutdown by watchdog
        signal.signal(signal.SIGTERM, self.handle_signals)
        signal.signal(signal.SIGALRM, self.handle_signals)

        self.clusters = {}
        self.cluster_config = load_cluster_config(
            cluster_config_file=self.config['CLUSTER_CONFIG_FILE'],
            cluster_passwords_file=self.config['CLUSTER_PASSWORDS_FILE']
        )
        self.environment_session_controller = EnvironmentSessionController()
        self.environment_session_controller.initialize(self.id, self.config, self.cluster_config, self.client)
        self.cluster_controller = ClusterController()
        self.cluster_controller.initialize(self.id, self.config, self.cluster_config, self.client)

    def handle_signals(self, signum, frame):
        """
        Callback function for graceful and emergency shutdown.
        """
        logging.info('got signal %s frame %s' % (signum, frame))

        # Here we handle signal SIGTERM, sent by Kubernetes when pod is being terminated,
        # to break out of main loop as soon as work has finished
        if signum == signal.SIGTERM:
            logging.info('stopping worker')
            self.terminate = True
        # handle emergency shutdown by watchdog timer in case worker has been stuck
        if signum == signal.SIGALRM:
            logging.info('terminating worker')
            exit(signum)

    def run(self):
        logging.info('worker "%s" starting' % self.id)

        # TODO:
        # - housekeeping

        # check if we are being terminated and drop out of the loop
        while not self.terminate:
            logging.debug('worker main loop')
            # set watchdog timer
            signal.alarm(60 * 5)

            # make sure we have a fresh session
            self.client.check_and_refresh_session('worker@pebbles', self.api_key)

            # process environment sessions
            self.environment_session_controller.process()

            # process clusters
            self.cluster_controller.process()

            # stop the watchdog
            signal.alarm(0)

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
