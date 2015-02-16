import base64
from random import randint
import select
import shlex
import os
import subprocess
import requests
from celery import Celery
from celery.utils.log import get_task_logger
import jinja2
from flask import render_template
from flask.ext.mail import Message
import stat
import time
import logging
import yaml
from resource_cloud.app import get_app
# from resource_cloud.config import BaseConfig as config
from resource_cloud.config import DevConfig as config

config.FAKE_PROVISIONING = True

# tune requests to give less spam in development environment with self signed certificate
requests.packages.urllib3.disable_warnings()
logging.getLogger("requests").setLevel(logging.WARNING)

logger = get_task_logger(__name__)
app = Celery('tasks', broker=config.MESSAGE_QUEUE_URI, backend=config.MESSAGE_QUEUE_URI)
app.conf.CELERY_TASK_SERIALIZER = 'json'

flask_app = get_app()


@app.task(name="resource_cloud.tasks.send_mails")
def send_mails(users):
    with flask_app.test_request_context():
        for email, token in users:
            msg = Message('Resource-cloud activation')
            msg.recipients = [email]
            msg.sender = 'resource-cloud@csc.fi'
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


@app.task(name="resource_cloud.tasks.run_provisioning")
def run_provisioning(token, resource_id):
    logger.info('provisioning triggered for %s' % resource_id)

    do_provisioned_resource_patch(token, resource_id, {'state': 'provisioning'})

    run_pvc_provisioning(token, resource_id)

    logger.info('provisioning done, notifying server')
    resp = do_provisioned_resource_patch(token, resource_id, {'state': 'running'})

    if resp.status_code == 200:
        return 'ok'

    return 'error: %s %s' % (resp.status_code, resp.reason)


@app.task(name="resource_cloud.tasks.run_deprovisioning")
def run_deprovisioning(token, resource_id):
    logger.info('deprovisioning triggered for %s' % resource_id)

    run_pvc_deprovisioning(token, resource_id)

    logger.info('deprovisioning done, notifying server')
    resp = do_provisioned_resource_patch(token, resource_id, {'state': 'deleted'})

    if resp.status_code == 200:
        return 'ok'

    return 'error: %s %s' % (resp.status_code, resp.reason)


def do_provisioned_resource_patch(token, provisioned_resource_id, payload):
    auth = base64.encodestring('%s:%s' % (token, '')).replace('\n', '')
    headers = {'Content-type': 'application/x-www-form-urlencoded',
               'Accept': 'text/plain',
               'Authorization': 'Basic %s' % auth}
    url = 'https://localhost/api/v1/provisioned_resources/%s' % provisioned_resource_id
    resp = requests.patch(url, data=payload, headers=headers,
                          verify=config.SSL_VERIFY)
    logger.debug('got response %s %s' % (resp.status_code, resp.reason))
    return resp


def upload_provisioning_log(token, provisioned_resource_id, log_type, log_text):
    payload = {'text': log_text, 'type': log_type}
    auth = base64.encodestring('%s:%s' % (token, '')).replace('\n', '')
    headers = {'Content-type': 'application/x-www-form-urlencoded',
               'Accept': 'text/plain',
               'Authorization': 'Basic %s' % auth}
    url = 'https://localhost/api/v1/provisioned_resources/%s/logs' % provisioned_resource_id
    resp = requests.patch(url, data=payload, headers=headers,
                          verify=config.SSL_VERIFY)
    logger.debug('got response %s %s' % (resp.status_code, resp.reason))
    return resp


def create_prov_log_uploader(token, provisioned_resource_id, log_type):
    def uploader(text):
        upload_provisioning_log(token, provisioned_resource_id, log_type, text)

    return uploader


def do_get(token, object_url):
    auth = base64.encodestring('%s:%s' % (token, '')).replace('\n', '')
    headers = {'Accept': 'text/plain',
               'Authorization': 'Basic %s' % auth}

    url = 'https://localhost/api/v1/%s' % object_url
    resp = requests.get(url, headers=headers, verify=config.SSL_VERIFY)
    logger.debug('got response %s %s' % (resp.status_code, resp.reason))
    return resp


