import base64
from email.mime.text import MIMEText
import glob
import json
import logging
from string import Template
import os
import smtplib

import requests
from kombu import Queue
from celery import Celery
from celery.utils.log import get_task_logger
from celery.schedules import crontab
from flask import render_template

from pouta_blueprints.app import app as flask_app
from pouta_blueprints.client import PBClient

# tune requests to give less spam in development environment with self signed certificate
requests.packages.urllib3.disable_warnings()
logging.getLogger("requests").setLevel(logging.WARNING)

flask_config = flask_app.dynamic_config

RUNTIME_PATH = '/webapps/pouta_blueprints/run'


def get_token():
    auth_url = '%s/sessions' % flask_config['INTERNAL_API_BASE_URL']
    auth_credentials = {'email': 'worker@pouta_blueprints',
                        'password': flask_config['SECRET_KEY']}
    try:
        r = requests.post(auth_url, auth_credentials, verify=flask_config['SSL_VERIFY'])
        return json.loads(r.text).get('token')
    except:
        return None


def do_get(token, object_url):
    auth = base64.encodestring('%s:%s' % (token, '')).replace('\n', '')
    headers = {'Accept': 'text/plain',
               'Authorization': 'Basic %s' % auth}
    url = '%s/%s' % (flask_config['INTERNAL_API_BASE_URL'], object_url)
    resp = requests.get(url, headers=headers, verify=flask_config['SSL_VERIFY'])
    return resp


def do_post(token, api_path, data):
    auth = base64.encodestring('%s:%s' % (token, '')).replace('\n', '')
    headers = {'Accept': 'text/plain',
               'Authorization': 'Basic %s' % auth}
    url = '%s/%s' % (flask_config['INTERNAL_API_BASE_URL'], api_path)
    resp = requests.post(url, data, headers=headers, verify=flask_config['SSL_VERIFY'])
    return resp


def get_config():
    """
    Retrieve dynamic config over ReST API. Config object from Flask is unable to resolve variables from
    database if containers are used. In order to use the ReST API some configuration items
    (Variable.filtered_variables) are required. These are read from Flask config object, as these values
    cannot be modified during the runtime.
    """
    token = get_token()
    pbclient = PBClient(token, flask_config['INTERNAL_API_BASE_URL'], ssl_verify=False)

    return dict([(x['key'], x['value']) for x in pbclient.do_get('variables').json()])


logger = get_task_logger(__name__)
if flask_config['DEBUG']:
    logger.setLevel('DEBUG')

app = Celery(
    'tasks',
    broker=flask_config['MESSAGE_QUEUE_URI'],
    backend=flask_config['MESSAGE_QUEUE_URI']
)

app.conf.CELERY_TIMEZONE = 'UTC'
app.conf.CELERY_ACCEPT_CONTENT = ['pickle', 'json', 'msgpack', 'yaml']
app.conf.CELERYD_CONCURRENCY = 16
app.conf.CELERYD_PREFETCH_MULTIPLIER = 1
app.conf.CELERY_TASK_SERIALIZER = 'json'

app.conf.CELERY_QUEUES = (
    Queue('celery', routing_key='task.#'),
    Queue('proxy_tasks', routing_key='proxy_task.#'),
)

# app.conf.CELERY_ROUTES = {
#         'pouta_blueprints.tasks.proxy_add_route': {
#             'queue': 'proxy_tasks',
#             'routing_key': 'proxy_task.proxy_add_route',
#         },
# }

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
    },
    'housekeeping-every-minute': {
        'task': 'pouta_blueprints.tasks.housekeeping',
        'schedule': crontab(minute='*/1'),
        'options': {'expires': 60},
    }
}


@app.task(name="pouta_blueprints.tasks.deprovision_expired")
def deprovision_expired():
    token = get_token()
    pbclient = PBClient(token, flask_config['INTERNAL_API_BASE_URL'], ssl_verify=False)
    instances = pbclient.get_instances()

    for instance in instances:
        logger.debug('checking instance for expiration %s' % instance)
        user = instance.get('user')
        deprovision_required = False
        if not instance.get('state') in ['running']:
            continue

        if not instance.get('lifetime_left') and instance.get('maximum_lifetime'):
            logger.info('deprovisioning triggered for %s (reason: maximum lifetime exceeded)' % instance.get('id'))
            deprovision_required = True
        elif user.get('credits_quota') <= user.get('credits_spent'):
            if instance.get('cost_multiplier', 0) > 0:
                logger.info('deprovisioning triggered for %s (reason: user out of quota)' % instance.get('id'))
                deprovision_required = True

        if deprovision_required:
            run_deprovisioning.delay(token, instance.get('id'))


@app.task(name="pouta_blueprints.tasks.send_mails")
def send_mails(users):
    with flask_app.test_request_context():
        config = get_config()
        for email, token in users:
            base_url = config['BASE_URL'].strip('/')
            activation_url = '%s/#/activate/%s' % (base_url, token)
            msg = MIMEText(render_template('invitation.txt', activation_link=activation_url))
            msg['Subject'] = 'Pouta Blueprints account activation'
            msg['To'] = email
            msg['From'] = config['SENDER_EMAIL']
            logger.info(msg)

            if not config['MAIL_SUPPRESS_SEND']:
                s = smtplib.SMTP(config['MAIL_SERVER'])
                if config['MAIL_USE_TLS']:
                    s.starttls()
                s.sendmail(msg['From'], [msg['To']], msg.as_string())
                s.quit()
            else:
                logger.info('Mail sending suppressed in config')


