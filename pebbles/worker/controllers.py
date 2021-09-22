import logging
import time
import traceback

import requests

from pebbles.models import EnvironmentSession
from pebbles.utils import find_driver_class


class ControllerBase:
    def __init__(self):
        self.worker_id = None
        self.config = None
        self.cluster_config = None
        self.client = None

    def initialize(self, worker_id, config, cluster_config, client):
        self.worker_id = worker_id
        self.config = config
        self.cluster_config = cluster_config
        self.client = client

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

        # create an instance and populate the cache
        driver_instance = driver_class(logging.getLogger(), self.config, cluster)
        cluster['driver_instance'] = driver_instance

        return driver_instance


class EnvironmentSessionController(ControllerBase):
    """
    Controller that takes care of environment sessions
    """

    def update_environment_session(self, environment_session):
        logging.debug('updating %s' % environment_session)
        environment_session_id = environment_session['id']
        cluster_name = environment_session['provisioning_config']['cluster']
        if cluster_name is None:
            logging.warning('Cluster/driver config for the environment session %s is not found' % environment_session.get('name'))

        driver_environment_session = self.get_driver(cluster_name)
        driver_environment_session.update(self.client.token, environment_session_id)

    def process_environment_session(self, environment_session):
        # check if we need to deprovision the environment session
        if environment_session.get('state') in [EnvironmentSession.STATE_RUNNING]:
            if not environment_session.get('lifetime_left') and environment_session.get('maximum_lifetime'):
                logging.info(
                    'deprovisioning triggered for %s (reason: maximum lifetime exceeded)' % environment_session.get('id'))
                self.client.do_environment_session_patch(environment_session['id'], {'to_be_deleted': True})

        self.update_environment_session(environment_session)

    def process(self):
        # we query all non-deleted environment sessions
        sessions = self.client.get_environment_sessions()

        # extract sessions that need to be processed
        # waiting to be provisioned
        queueing_sessions = filter(lambda x: x['state'] == EnvironmentSession.STATE_QUEUEING, sessions)
        # starting asynchronously
        starting_sessions = filter(lambda x: x['state'] == EnvironmentSession.STATE_STARTING, sessions)
        # log fetching needed
        log_fetch_environment_sessions = filter(
            lambda x: x['state'] == EnvironmentSession.STATE_RUNNING and x['log_fetch_pending'], sessions)
        # expired sessions in need of deprovisioning
        expired_sessions = filter(
            lambda x: x['to_be_deleted'] or (x['lifetime_left'] == 0 and x['maximum_lifetime']),
            sessions
        )

        # process sessions that need action
        processed_sessions = []
        processed_sessions.extend(queueing_sessions)
        processed_sessions.extend(starting_sessions)
        processed_sessions.extend(expired_sessions)
        processed_sessions.extend(log_fetch_environment_sessions)

        if len(processed_sessions):
            # get locks for sessions that are already being processed by another worker
            locks = self.client.query_locks()
            locked_session_ids = [lock['id'] for lock in locks]

            # delete leftover locks that we own
            for lock in locks:
                if lock['owner'] == self.worker_id:
                    self.client.release_lock(lock['id'], self.worker_id)

            for session in processed_sessions:
                # skip the ones that are already in progress
                if session['id'] in locked_session_ids:
                    continue

                # try to obtain a lock. Should we lose the race, the winner takes it and we move on
                lock = self.client.obtain_lock(session.get('id'), self.worker_id)
                if lock is None:
                    continue

                # process session and release the lock
                try:
                    self.process_environment_session(session)
                except Exception as e:
                    logging.warning(e)
                    logging.debug(traceback.format_exc().splitlines()[-5:])
                finally:
                    self.client.release_lock(session.get('id'), self.worker_id)


class ClusterController(ControllerBase):
    """
    Controller that takes care of cluster resources
    The only task at the moment is to fetch and publish alerts.
    """

    def __init__(self):
        self.last_check_ts = 0

    def process(self):
        if time.time() - self.last_check_ts < 60:
            return
        self.last_check_ts = time.time()

        logging.debug('checking cluster alerts')

        for cluster in self.cluster_config['clusters']:
            cluster_name = cluster['name']

            if 'appDomain' not in cluster.keys():
                continue

            if cluster.get('disableAlerts', False):
                logging.debug('alerts disabled for cluster %s ' % cluster_name)
                continue

            logging.debug(cluster)
            res = requests.get(
                url="https://" + cluster['appDomain'] + "/prometheus/api/v1/alerts",
                auth=('token', 'pebbles!selddeq')
            )
            if not res.ok:
                logging.warning('unable to get alerts from cluster %s' % cluster_name)
                continue

            alert_data = res.json()
            alerts = alert_data['data']['alerts']

            # the watchdog alert should be always firing
            if len(alerts) == 0:
                logging.warning('zero alerts, watchdog is not working for cluster %s' % cluster_name)
                continue

            real_alerts = list(filter(lambda x: x['labels']['severity'] != 'none', alerts))

            if len(real_alerts) > 0:
                logging.info('found %d alerts for cluster %s' % (len(real_alerts), cluster_name))

            res = self.client.do_post(
                object_url='alerts',
                json_data=dict(
                    target=cluster_name,
                    source='prometheus',
                    status='firing' if len(real_alerts) else 'ok',
                    data=real_alerts
                ))
            if not res.ok:
                logging.warning('unable to update alerts in api, code/reason: %s/%s' % (res.status_code, res.reason))
