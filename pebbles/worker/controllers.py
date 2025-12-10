import logging
import os
import time
import traceback
from random import randrange

import requests

from pebbles.client import PBClient
from pebbles.config import BaseConfig
from pebbles.models import ApplicationSession, Task, CustomImage
from pebbles.utils import find_driver_class
from pebbles.worker.build_client import BuildClient

WS_CONTROLLER_TASK_LOCK_NAME = 'workspace-controller-tasks'

SESSION_CONTROLLER_LIMIT_SIZE = 50

CUSTOM_IMAGE_CONTROLLER_TASK_LOCK_NAME = 'custom-image-controller-tasks'
CUSTOM_IMAGE_CONTROLLER_LIMIT_SIZE = 1

DRIVER_CACHE_LIFETIME = 900


class ControllerBase:
    def __init__(self, worker_id: str, config: BaseConfig, cluster_config: dict, client: PBClient,
                 controller_name: str):
        self.worker_id = worker_id
        self.config = config
        self.cluster_config = cluster_config
        self.client = client
        self.controller_name = controller_name
        self.next_check_ts = 0

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
        cluster['runtime_data'] = self.cluster_config.get('runtime_data', {})

        return driver_instance

    def update_next_check_ts(self, polling_interval_min, polling_interval_max):
        self.next_check_ts = time.time() + randrange(polling_interval_min, polling_interval_max + 1)

    def get_polling_interval(self, default_min, default_max):
        """
        Read the polling interval from worker environment variables, if present. If not present,
        use given controller specific default values.
        """
        polling_interval_min = int(os.getenv(f"{self.controller_name}_POLLING_INTERVAL_SEC_MIN", default_min))
        polling_interval_max = int(os.getenv(f"{self.controller_name}_POLLING_INTERVAL_SEC_MAX", default_max))
        logging.info(f"{self.controller_name}_POLLING_INTERVAL_SEC_MIN is set to {polling_interval_min}")
        logging.info(f"{self.controller_name}_POLLING_INTERVAL_SEC_MAX is set to {polling_interval_max}")
        if polling_interval_min > polling_interval_max:
            logging.warning(f"{self.controller_name}_POLLING_INTERVAL_SEC_MIN is larger than "
                            f"{self.controller_name}_POLLING_INTERVAL_SEC_MAX, using default values instead")
            return default_min, default_max
        return polling_interval_min, polling_interval_max


