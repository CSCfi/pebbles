import base64
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
from resource_cloud.app import get_app
# from resource_cloud.config import BaseConfig as config
from resource_cloud.config import DevConfig as config

# config.FAKE_PROVISIONING = False

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

    update_resource_state(token, resource_id, 'provisioning')

    run_pvc_provisioning(token, resource_id)

    logger.info('provisioning done, notifying server')
    resp = update_resource_state(token, resource_id, 'running')

    if resp.status_code == 200:
        return 'ok'

    return 'error: %s %s' % (resp.status_code, resp.reason)


@app.task(name="resource_cloud.tasks.run_deprovisioning")
def run_deprovisioning(token, resource_id):
    logger.info('deprovisioning triggered for %s' % resource_id)

    run_pvc_deprovisioning(token, resource_id)

    logger.info('deprovisioning done, notifying server')
    resp = update_resource_state(token, resource_id, 'deleted')

    if resp.status_code == 200:
        return 'ok'

    return 'error: %s %s' % (resp.status_code, resp.reason)


def update_resource_state(token, resource_id, state):
    payload = {'state': state}
    auth = base64.encodestring('%s:%s' % (token, '')).replace('\n', '')
    headers = {'Content-type': 'application/x-www-form-urlencoded',
               'Accept': 'text/plain',
               'Authorization': 'Basic %s' % auth}
    url = 'https://localhost/api/v1/provisioned_resources/%s' % resource_id
    resp = requests.patch(url, data=payload, headers=headers,
                          verify=config.SSL_VERIFY)
    logger.info('got response %s %s' % (resp.status_code, resp.reason))
    return resp


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


def run_logged_process(cmd, cwd='.', shell=False, env=None):
    if shell:
        args = [cmd]
    else:
        args = shlex.split(cmd)

    p = subprocess.Popen(args, cwd=cwd, shell=shell, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env)
    poller = select.poll()
    poller.register(p.stdout)
    poller.register(p.stderr)
    with open('%s/pvc_stdout.log' % cwd, 'a') as stdout, open('%s/pvc_stderr.log' % cwd, 'a') as stderr:
        stdout_open = stderr_open = True
        while stdout_open or stderr_open:
            poll_results = poller.poll(500)
            for fd, mask in poll_results:
                if fd == p.stdout.fileno():
                    if mask & select.POLLIN > 0:
                        line = p.stdout.readline()
                        stdout.write(line)
                        logger.debug('STDOUT: ' + line.strip('\n'))
                    elif mask & select.POLLHUP > 0:
                        stdout_open = False

                elif fd == p.stderr.fileno():
                    if mask & select.POLLIN > 0:
                        line = p.stderr.readline()
                        stderr.write(line)
                        logger.info('STDERR: ' + line.strip('\n'))
                    elif mask & select.POLLHUP > 0:
                        stderr_open = False


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
    conf = tc.render(cluster_name='rc-%s' % c_name, security_key='rc-%s' % c_name, frontend_flavor='mini',
                     public_ip='86.50.169.98',
                     node_flavor='mini', )
    with open('%s/cluster.yml' % res_dir, 'w') as cf:
        cf.write(conf)
        cf.write('\n')

    # fetch user public key and save it
    key_data = get_user_key_data(token, pr_data['user_id']).json()
    user_key_file = '%s/userkey.pub' % res_dir
    if not key_data:
        update_resource_state(token, provisioned_resource_id, 'failed')
        raise RuntimeError("User's public key missing")

    with open(user_key_file, 'w') as kf:
        kf.write(key_data[0]['public_key'])

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
        cmd = '/webapps/resource_cloud/venv/bin/python /opt/pvc/python/poutacluster.py up 2'
        logger.debug('spawning "%s"' % cmd)
        run_logged_process(cmd=cmd, cwd=res_dir, env=create_pvc_env())

        # add user key for ssh access
        cmd = '/webapps/resource_cloud/venv/bin/python /opt/pvc/python/poutacluster.py add_key userkey.pub'
        logger.debug('spawning "%s"' % cmd)
        run_logged_process(cmd=cmd, cwd=res_dir, env=create_pvc_env())

    else:
        logger.info('faking provisioning')
        cmd = 'time ping -c 10 localhost'
        run_logged_process(cmd=cmd, cwd=res_dir, shell=True)


def run_pvc_deprovisioning(token, resource_id):
    resp = get_provisioned_resource_data(token, resource_id)
    if resp.status_code != 200:
        raise RuntimeError('Cannot fetch data for resource %s, %s' % (resource_id, resp.reason))
    r_data = resp.json()
    c_name = r_data['name']

    res_dir = '%s/%s' % (config.PVC_CLUSTER_DATA_DIR, c_name)

    if not config.FAKE_PROVISIONING:
        # run deprovisioning
        cmd = '/webapps/resource_cloud/venv/bin/python /opt/pvc/python/poutacluster.py down'
        run_logged_process(cmd=cmd, cwd=res_dir, env=create_pvc_env())

        # clean generated security and server groups
        cmd = '/webapps/resource_cloud/venv/bin/python /opt/pvc/python/poutacluster.py cleanup'
        run_logged_process(cmd=cmd, cwd=res_dir, env=create_pvc_env())

        # destroy volumes
        cmd = '/webapps/resource_cloud/venv/bin/python /opt/pvc/python/poutacluster.py destroy_volumes'
        run_logged_process(cmd=cmd, cwd=res_dir, env=create_pvc_env())

    else:
        logger.info('faking deprovisioning')
        cmd = 'time ping -c 5 localhost'
        run_logged_process(cmd=cmd, cwd=res_dir, shell=True)

    # use resource id as a part of the name to make tombstones always unique
    os.rename(res_dir, '%s.deleted.%s' % (res_dir, resource_id))


def create_pvc_env():
    env = os.environ.copy()
    env['PYTHONUNBUFFERED'] = '1'
    return env