def get_provisioning_manager():
    from stevedore import dispatch

    config = get_config()
    if config.get('PLUGIN_WHITELIST', ''):
        plugin_whitelist = config.get('PLUGIN_WHITELIST').split()
        mgr = dispatch.NameDispatchExtensionManager(
            namespace='pouta_blueprints.drivers.provisioning',
            check_func=lambda x: x.name in plugin_whitelist,
            invoke_on_load=True,
            invoke_args=(logger, get_config()),
        )
    else:
        mgr = dispatch.NameDispatchExtensionManager(
            namespace='pouta_blueprints.drivers.provisioning',
            check_func=lambda x: True,
            invoke_on_load=True,
            invoke_args=(logger, get_config()),
        )

    logger.debug('provisioning manager loaded, extensions: %s ' % mgr.names())

    return mgr


def get_provisioning_type(token, instance_id):
    pbclient = PBClient(token, flask_config['INTERNAL_API_BASE_URL'], ssl_verify=False)

    blueprint = pbclient.get_instance_parent_data(instance_id)
    plugin_id = blueprint['plugin']
    return pbclient.get_plugin_data(plugin_id)['name']


def run_provisioning_impl(token, instance_id, method):
    logger.info('%s triggered for %s' % (method, instance_id))
    mgr = get_provisioning_manager()

    plugin = get_provisioning_type(token, instance_id)

    mgr.map_method([plugin], method, token, instance_id)

    logger.info('%s done, notifying server' % method)


@app.task(name="pouta_blueprints.tasks.run_provisioning")
def run_provisioning(token, instance_id):
    run_provisioning_impl(token, instance_id, 'provision')


@app.task(name="pouta_blueprints.tasks.run_deprovisioning")
def run_deprovisioning(token, instance_id):
    run_provisioning_impl(token, instance_id, 'deprovision')


@app.task(name="pouta_blueprints.tasks.publish_plugins")
def publish_plugins():
    logger.info('provisioning plugins queried from worker')
    token = get_token()
    mgr = get_provisioning_manager()
    for plugin in mgr.names():
        payload = {'plugin': plugin}
        res = mgr.map_method([plugin], 'get_configuration')
        if not len(res):
            logger.warn('plugin returned empty configuration: %s' % plugin)
            continue
        config = res[0]

        if not config:
            logger.warn('No config for %s obtained' % plugin)
            continue

        for key in ('schema', 'form', 'model'):
            payload[key] = json.dumps(config.get(key, {}))

        do_post(token, 'plugins', payload)


@app.task(name="pouta_blueprints.tasks.housekeeping")
def housekeeping():
    token = get_token()
    logger.info('provisioning plugins queried from worker')
    mgr = get_provisioning_manager()
    mgr.map_method(mgr.names(), 'housekeep', token)


@app.task(name="pouta_blueprints.tasks.update_user_connectivity")
def update_user_connectivity(instance_id):
    logger.info('updating connectivity for instance %s' % instance_id)
    token = get_token()
    mgr = get_provisioning_manager()
    plugin = get_provisioning_type(token, instance_id)
    mgr.map_method([plugin], 'update_connectivity', token, instance_id)
    logger.info('update connectivity for instance %s ready' % instance_id)


@app.task(name="pouta_blueprints.tasks.proxy_add_route")
def proxy_add_route(route_key, target):
    logger.info('proxy_add_route(%s, %s)' % (route_key, target))

    # generate a location snippet for nginx proxy config
    # see https://support.rstudio.com/hc/en-us/articles/200552326-Running-with-a-Proxy
    template = Template(
        """
        location /${route_key}/ {
          rewrite ^/${route_key}/(.*)$$ /$$1 break;
          proxy_pass ${target};
          proxy_redirect ${target} $$scheme://$$host:${public_http_proxy_port}/${route_key};
        }
        """
    )

    path = '%s/route_key-%s' % (RUNTIME_PATH, route_key)
    with open(path, 'w') as f:
        f.write(
            template.substitute(
                route_key=route_key,
                target=target,
                public_http_proxy_port=get_config()['PUBLIC_HTTP_PROXY_PORT']
            )
        )

    refresh_nginx_config()


@app.task(name="pouta_blueprints.tasks.proxy_remove_route")
def proxy_remove_route(route_key):
    logger.info('proxy_remove_route(%s)' % route_key)

    path = '%s/route_key-%s' % (RUNTIME_PATH, route_key)
    if os.path.exists(path):
        os.remove(path)
    else:
        logger.info('proxy_remove_route(): no such file')

    refresh_nginx_config()


def refresh_nginx_config():
    logger.debug('refresh_nginx_config()')

    config = ['server {', 'listen %s;' % get_config()['INTERNAL_HTTP_PROXY_PORT']]

    pattern = '%s/route_key-*' % RUNTIME_PATH
    for proxy_route in glob.glob(pattern):
        logger.debug('refresh_nginx_config(): adding %s to config' % proxy_route)
        with open(proxy_route, 'r') as f:
            config.extend(x.rstrip() for x in f.readlines())

    config.append('}')

    # path = '/etc/nginx/sites-enabled/proxy'
    # path = '/tmp/proxy.conf'
    path = '%s/proxy.conf' % RUNTIME_PATH

    with open(path, 'w') as f:
        f.write('\n'.join(config))