class ApplicationSessionController(ControllerBase):
    """
    Controller that takes care of application sessions
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.polling_interval_min, self.polling_interval_max = self.get_polling_interval(2, 5)

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
        # process sessions in increased intervals
        if time.time() < self.next_check_ts:
            return
        self.update_next_check_ts(self.polling_interval_min, self.polling_interval_max)

        # Query all non-deleted application sessions. This will be a list of candidates, because other
        # workers could fetch the overlapping sessions as well.
        sessions = self.client.get_application_sessions(limit=SESSION_CONTROLLER_LIMIT_SIZE)
        logging.debug('got %d sessions', len(sessions))

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
                    logging.debug('skipping locked session %s', session['id'])
                    continue

                # try to obtain a lock. Should we lose the race, the winner takes it and we move on
                lock_id = self.client.obtain_lock(session.get('id'), self.worker_id)
                if not lock_id:
                    logging.debug('failed to acquire lock on session %s, skipping', session['id'])
                    continue

                # process session and release the lock
                try:
                    # Now we have the lock, and we can fetch the definite state for the session
                    # If the session has been already deleted by another worker, we'll get None
                    fresh_session = self.client.get_application_session(session.get('id'), suppress_404=True)
                    if fresh_session and fresh_session.get('state') == session.get('state'):
                        self.process_application_session(fresh_session)
                    else:
                        logging.info('session %s already processed by another worker', session.get('name'))
                except Exception as e:
                    logging.warning(e)
                    logging.debug(traceback.format_exc().splitlines()[-5:])
                finally:
                    self.client.release_lock(lock_id, self.worker_id)


class ClusterController(ControllerBase):
    """
    Controller that takes care of cluster resources
    The only task at the moment is to fetch and publish alerts.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.polling_interval_min, self.polling_interval_max = self.get_polling_interval(30, 90)

    def process(self):
        # process clusters in increased intervals
        if time.time() < self.next_check_ts:
            return
        self.update_next_check_ts(self.polling_interval_min, self.polling_interval_max)

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

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.polling_interval_min, self.polling_interval_max = self.get_polling_interval(30, 90)
        self.max_concurrent_tasks = 20

    def process(self):
        # process workspace management in increased intervals
        if time.time() < self.next_check_ts:
            return
        self.update_next_check_ts(self.polling_interval_min, self.polling_interval_max)

        # Try to obtain a global lock for WorkspaceTaskProcessing.
        # Should we lose the race, the winner takes it, and we try next time we are active
        lock = self.client.obtain_lock(WS_CONTROLLER_TASK_LOCK_NAME, self.worker_id)
        if lock is None:
            logging.debug('WorkspaceController did not acquire lock, skipping')
            return

        try:
            logging.debug('WorkspaceController: checking tasks')
            unfinished_tasks = self.client.get_tasks(unfinished=1)

            unfinished_tasks = sorted(
                unfinished_tasks,
                key=lambda t: '%d-%s' % (t.get('create_ts'), t.get('id')),
                reverse=True
            )
            tasks = unfinished_tasks[:self.max_concurrent_tasks]

            for task in tasks:
                logging.debug(task)
                # process tasks and release the lock
                try:
                    if task.get('kind') == Task.KIND_WORKSPACE_VOLUME_BACKUP:
                        self.process_volume_backup_task(task)
                    elif task.get('kind') == Task.KIND_WORKSPACE_VOLUME_RESTORE:
                        self.process_volume_restore_task(task)
                    else:
                        logging.warning('unknown task kind: %s' % task.kind)
                except Exception as e:
                    logging.warning('Marking task %s FAILED due to "%s"', task.get('id'), e)
                    self.client.update_task(task.get('id'), state=Task.STATE_FAILED)
                    self.client.add_task_results(
                        task.get('id'),
                        results='\n'.join(e.__str__().splitlines()[:4])
                    )
        finally:
            self.client.release_lock(WS_CONTROLLER_TASK_LOCK_NAME, self.worker_id)

    @staticmethod
    def get_volume_name(task_data):
        if task_data.get('type') == 'shared-data':
            return 'pvc-ws-vol-1'
        elif task_data.get('type') == 'user-data':
            return 'pvc-%s-work' % task_data.get('pseudonym')
        else:
            raise RuntimeWarning('Unknown task type "%s" encountered' % task_data.get('type'))

    def process_volume_backup_task(self, task):
        driver = self.get_driver(task.get('data').get('cluster'))
        if not driver:
            raise RuntimeError(
                'No driver for cluster %s in task %s' % (task.get('data').get('cluster'), task.get('id')))
        if task.get('state') == Task.STATE_NEW:
            logging.info('Starting processing of task %s', task.get('id'))
            self.client.update_task(task.get('id'), state=Task.STATE_PROCESSING)

            driver.create_volume_backup_job(
                self.client.token,
                task.get('data').get('workspace_id'),
                self.get_volume_name(task.get('data')),
            )
        elif task.get('state') == Task.STATE_PROCESSING:
            if driver.check_volume_backup_job(
                    self.client.token,
                    task.get('data').get('workspace_id'),
                    self.get_volume_name(task.get('data')),
            ):
                logging.info('Task %s FINISHED', task.get('id'))
                self.client.update_task(task.get('id'), state=Task.STATE_FINISHED)
        else:
            logging.warning(
                'task %s in state %s should not end up in processing', task.get('id'), task.get('state'))

    def process_volume_restore_task(self, task):
        task_data = task.get('data')
        driver = self.get_driver(task_data.get('tgt_cluster'))
        if not driver:
            raise RuntimeError(
                'No driver for tgt_cluster %s in task %s' % (task_data.get('tgt_cluster'), task.get('id')))
        ws_id = task_data.get('workspace_id')
        if not ws_id:
            raise RuntimeError('No data.workspace_id in task %s' % task.get('id'))
        src_cluster = task_data.get('src_cluster')
        if not src_cluster:
            raise RuntimeError('No data.src_cluster in task %s' % task.get('id'))

        if task.get('state') == Task.STATE_NEW:
            logging.info('Starting processing of task %s', task.get('id'))
            ws = self.client.get_workspace(ws_id)
            self.client.update_task(task.get('id'), state=Task.STATE_PROCESSING)

            # Figure out volume properties.
            # Volume sizes can be configured in workspace config or cluster_config.
            # cluster_config value has a size suffix, drop that (assume 'Gi' or fail) and convert to a number.
            if task_data.get('type') == 'shared-data':
                volume_size_gib = int(driver.cluster_config.get('volumeSizeShared', '20Gi').replace('Gi', ''))
                storage_class_name = driver.cluster_config.get('storageClassNameShared')
                access_mode = 'ReadWriteMany'
            elif task_data.get('type') == 'user-data':
                volume_size_gib = ws.get('config', {}).get('user_work_folder_size_gib', 1)
                storage_class_name = driver.cluster_config.get('storageClassNameUser')
                access_mode = 'ReadWriteOnce'
            else:
                raise RuntimeWarning('Unknown task type "%s" encountered' % task_data.get('type'))

            driver.create_volume_restore_job(
                token=self.client.token,
                workspace_id=ws_id,
                volume_name=self.get_volume_name(task_data),
                volume_size_spec='%dGi' % volume_size_gib,
                storage_class=storage_class_name,
                access_mode=access_mode,
                src_cluster=src_cluster,
            )
        elif task.get('state') == Task.STATE_PROCESSING:
            if driver.check_volume_restore_job(self.client.token, ws_id, self.get_volume_name(task_data)):
                logging.info('Task %s FINISHED', task.get('id'))
                self.client.update_task(task.get('id'), state=Task.STATE_FINISHED)
        else:
            logging.warning(
                'task %s in state %s should not end up in processing', task.get('id'), task.get('state'))


