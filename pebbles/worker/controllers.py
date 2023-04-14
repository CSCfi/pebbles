import logging
import os
import time
import traceback
from random import randrange

import requests

from pebbles.models import ApplicationSession, Task
from pebbles.utils import find_driver_class

DRIVER_CACHE_LIFETIME = 900


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
        """Create driver instance for given cluster.
        We cache the driver instances to avoid login for every new request"""
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
            if driver_instance.create_ts + DRIVER_CACHE_LIFETIME > time.time() and not driver_instance.is_expired():
                return driver_instance

        # create the driver by finding out the class and creating an instance
        driver_class = find_driver_class(cluster.get('driver'))
        if not driver_class:
            raise RuntimeWarning('No matching driver %s found for %s' % (cluster.get('driver'), cluster_name))

        # create an instance, test the connection and populate the cache
        driver_instance = driver_class(logging.getLogger(), self.config, cluster, self.client.token)
        driver_instance.connect()
        cluster['driver_instance'] = driver_instance

        return driver_instance


class ApplicationSessionController(ControllerBase):
    """
    Controller that takes care of application sessions
    """

    def update_application_session(self, application_session):
        logging.debug('updating %s' % application_session)
        application_session_id = application_session['id']
        cluster_name = application_session['provisioning_config']['cluster']
        if cluster_name is None:
            logging.warning(
                'Cluster/driver config for the application session %s is not found',
                application_session.get('name')
            )

        driver_application_session = self.get_driver(cluster_name)
        driver_application_session.test_connection()
        driver_application_session.update(self.client.token, application_session_id)

    def process_application_session(self, application_session):
        # check if we need to deprovision the application session
        if application_session.get('state') in [ApplicationSession.STATE_RUNNING]:
            if not application_session.get('lifetime_left') and application_session.get('maximum_lifetime'):
                logging.info(
                    'deprovisioning triggered for %s (reason: maximum lifetime exceeded)',
                    application_session.get('id')
                )
                self.client.do_application_session_patch(
                    application_session['id'], json_data={'to_be_deleted': True})

        self.update_application_session(application_session)

    def process(self):
        # we query all non-deleted application sessions
        sessions = self.client.get_application_sessions()

        # extract sessions that need to be processed
        # waiting to be provisioned
        queueing_sessions = filter(lambda x: x['state'] == ApplicationSession.STATE_QUEUEING, sessions)
        # starting asynchronously
        starting_sessions = filter(lambda x: x['state'] == ApplicationSession.STATE_STARTING, sessions)
        # log fetching needed
        log_fetch_application_sessions = filter(
            lambda x: x['state'] == ApplicationSession.STATE_RUNNING and x['log_fetch_pending'], sessions)
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
        processed_sessions.extend(log_fetch_application_sessions)

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
                    self.process_application_session(session)
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
        super().__init__()
        self.next_check_ts = 0

    def process(self):
        # process clusters in increased intervals
        if time.time() < self.next_check_ts:
            return
        self.next_check_ts = time.time() + randrange(30, 90)

        logging.debug('checking cluster alerts')

        for cluster in self.cluster_config['clusters']:
            cluster_name = cluster['name']

            if 'appDomain' not in cluster.keys():
                continue

            if cluster.get('disableAlerts', False):
                logging.debug('alerts disabled for cluster %s', cluster_name)
                continue

            try:
                logging.debug('getting alerts for cluster %s', cluster_name)
                res = requests.get(
                    url="https://" + cluster['appDomain'] + "/prometheus/api/v1/alerts",
                    auth=('token', cluster.get('monitoringToken')),
                    timeout=5
                )
            except requests.exceptions.RequestException:
                res = None

            if not (res and res.ok):
                logging.warning('unable to get alerts from cluster %s', cluster_name)
                continue

            alert_data = res.json()
            alerts = alert_data['data']['alerts']

            logging.debug('got %d alert entries for cluster %s', len(alert_data), cluster_name)

            # the watchdog alert should be always firing
            if len(alerts) == 0:
                logging.warning('zero alerts, watchdog is not working for cluster %s', cluster_name)
                continue

            # filter out low severity ('none', 'info') and speculative alerts (state not 'firing')
            real_alerts = list(filter(
                lambda x: x['labels'].get('severity', 'none') not in ('none', 'info') and x['state'] == 'firing',
                alerts
            ))

            if 'ALERTNAMES_TO_IGNORE' in os.environ:
                alertnames_to_ignore = os.environ.get('ALERTNAMES_TO_IGNORE').split(',')
                real_alerts = list(filter(
                    lambda x: x['labels']['alertname'] not in alertnames_to_ignore,
                    real_alerts
                ))

            if len(real_alerts) > 0:
                json_data = []
                logging.info('found %d alerts for cluster %s', len(real_alerts), cluster_name)

                # add real alerts to post data
                for alert in real_alerts:
                    json_data.append(
                        dict(
                            target=cluster_name,
                            source='prometheus',
                            status='firing',
                            data=alert
                        )
                    )

                # add notification that the cluster has been polled successfully
                json_data.append(
                    dict(
                        target=cluster_name,
                        source='prometheus',
                        status='ok',
                        data=dict()
                    )
                )
                res = self.client.do_post(
                    object_url='alerts',
                    json_data=json_data
                )
            else:
                # inform API that cluster is ok and archive any firing alerts
                res = self.client.do_post(
                    object_url='alert_reset/%s/%s' % (cluster_name, 'prometheus'),
                    json_data=None)

            if not res.ok:
                logging.warning('unable to update alerts in api, code/reason: %s/%s', res.status_code, res.reason)