def get_provisioned_resource_data(token, provisioned_resource_id):
    resp = do_get(token, 'provisioned_resources/%s' % provisioned_resource_id)
    return resp


def get_resource_description(token, resource_id):
    return do_get(token, 'resources/%s' % resource_id)


def get_user_key_data(token, user_id):
    return do_get(token, 'users/%s/keypairs' % user_id)


def run_logged_process(cmd, cwd='.', shell=False, env=None, log_uploader=None):
    if shell:
        args = [cmd]
    else:
        args = shlex.split(cmd)

    p = subprocess.Popen(args, cwd=cwd, shell=shell, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env)
    poller = select.poll()
    poller.register(p.stdout)
    poller.register(p.stderr)
    log_buffer = []
    last_upload = time.time()
    with open('%s/pvc_stdout.log' % cwd, 'a') as stdout, open('%s/pvc_stderr.log' % cwd, 'a') as stderr:
        stdout_open = stderr_open = True
        while stdout_open or stderr_open:
            poll_results = poller.poll(500)
            for fd, mask in poll_results:
                if fd == p.stdout.fileno():
                    if mask & select.POLLIN > 0:
                        line = p.stdout.readline()
                        logger.debug('STDOUT: ' + line.strip('\n'))
                        stdout.write(line)
                        stdout.flush()
                        log_buffer.append('STDOUT %s' % line)
                    elif mask & select.POLLHUP > 0:
                        stdout_open = False

                elif fd == p.stderr.fileno():
                    if mask & select.POLLIN > 0:
                        line = p.stderr.readline()
                        logger.info('STDERR: ' + line.strip('\n'))
                        stderr.write(line)
                        stderr.flush()
                        if log_uploader:
                            log_buffer.append('STDERR %s' % line)

                    elif mask & select.POLLHUP > 0:
                        stderr_open = False

            if log_uploader and (last_upload < time.time() - 10 or len(log_buffer) > 100):
                if len(log_buffer) > 0:
                    log_uploader(''.join(log_buffer))
                    log_buffer = []
                    last_upload = time.time()

    if log_uploader and len(log_buffer) > 0:
        log_uploader(''.join(log_buffer))


