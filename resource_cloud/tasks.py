import base64
import json
import logging

import requests
from celery import Celery
from celery.utils.log import get_task_logger
from celery.schedules import crontab
from flask import render_template
from flask.ext.mail import Message

from resource_cloud.app import get_app

# from resource_cloud.config import BaseConfig as config
from resource_cloud.config import DevConfig as ActiveConfig

ActiveConfig.FAKE_PROVISIONING = True

# tune requests to give less spam in development environment with self signed certificate
requests.packages.urllib3.disable_warnings()
logging.getLogger("requests").setLevel(logging.WARNING)

logger = get_task_logger(__name__)
app = Celery('tasks', broker=ActiveConfig.MESSAGE_QUEUE_URI, backend=ActiveConfig.MESSAGE_QUEUE_URI)
app.conf.CELERY_TASK_SERIALIZER = 'json'
app.conf.CELERYBEAT_SCHEDULE = {
    'deprovision-expired-every-minute': {
        'task': 'resource_cloud.tasks.deprovision_expired',
        'schedule': crontab(minute='*/1'),
    },
    'check-plugins-every-minute': {
        'task': 'resource_cloud.tasks.publish_plugins',
        'schedule': crontab(minute='*/1'),
    }
}
app.conf.CELERY_TIMEZONE = 'UTC'

flask_app = get_app()


@app.task(name="resource_cloud.tasks.deprovision_expired")
def deprovision_expired():
    token = get_token()
    provisioned_resources = get_provisioned_resources(token)
    for provisioned_resource in provisioned_resources:
        logger.debug('checking provisioned resource for expiration %s' % provisioned_resource)

        if not provisioned_resource.get('state') in ['running']:
            continue
        if not provisioned_resource.get('lifetime_left'):
            logger.info('timed deprovisioning triggered for %s' % provisioned_resource.get('id'))
            run_deprovisioning.delay(token, provisioned_resource.get('id'))


@app.task(name="resource_cloud.tasks.send_mails")
def send_mails(users):
    with flask_app.test_request_context():
        for email, token in users:
            msg = Message('Resource-cloud activation')
            msg.recipients = [email]
            msg.sender = flask_app.config.get('SENDER_EMAIL')
            activation_url = '%s/#/activate/%s' % (flask_app.config['BASE_URL'],
                                                   token)
            msg.html = render_template('invitation.html',
                                       activation_link=activation_url)
            msg.body = render_template('invitation.txt',
                                       activation_link=activation_url)
            mail = flask_app.extensions.get('mail')
            if not mail:
                raise RuntimeError("mail extension is not configured")
            if flask_app.config.get('MAIL_SUPPRESS_SEND'):
                logger.info(msg.body)
            mail.send(msg)


def get_provisioning_manager():
    from stevedore import dispatch

    mgr = dispatch.NameDispatchExtensionManager(
        namespace='resource_cloud.drivers.provisioning',
        check_func=lambda x: True,
        invoke_on_load=True,
        invoke_args=(logger, ActiveConfig),
    )

    logger.debug('provisioning manager loaded, extensions: %s ' % mgr.names())

    return mgr


def get_provisioning_type(token, provisioned_resource_id):
    resource = get_provisioned_resource_parent_data(token, provisioned_resource_id)
    plugin_id = resource['plugin']
    return get_plugin_data(token, plugin_id)['name']


@app.task(name="resource_cloud.tasks.run_provisioning")
def run_provisioning(token, provisioned_resource_id):
    logger.info('provisioning triggered for %s' % provisioned_resource_id)
    mgr = get_provisioning_manager()

    plugin = get_provisioning_type(token, provisioned_resource_id)

    mgr.map_method([plugin], 'provision', token, provisioned_resource_id)

    logger.info('provisioning done, notifying server')


@app.task(name="resource_cloud.tasks.run_deprovisioning")
def run_deprovisioning(token, provisioned_resource_id):
    logger.info('deprovisioning triggered for %s' % provisioned_resource_id)

    mgr = get_provisioning_manager()

    plugin = get_provisioning_type(token, provisioned_resource_id)

    mgr.map_method([plugin], 'deprovision', token, provisioned_resource_id)

    logger.info('deprovisioning done, notifying server')


@app.task(name="resource_cloud.tasks.publish_plugins")
def publish_plugins():
    logger.info('provisioning plugins queried from worker')
    token = get_token()
    mgr = get_provisioning_manager()
    for plugin in mgr.names():
        payload = {}
        payload['plugin'] = plugin

        res=mgr.map_method([plugin], 'get_configuration')
        if not len(res):
            logger.warn('plugin returned empty configuration: %s' % plugin)
            continue
        config=res[0]

        for key in ('schema', 'form', 'model'):
            payload[key] = json.dumps(config.get(key, {}))

        do_post(token, 'plugins', payload)


def get_token():
    auth_url = 'https://localhost/api/v1/sessions'
    auth_credentials = {'email': 'worker@resource_cloud',
                        'password': flask_app.config['SECRET_KEY']}
    try:
        r = requests.post(auth_url, auth_credentials, verify=ActiveConfig.SSL_VERIFY)
        return json.loads(r.text).get('token')
    except:
        return None


def do_get(token, object_url):
    auth = base64.encodestring('%s:%s' % (token, '')).replace('\n', '')
    headers = {'Accept': 'text/plain',
               'Authorization': 'Basic %s' % auth}

    url = 'https://localhost/api/v1/%s' % object_url
    resp = requests.get(url, headers=headers, verify=ActiveConfig.SSL_VERIFY)
    logger.debug('got response %s %s' % (resp.status_code, resp.reason))
    return resp


def do_post(token, api_path, data):
    auth = base64.encodestring('%s:%s' % (token, '')).replace('\n', '')
    headers = {'Accept': 'text/plain',
               'Authorization': 'Basic %s' % auth}
    url = 'https://localhost/api/v1/%s' % api_path
    resp = requests.post(url, data, headers=headers, verify=ActiveConfig.SSL_VERIFY)
    logger.debug('got response %s %s' % (resp.status_code, resp.reason))
    return resp


def get_provisioned_resources(token):
    resp = do_get(token, 'provisioned_resources')
    if resp.status_code != 200:
        raise RuntimeError('Cannot fetch data for provisioned resources, %s' % resp.reason)
    return resp.json()


def get_provisioned_resource(token, provisioned_resource_id):
    resp = do_get(token, 'provisioned_resources/%s' % provisioned_resource_id)
    if resp.status_code != 200:
        raise RuntimeError('Cannot fetch data for provisioned resource %s, %s' % (provisioned_resource_id, resp.reason))
    return resp.json()


def get_resource_description(token, resource_id):
    resp = do_get(token, 'resources/%s' % resource_id)
    if resp.status_code != 200:
        raise RuntimeError('Cannot fetch data for resource %s, %s' % (resource_id, resp.reason))
    return resp.json()


def get_provisioned_resource_parent_data(token, provisioned_resource_id):
    resource_id = get_provisioned_resource(token, provisioned_resource_id)['resource_id']

    resp = do_get(token, 'resources/%s' % resource_id)
    if resp.status_code != 200:
        raise RuntimeError('Error loading resource data: %s, %s' % (resource_id, resp.reason))

    return resp.json()


def get_plugin_data(token, plugin_id):
    resp = do_get(token, 'plugins/%s' % plugin_id)
    if resp.status_code != 200:
        raise RuntimeError('Error loading plugin data: %s, %s' % (plugin_id, resp.reason))

    return resp.json()