class WorkspaceController(ControllerBase):
    """
    Controller that takes care of Workspace tasks
    """

    def __init__(self):
        super().__init__()
        self.max_concurrent_tasks = 1
        self.next_check_ts = 0

    def process(self):
        # process workspace management in increased intervals
        if time.time() < self.next_check_ts:
            return
        self.next_check_ts = time.time() + randrange(30, 90)

        logging.debug('WorkspaceController: checking tasks')
        tasks = self.client.get_tasks(unfinished=1)
        logging.debug('got tasks: %s', tasks)

        # Wait until all tasks currently in PROCESSING have completed before taking new tasks
        tasks_in_processing = [t for t in tasks if t.get('state') == Task.STATE_PROCESSING]
        if tasks_in_processing:
            tasks = tasks_in_processing
            logging.debug('processing existing %d tasks, no new tasks taken this time', len(tasks))
        else:
            # Taking new tasks, limit concurrency
            tasks = tasks[:self.max_concurrent_tasks]

        for task in tasks:
            # try to obtain a lock. Should we lose the race, the winner takes it, and we move on
            lock = self.client.obtain_lock(task.get('id'), self.worker_id)
            if lock is None:
                continue

            # process tasks and release the lock
            try:
                if task.get('kind') == Task.KIND_WORKSPACE_BACKUP:
                    self.process_backup_task(task)
                elif task.get('kind') == Task.KIND_WORKSPACE_RESTORE:
                    self.process_restore_task(task)
                else:
                    logging.warning('unknown task kind: %s' % task.kind)
            except Exception as e:
                logging.debug(traceback.format_exc().splitlines()[-5:])
                logging.warning('Marking task %s FAILED due to "%s"', task.get('id'), e)
                self.client.update_task(task.get('id'), state=Task.STATE_FAILED)
            finally:
                self.client.release_lock(task.get('id'), self.worker_id)

    def process_backup_task(self, task):
        driver = self.get_driver(task.get('data').get('cluster'))
        if not driver:
            raise RuntimeError(
                'No driver for cluster %s in task %s' % (task.get('data').get('cluster'), task.get('id')))
        if task.get('state') == Task.STATE_NEW:
            logging.info('Starting processing of task %s', task.get('id'))
            self.client.update_task(task.get('id'), state=Task.STATE_PROCESSING)
            driver.create_workspace_backup_jobs(self.client.token, task.get('data').get('workspace_id'))
        elif task.get('state') == Task.STATE_PROCESSING:
            if driver.check_workspace_backup_jobs(self.client.token, task.get('data').get('workspace_id')):
                logging.info('Task %s FINISHED', task.get('id'))
                self.client.update_task(task.get('id'), state=Task.STATE_FINISHED)
        else:
            logging.warning(
                'task %s in state %s should not end up in processing', task.get('id'), task.get('state'))

    def process_restore_task(self, task):
        driver = self.get_driver(task.get('data').get('tgt_cluster'))
        if not driver:
            raise RuntimeError(
                'No driver for tgt_cluster %s in task %s' % (task.get('data').get('tgt_cluster'), task.get('id')))
        ws_id = task.get('data').get('workspace_id')
        if not ws_id:
            raise RuntimeError('No data.workspace_id in task %s' % task.get('id'))
        src_cluster = task.get('data').get('src_cluster')
        if not src_cluster:
            raise RuntimeError('No data.src_cluster in task %s' % task.get('id'))

        if task.get('state') == Task.STATE_NEW:
            logging.info('Starting processing of task %s', task.get('id'))
            self.client.update_task(task.get('id'), state=Task.STATE_PROCESSING)

            # list current users of the workspace to create a list of restorable volumes
            wuas = self.client.get_workspace_user_associations(ws_id)
            pseudonyms = []
            for wua in wuas:
                user = self.client.get_user(wua['user_id'])
                pseudonyms.append(user['pseudonym'])

            # figure out right size for user work volume
            ws = self.client.get_workspace(ws_id)
            user_work_volume_size_gib = ws.get('config', {}).get('user_work_folder_size_gib', 1)

            driver.create_workspace_restore_jobs(
                self.client.token,
                ws_id,
                pseudonyms,
                user_work_volume_size_gib,
                src_cluster,
            )
        elif task.get('state') == Task.STATE_PROCESSING:
            if driver.check_workspace_restore_jobs(self.client.token, ws_id):
                logging.info('Task %s FINISHED', task.get('id'))
                self.client.update_task(task.get('id'), state=Task.STATE_FINISHED)
        else:
            logging.warning(
                'task %s in state %s should not end up in processing', task.get('id'), task.get('state'))