def run_pvc_provisioning(token, provisioned_resource_id):
    resp = get_provisioned_resource_data(token, provisioned_resource_id)
    if resp.status_code != 200:
        raise RuntimeError('Cannot fetch data for provisioned_resource %s, %s' % (provisioned_resource_id, resp.reason))
    pr_data = resp.json()
    c_name = pr_data['name']

    res_dir = '%s/%s' % (config.PVC_CLUSTER_DATA_DIR, c_name)

    # will fail if there is already a directory for this resource
    os.makedirs(res_dir)

    # generate pvc config for this cluster
    resp = get_resource_description(token, pr_data['resource_id'])
    if resp.status_code != 200:
        raise RuntimeError('Cannot fetch data for resource %s, %s' % (pr_data['resource_id'], resp.reason))
    r_data = resp.json()
    tc = jinja2.Template(r_data['config'])
    conf = tc.render(cluster_name='rc-%s' % c_name, security_key='rc-%s' % c_name)
    with open('%s/cluster.yml' % res_dir, 'w') as cf:
        cf.write(conf)
        cf.write('\n')

    # figure out the number of nodes from config provisioning-data
    cluster_config=yaml.load(conf)
    if 'provisioning_data' in cluster_config.keys() and 'num_nodes' in cluster_config['provisioning_data'].keys():
        num_nodes=int(cluster_config['provisioning_data']['num_nodes'])
    else:
        logger.warn('number of nodes in cluster not defined, using default: 2')
        num_nodes=2

    # fetch user public key and save it
    key_data = get_user_key_data(token, pr_data['user_id']).json()
    user_key_file = '%s/userkey.pub' % res_dir
    if not key_data:
        do_provisioned_resource_patch(token, provisioned_resource_id, {'state': 'failed'})
        raise RuntimeError("User's public key missing")

    with open(user_key_file, 'w') as kf:
        kf.write(key_data[0]['public_key'])

    uploader = create_prov_log_uploader(token, provisioned_resource_id, log_type='provisioning')
    if not config.FAKE_PROVISIONING:
        # generate keypair for this cluster
        key_file = '%s/key.priv' % res_dir
        if not os.path.isfile(key_file):
            with open(key_file, 'w') as keyfile:
                args = ['nova', 'keypair-add', 'rc-%s' % c_name]
                p = subprocess.Popen(args, cwd=res_dir, stdout=keyfile)
                p.wait()
            os.chmod(key_file, stat.S_IRUSR)

        # run provisioning
        cmd = '/webapps/resource_cloud/venv/bin/python /opt/pvc/python/poutacluster.py up %d' % num_nodes
        logger.debug('spawning "%s"' % cmd)
        run_logged_process(cmd=cmd, cwd=res_dir, env=create_pvc_env(), log_uploader=uploader)

        # add user key for ssh access
        cmd = '/webapps/resource_cloud/venv/bin/python /opt/pvc/python/poutacluster.py add_key userkey.pub'
        logger.debug('spawning "%s"' % cmd)
        run_logged_process(cmd=cmd, cwd=res_dir, env=create_pvc_env(), log_uploader=uploader)

        # get public IP
        cmd = '/webapps/resource_cloud/venv/bin/python /opt/pvc/python/poutacluster.py info'
        p = subprocess.Popen(shlex.split(cmd), cwd=res_dir, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        out, err = p.communicate()
        public_ip = None
        for line in out.splitlines():
            line = line.strip()
            if line.startswith('public ip:'):
                public_ip = line.split(':')[1]
                break
        if public_ip:
            do_provisioned_resource_patch(token, provisioned_resource_id, {'public_ip': public_ip})

    else:
        logger.info('faking provisioning')
        cmd = 'time ping -c 10 localhost'
        run_logged_process(cmd=cmd, cwd=res_dir, shell=True, log_uploader=uploader)
        do_provisioned_resource_patch(token, provisioned_resource_id, {'public_ip': '%s.%s.%s.%s' % (
            randint(1, 254), randint(1, 254), randint(1, 254), randint(1, 254))})


def run_pvc_deprovisioning(token, provisioned_resource_id):
    resp = get_provisioned_resource_data(token, provisioned_resource_id)
    if resp.status_code != 200:
        raise RuntimeError('Cannot fetch data for resource %s, %s' % (provisioned_resource_id, resp.reason))
    r_data = resp.json()
    c_name = r_data['name']

    res_dir = '%s/%s' % (config.PVC_CLUSTER_DATA_DIR, c_name)

    uploader = create_prov_log_uploader(token, provisioned_resource_id, log_type='deprovisioning')
    if not config.FAKE_PROVISIONING:
        # run deprovisioning
        cmd = '/webapps/resource_cloud/venv/bin/python /opt/pvc/python/poutacluster.py down'
        run_logged_process(cmd=cmd, cwd=res_dir, env=create_pvc_env(), log_uploader=uploader)

        # clean generated security and server groups
        cmd = '/webapps/resource_cloud/venv/bin/python /opt/pvc/python/poutacluster.py cleanup'
        run_logged_process(cmd=cmd, cwd=res_dir, env=create_pvc_env(), log_uploader=uploader)

        # destroy volumes
        cmd = '/webapps/resource_cloud/venv/bin/python /opt/pvc/python/poutacluster.py destroy_volumes'
        run_logged_process(cmd=cmd, cwd=res_dir, env=create_pvc_env(), log_uploader=uploader)

        # remove generated key from OpenStack
        args = ['nova', 'keypair-delete', 'rc-%s' % c_name]
        p = subprocess.Popen(args, cwd=res_dir)
        p.wait()

    else:
        logger.info('faking deprovisioning')
        cmd = 'time ping -c 5 localhost'
        run_logged_process(cmd=cmd, cwd=res_dir, shell=True, log_uploader=uploader)

    # use resource id as a part of the name to make tombstones always unique
    os.rename(res_dir, '%s.deleted.%s' % (res_dir, provisioned_resource_id))


def create_pvc_env():
    env = os.environ.copy()
    env['PYTHONUNBUFFERED'] = '1'
    return env
