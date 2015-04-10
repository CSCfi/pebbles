import base64
import json
import logging

import requests
from celery import Celery
from celery.utils.log import get_task_logger
from celery.schedules import crontab
from flask import render_template
from flask.ext.mail import Message

from pouta_blueprints.app import get_app
from pouta_blueprints.config import BaseConfig

flask_app = get_app()

# tune requests to give less spam in development environment with self signed certificate
requests.packages.urllib3.disable_warnings()
logging.getLogger("requests").setLevel(logging.WARNING)

config = BaseConfig()

logger = get_task_logger(__name__)
app = Celery('tasks', broker=config['MESSAGE_QUEUE_URI'], backend=config['MESSAGE_QUEUE_URI'])
app.conf.CELERY_TASK_SERIALIZER = 'json'
app.conf.CELERYBEAT_SCHEDULE = {
    'deprovision-expired-every-minute': {
        'task': 'pouta_blueprints.tasks.deprovision_expired',
        'schedule': crontab(minute='*/1'),
        'options': {'expires': 60},
    },
    'check-plugins-every-minute': {
        'task': 'pouta_blueprints.tasks.publish_plugins',
        'schedule': crontab(minute='*/1'),
        'options': {'expires': 60},
    }
}
app.conf.CELERY_TIMEZONE = 'UTC'


@app.task(name="pouta_blueprints.tasks.deprovision_expired")
def deprovision_expired():
    token = get_token()
    instances = get_instances(token)
    for instance in instances:
        logger.debug('checking instance for expiration %s' % instance)

        if not instance.get('state') in ['running']:
            continue
        if not instance.get('lifetime_left') and instance.get('max_lifetime'):
            logger.info('timed deprovisioning triggered for %s' % instance.get('id'))
            run_deprovisioning.delay(token, instance.get('id'))


@app.task(name="pouta_blueprints.tasks.send_mails")
def send_mails(users):
    with flask_app.test_request_context():
        for email, token in users:
            msg = Message('Resource-cloud activation')
            msg.recipients = [email]
            msg.sender = config['SENDER_EMAIL']
            activation_url = '%s/#/activate/%s' % (config['BASE_URL'], token)
            msg.html = render_template('invitation.html',
                                       activation_link=activation_url)
            msg.body = render_template('invitation.txt',
                                       activation_link=activation_url)
            mail = flask_app.extensions.get('mail')
            if not mail:
                raise RuntimeError("mail extension is not configured")
            if config['MAIL_SUPPRESS_SEND']:
                logger.info(msg.body)
            mail.send(msg)


def get_provisioning_manager():
    from stevedore import dispatch

    mgr = dispatch.NameDispatchExtensionManager(
        namespace='pouta_blueprints.drivers.provisioning',
        check_func=lambda x: True,
        invoke_on_load=True,
        invoke_args=(logger, flask_app.config),
    )

    logger.debug('provisioning manager loaded, extensions: %s ' % mgr.names())

    return mgr


def get_provisioning_type(token, instance_id):
    blueprint = get_instance_parent_data(token, instance_id)
    plugin_id = blueprint['plugin']
    return get_plugin_data(token, plugin_id)['name']


@app.task(name="pouta_blueprints.tasks.run_provisioning")
def run_provisioning(token, instance_id):
    logger.info('provisioning triggered for %s' % instance_id)
    mgr = get_provisioning_manager()

    plugin = get_provisioning_type(token, instance_id)

    mgr.map_method([plugin], 'provision', token, instance_id)

    logger.info('provisioning done, notifying server')


@app.task(name="pouta_blueprints.tasks.run_deprovisioning")
def run_deprovisioning(token, instance_id):
    logger.info('deprovisioning triggered for %s' % instance_id)

    mgr = get_provisioning_manager()

    plugin = get_provisioning_type(token, instance_id)

    mgr.map_method([plugin], 'deprovision', token, instance_id)

    logger.info('deprovisioning done, notifying server')


@app.task(name="pouta_blueprints.tasks.publish_plugins")
def publish_plugins():
    logger.info('provisioning plugins queried from worker')
    token = get_token()
    mgr = get_provisioning_manager()
    for plugin in mgr.names():
        payload = {}
        payload['plugin'] = plugin

        res = mgr.map_method([plugin], 'get_configuration')
        if not len(res):
            logger.warn('plugin returned empty configuration: %s' % plugin)
            continue
        config = res[0]

        for key in ('schema', 'form', 'model'):
            payload[key] = json.dumps(config.get(key, {}))

        do_post(token, 'plugins', payload)


@app.task(name="pouta_blueprints.tasks.update_user_connectivity")
def update_user_connectivity(instance_id):
    logger.info('updating connectivity for instance %s' % instance_id)
    token = get_token()
    mgr = get_provisioning_manager()
    plugin = get_provisioning_type(token, instance_id)
    mgr.map_method([plugin], 'update_connectivity', token, instance_id)
    logger.info('update connectivity for instance %s ready' % instance_id)


def get_token():
    auth_url = '%s/sessions' % config['INTERNAL_API_BASE_URL']
    auth_credentials = {'email': 'worker@pouta_blueprints',
                        'password': config['SECRET_KEY']}
    try:
        r = requests.post(auth_url, auth_credentials, verify=config['SSL_VERIFY'])
        return json.loads(r.text).get('token')
    except:
        return None


def do_get(token, object_url):
    auth = base64.encodestring('%s:%s' % (token, '')).replace('\n', '')
    headers = {'Accept': 'text/plain',
               'Authorization': 'Basic %s' % auth}

    url = '%s/%s' % (config['INTERNAL_API_BASE_URL'], object_url)
    resp = requests.get(url, headers=headers, verify=config['SSL_VERIFY'])
    logger.debug('got response %s %s' % (resp.status_code, resp.reason))
    return resp


def do_post(token, api_path, data):
    auth = base64.encodestring('%s:%s' % (token, '')).replace('\n', '')
    headers = {'Accept': 'text/plain',
               'Authorization': 'Basic %s' % auth}
    url = '%s/%s' % (config['INTERNAL_API_BASE_URL'], api_path)
    resp = requests.post(url, data, headers=headers, verify=config['SSL_VERIFY'])
    logger.debug('got response %s %s' % (resp.status_code, resp.reason))
    return resp


def get_instances(token):
    resp = do_get(token, 'instances')
    if resp.status_code != 200:
        raise RuntimeError('Cannot fetch data for instances, %s' % resp.reason)
    return resp.json()


def get_instance(token, instance_id):
    resp = do_get(token, 'instances/%s' % instance_id)
    if resp.status_code != 200:
        raise RuntimeError('Cannot fetch data for instances %s, %s' % (instance_id, resp.reason))
    return resp.json()


def get_blueprint_description(token, blueprint_id):
    resp = do_get(token, 'blueprints/%s' % blueprint_id)
    if resp.status_code != 200:
        raise RuntimeError('Cannot fetch data for blueprint %s, %s' % (blueprint_id, resp.reason))
    return resp.json()


def get_instance_parent_data(token, instance_id):
    blueprint_id = get_instance(token, instance_id)['blueprint_id']

    resp = do_get(token, 'blueprints/%s' % blueprint_id)
    if resp.status_code != 200:
        raise RuntimeError('Error loading blueprint data: %s, %s' % (blueprint_id, resp.reason))

    return resp.json()


def get_plugin_data(token, plugin_id):
    resp = do_get(token, 'plugins/%s' % plugin_id)
    if resp.status_code != 200:
        raise RuntimeError('Error loading plugin data: %s, %s' % (plugin_id, resp.reason))

    return resp.json()
