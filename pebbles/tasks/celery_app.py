import base64
import json
import logging
from celery import Celery
from kombu import Queue
from celery.schedules import crontab
from celery.signals import worker_process_init
import requests
from celery.utils.log import get_task_logger
from pebbles.config import BaseConfig

local_config = BaseConfig()


def get_token():
    """ returns a session token from te internal API.
    """
    auth_url = '%s/sessions' % local_config['INTERNAL_API_BASE_URL']
    auth_credentials = {'eppn': 'worker@pebbles',
                        'password': local_config['SECRET_KEY']}
    try:
        r = requests.post(auth_url, auth_credentials, verify=local_config['SSL_VERIFY'])
        return json.loads(r.text).get('token')
    except:
        return None


def do_get(token, object_url):
    """ wrapper to use the GET method with authentication token against the
    internal api url.
    """
    auth = base64.encodestring('%s:%s' % (token, '')).replace('\n', '')
    headers = {'Accept': 'text/plain',
               'Authorization': 'Basic %s' % auth}
    url = '%s/%s' % (local_config['INTERNAL_API_BASE_URL'], object_url)
    resp = requests.get(url, headers=headers, verify=local_config['SSL_VERIFY'])
    return resp


def do_post_or_put(token, api_path, data, method='POST'):
    """ wrapper to use the POST method with uthentication token against the
    internal api url.
    """
    auth = base64.encodestring('%s:%s' % (token, '')).replace('\n', '')
    headers = {'Accept': 'text/plain',
               'Authorization': 'Basic %s' % auth}
    url = '%s/%s' % (local_config['INTERNAL_API_BASE_URL'], api_path)
    if method == 'POST':
        resp = requests.post(url, json=data, headers=headers, verify=local_config['SSL_VERIFY'])
    elif method == 'PUT':
        resp = requests.put(url, json=data, headers=headers, verify=local_config['SSL_VERIFY'])
    return resp


def get_dynamic_config():

    """ Get the dynamic config by using the environment vars, config YAML file,
        default values in config.py, In that order of precedence
    """

    return BaseConfig()


# tune requests to give less spam in development environment with self signed certificate
# TODO: Should we disable this when not in development environment then? -jyrsa 2016-11-28
requests.packages.urllib3.disable_warnings()
logging.getLogger("requests").setLevel(logging.WARNING)

logger = get_task_logger(__name__)
if local_config['DEBUG']:
    logger.setLevel('DEBUG')
    print('debug enabled')
    print('api url ' + local_config['INTERNAL_API_BASE_URL'])

celery_app = Celery(
    'tasks',
    broker=local_config['MESSAGE_QUEUE_URI'],
    backend=local_config['MESSAGE_QUEUE_URI']
)

celery_app.conf.CELERY_TIMEZONE = 'UTC'
celery_app.conf.CELERY_ACCEPT_CONTENT = ['pickle', 'json', 'msgpack', 'yaml']
celery_app.conf.CELERYD_PREFETCH_MULTIPLIER = 1
celery_app.conf.CELERY_TASK_SERIALIZER = 'json'

celery_app.conf.CELERY_CREATE_MISSING_QUEUES = True
celery_app.conf.CELERY_QUEUES = (
    Queue('celery', routing_key='task.#'),
    Queue('proxy_tasks', routing_key='proxy_task.#'),
    Queue('system_tasks', routing_key='system_task.#'),
)
celery_app.conf.CELERY_ROUTES = (
    'pebbles.tasks.celery_app.TaskRouter',
)

celery_app.conf.CELERYBEAT_SCHEDULE = {
    'periodic-update-every-minute': {
        'task': 'pebbles.tasks.periodic_update',
        'schedule': crontab(minute='*/1'),
        'options': {'expires': 60, 'queue': 'system_tasks'},
    },
    'check-plugins-every-minute': {
        'task': 'pebbles.tasks.publish_plugins_and_configs',
        'schedule': crontab(minute='*/1'),
        'options': {'expires': 60, 'queue': 'system_tasks'},
    },
    'housekeeping-every-minute': {
        'task': 'pebbles.tasks.housekeeping',
        'schedule': crontab(minute='*/1'),
        'options': {'expires': 60, 'queue': 'system_tasks'},
    },
    'periodic-update-every-year': {
        'task': 'pebbles.tasks.user_blueprint_cleanup',
        'schedule': crontab(month_of_year='12', day_of_month='1'),
        'options': {'expires': 60, 'queue': 'system_tasks'},
    }
}


class TaskRouter(object):
    @staticmethod
    def get_provisioning_queue(instance_id):
        queue_num = ((int(instance_id[-2:], 16) % local_config['PROVISIONING_NUM_WORKERS']) + 1)
        logger.debug('selected queue %d/%d for %s' % (queue_num, local_config['PROVISIONING_NUM_WORKERS'], instance_id))
        return 'provisioning_tasks-%d' % queue_num

    def route_for_task(self, task, args=None, kwargs=None):
        if task in (
                "pebbles.tasks.send_mails",
                "pebbles.tasks.periodic_update",
                "pebbles.tasks.send_mails",
                "pebbles.tasks.publish_plugins_and_configs",
                "pebbles.tasks.housekeeping",
                "pebbles.tasks.user_blueprint_cleanup",
                "pebbles.tasks.instance_token_cleanup"
        ):
            return {'queue': 'system_tasks'}

        if task in (
                "pebbles.tasks.update_user_connectivity",
                "pebbles.tasks.run_update",
                "pebbles.tasks.fetch_running_instance_logs"
        ):
            instance_id = args[0]
            return {'queue': self.get_provisioning_queue(instance_id)}

        if task == "pebbles.tasks.run_update":
            instance_id = args[1]
            return {'queue': self.get_provisioning_queue(instance_id)}

        if task in (
                "pebbles.tasks.proxy_add_route",
                "pebbles.tasks.proxy_remove_route"
        ):
            return {'queue': 'proxy_tasks'}

        return {'queue': 'celery'}


@worker_process_init.connect
def fix_multiprocessing(**kwargs):
    # don't be a daemon, so we can create new subprocesses
    # see https://github.com/celery/celery/issues/1709#issuecomment-261710839
    from multiprocessing import current_process
    current_process().daemon = False
