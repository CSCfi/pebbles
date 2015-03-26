import base64
import select
import shlex
import json
import subprocess
import time
import os

import abc
import six
import requests

from pouta_blueprints.config import DevConfig as ActiveConfig


@six.add_metaclass(abc.ABCMeta)
class ProvisioningDriverBase(object):
    config = {}

    def __init__(self, logger, config):
        self.logger = logger
        self.config = config

        m2m_credential_store = getattr(self.config, 'M2M_CREDENTIAL_STORE')
        try:
            self.m2m_credentials = json.load(open(m2m_credential_store))
        except (IOError, ValueError) as e:
            self.logger.warn("Unable to read/parse M2M credentials from path %s %s" % (m2m_credential_store, e))

    def get_configuration(self):
        return {
            'schema': {
                'type': 'object',
                'properties': {
                    'name': {
                        'type': 'string'
                    }
                },
            },
            'form': [
                {'type': 'help', 'helpvalue': 'config is empty'},
                '*',
                {'style': 'btn-info', 'title': 'Create', 'type': 'submit'}
            ], 'model': {}}

    def update_connectivity(self, token, instance_id):
        self.logger.debug('update connectivity')
        self.do_update_connectivity(token, instance_id)

    def provision(self, token, instance_id):
        self.logger.debug('starting provisioning')
        self.do_instance_patch(token, instance_id, {'state': 'provisioning'})

        try:
            self.logger.debug('calling subclass do_provision')
            self.do_provision(token, instance_id)

            self.logger.debug('finishing provisioning')
            self.do_instance_patch(token, instance_id, {'state': 'running'})
        except Exception as e:
            self.logger.debug('do_provision raised %s' % e)
            self.do_instance_patch(token, instance_id, {'state': 'failed'})
            raise e

    def deprovision(self, token, instance_id):
        self.logger.debug('starting deprovisioning')
        self.do_instance_patch(token, instance_id, {'state': 'deprovisioning'})
        try:
            self.logger.debug('calling subclass do_deprovision')
            self.do_deprovision(token, instance_id)

            self.logger.debug('finishing deprovisioning')
            self.do_instance_patch(token, instance_id, {'state': 'deleted'})
        except Exception as e:
            self.logger.debug('do_deprovision raised %s' % e)
            self.do_instance_patch(token, instance_id, {'state': 'failed'})
            raise e

    @abc.abstractmethod
    def do_update_connectivity(self, token, instance_id):
        pass

    @abc.abstractmethod
    def do_provision(self, token, instance_id):
        pass

    @abc.abstractmethod
    def do_deprovision(self, token, instance_id):
        pass

    def do_instance_patch(self, token, instance_id, payload):
        auth = base64.encodestring('%s:%s' % (token, '')).replace('\n', '')
        headers = {'Content-type': 'application/x-www-form-urlencoded',
                   'Accept': 'text/plain',
                   'Authorization': 'Basic %s' % auth}
        url = '%s/instances/%s' % (ActiveConfig.INTERNAL_API_BASE_URL, instance_id)
        resp = requests.patch(url, data=payload, headers=headers,
                              verify=self.config.SSL_VERIFY)
        self.logger.debug('got response %s %s' % (resp.status_code, resp.reason))
        return resp

    def upload_provisioning_log(self, token, instance_id, log_type, log_text):
        payload = {'text': log_text, 'type': log_type}
        auth = base64.encodestring('%s:%s' % (token, '')).replace('\n', '')
        headers = {'Content-type': 'application/x-www-form-urlencoded',
                   'Accept': 'text/plain',
                   'Authorization': 'Basic %s' % auth}
        url = '%s/instances/%s/logs' % (ActiveConfig.INTERNAL_API_BASE_URL, instance_id)
        resp = requests.patch(url, data=payload, headers=headers,
                              verify=self.config.SSL_VERIFY)
        self.logger.debug('got response %s %s' % (resp.status_code, resp.reason))
        return resp

    def create_prov_log_uploader(self, token, instance_id, log_type):
        def uploader(text):
            self.upload_provisioning_log(token, instance_id, log_type, text)

        return uploader

    def do_get(self, token, object_url):
        auth = base64.encodestring('%s:%s' % (token, '')).replace('\n', '')
        headers = {'Accept': 'text/plain',
                   'Authorization': 'Basic %s' % auth}

        url = '%s/%s' % (ActiveConfig.INTERNAL_API_BASE_URL, object_url)
        resp = requests.get(url, headers=headers, verify=self.config.SSL_VERIFY)
        self.logger.debug('got response %s %s' % (resp.status_code, resp.reason))
        return resp

    def get_instance_data(self, token, instance_id):
        resp = self.do_get(token, 'instances/%s' % instance_id)
        if resp.status_code != 200:
            raise RuntimeError('Cannot fetch data for provisioned blueprints, %s' % resp.reason)
        return resp.json()

    def get_blueprint_description(self, token, blueprint_id):
        resp = self.do_get(token, 'blueprints/%s' % blueprint_id)
        if resp.status_code != 200:
            raise RuntimeError('Cannot fetch data for provisioned blueprints, %s' % resp.reason)
        return resp.json()

    def get_user_key_data(self, token, user_id):
        return self.do_get(token, 'users/%s/keypairs' % user_id)

    def run_logged_process(self, cmd, cwd='.', shell=False, env=None, log_uploader=None):
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
        with open('%s/instance_stdout.log' % cwd, 'a') as stdout, open('%s/instance__stderr.log' % cwd, 'a') as stderr:
            stdout_open = stderr_open = True
            while stdout_open or stderr_open:
                poll_results = poller.poll(500)
                for fd, mask in poll_results:
                    if fd == p.stdout.fileno():
                        if mask & select.POLLIN > 0:
                            line = p.stdout.readline()
                            self.logger.debug('STDOUT: ' + line.strip('\n'))
                            stdout.write(line)
                            stdout.flush()
                            log_buffer.append('STDOUT %s' % line)
                        elif mask & select.POLLHUP > 0:
                            stdout_open = False

                    elif fd == p.stderr.fileno():
                        if mask & select.POLLIN > 0:
                            line = p.stderr.readline()
                            self.logger.info('STDERR: ' + line.strip('\n'))
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

    def create_openstack_env(self):
        env = os.environ.copy()
        for key in ('OS_USERNAME', 'OS_PASSWORD', 'OS_TENANT_ID', 'OS_AUTH_URL'):
            if key in self.m2m_credentials:
                env[key] = self.m2m_credentials[key]
        env['PYTHONUNBUFFERED'] = '1'
        env['ANSIBLE_HOST_KEY_CHECKING'] = '0'
        return env