class CustomImageController(ControllerBase):
    """
    Controller that takes care of custom images and builds
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.cached_pull_creds: tuple[str, int] = ('', 0)
        self.polling_interval_min, self.polling_interval_max = self.get_polling_interval(5, 20)
        self.build_client = BuildClient(
            build_namespace=os.environ.get('CUSTOM_IMAGE_CONTROLLER_BUILD_NAMESPACE'),
            registry=os.environ.get('CUSTOM_IMAGE_CONTROLLER_REGISTRY'),
            repo=os.environ.get('CUSTOM_IMAGE_CONTROLLER_REPO'),
        )
        self.build_pod_memory = os.environ.get('CUSTOM_IMAGE_CONTROLLER_BUILD_POD_MEMORY', '4Gi')
        logging.info(f'CustomImageController build_namespace: {self.build_client.build_namespace}')
        logging.info(f'CustomImageController registry: {self.build_client.registry}')
        logging.info(f'CustomImageController repo: {self.build_client.repo}')
        logging.info(f'CustomImageController build_pod_memory: {self.build_pod_memory}')

    def process_custom_image(self, image):
        logging.debug('CustomImageController processing image %s', image.get('id'))

        if image.get('to_be_deleted'):
            ws = self.client.get_workspace(image.get('workspace_id'))
            # delete build (usually done when build is completed, but for cancellation we need to do it)
            if image.get('build_system_id'):
                self.build_client.delete_build(image.get('build_system_id'), suppress_404=True)
            # delete tag from imagestream
            if image.get('tag'):
                self.build_client.delete_tag(ws.get('pseudonym'), image.get('tag'), suppress_404=True)
            self.client.do_custom_image_patch(
                image.get('id'),
                json_data=dict(
                    state=CustomImage.STATE_DELETED,
                )
            )
            logging.info(f'CustomImageController deleted custom image "{image.get('name', '')}"')
        elif image.get('state') in [CustomImage.STATE_NEW]:
            ws = self.client.get_workspace(image.get('workspace_id'))
            post_res = self.build_client.post_build(
                name=ws.get('pseudonym'),
                dockerfile=image.get('dockerfile'),
                build_pod_memory=self.build_pod_memory,
            )
            url = f"{post_res.get('registry')}/{post_res.get('repo')}/{post_res.get('name')}:{post_res.get('tag')}"
            logging.info('CustomImageController created build %s for url %s', post_res.get('build_id'), url)
            self.client.do_custom_image_patch(
                image.get('id'),
                json_data=dict(
                    state=CustomImage.STATE_BUILDING,
                    build_system_id=post_res.get('build_id'),
                    url=url,
                    tag=post_res.get('tag'),
                )
            )

        elif image.get('state') in [CustomImage.STATE_BUILDING]:
            build = self.build_client.get_build(image.get('build_system_id'))
            status = build.get('status')
            phase = status.get('phase')
            logging.info('CustomImageController build %s in phase %s', image.get('build_system_id'), phase)
            if phase == 'Failed':
                logging.warning(
                    'CustomImageController build %s failed due to %s',
                    image.get('build_system_id'),
                    status.get('message'))
                self.build_client.delete_build(image.get('build_system_id'))
                self.client.do_custom_image_patch(
                    image.get('id'),
                    json_data=dict(
                        state=CustomImage.STATE_FAILED,
                        build_system_output=f"{status.get('message')}\n{status.get('logSnippet')}",
                    )
                )
            elif phase == 'Complete':
                self.build_client.delete_build(image.get('build_system_id'))
                self.client.do_custom_image_patch(
                    image.get('id'),
                    json_data=dict(state=CustomImage.STATE_COMPLETED)
                )

    def process(self):
        # process images in increased intervals
        now = int(time.time())
        if now < self.next_check_ts:
            return
        self.update_next_check_ts(self.polling_interval_min, self.polling_interval_max)

        # renew the custom image pull credentials if necessary, and make them available in cluster_config.runtime_data
        if self.cached_pull_creds[1] < now + 60 * 5:
            try:
                self.cached_pull_creds = self.build_client.create_sa_pull_creds(
                    'custom-image-puller', duration_seconds=60 * 15)
                image_prefix = '%s/%s/' % (
                    os.environ.get('CUSTOM_IMAGE_CONTROLLER_REGISTRY'), os.environ.get('CUSTOM_IMAGE_CONTROLLER_REPO'),
                )
                self.cluster_config['runtime_data']['pull_creds'] = [
                    dict(
                        prefix=image_prefix,
                        dockercfg=self.cached_pull_creds[0],
                    ),
                ]
            except RuntimeWarning as e:
                logging.warning(e)

        # fetch unfinished images to process
        unfinished_images = self.client.get_custom_images(unfinished=True)
        # check if we have anything to do
        if not unfinished_images:
            return
        logging.debug('CustomImageController found %d unfinished images', len(unfinished_images))

        # Try to obtain a global lock for CustomImage processing.
        # Should we lose the race, the winner takes it, and we try next time we are active
        lock = self.client.obtain_lock(CUSTOM_IMAGE_CONTROLLER_TASK_LOCK_NAME, self.worker_id)
        if lock is None:
            logging.debug('CustomImageController did not acquire lock, skipping')
            return
        # we now hold exclusive lock for processing, refresh the list to make sure we have the latest committed data
        try:
            # fetch prioritized list for processing (building > new > the rest)
            images = self.client.get_custom_images(limit=CUSTOM_IMAGE_CONTROLLER_LIMIT_SIZE)
            for image in images:
                try:
                    self.process_custom_image(image)
                except Exception as e:
                    logging.warning(e)
                    self.client.do_custom_image_patch(image.get('id'), json_data=dict(state=CustomImage.STATE_FAILED))
        finally:
            self.client.release_lock(CUSTOM_IMAGE_CONTROLLER_TASK_LOCK_NAME, self.worker_id)
