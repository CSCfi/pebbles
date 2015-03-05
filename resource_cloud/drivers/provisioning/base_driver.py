import base64
import select
import shlex
import subprocess
import time
import os

import abc
import six
import requests


@six.add_metaclass(abc.ABCMeta)
class ProvisioningDriverBase(object):
    config = {}

    def __init__(self, logger, config):
        self.config = config
        self.logger = logger

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
        url = 'https://localhost/api/v1/instances/%s' % instance_id
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
        url = 'https://localhost/api/v1/instances/%s/logs' % instance_id
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

        url = 'https://localhost/api/v1/%s' % object_url
        resp = requests.get(url, headers=headers, verify=self.config.SSL_VERIFY)
        self.logger.debug('got response %s %s' % (resp.status_code, resp.reason))
        return resp

    def get_instance_data(self, token, instance_id):
        resp = self.do_get(token, 'instances/%s' % instance_id)
        if resp.status_code != 200:
            raise RuntimeError('Cannot fetch data for provisioned resources, %s' % resp.reason)
        return resp.json()

    def get_resource_description(self, token, resource_id):
        resp = self.do_get(token, 'resources/%s' % resource_id)
        if resp.status_code != 200:
            raise RuntimeError('Cannot fetch data for provisioned resources, %s' % resp.reason)
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
        with open('%s/pvc_stdout.log' % cwd, 'a') as stdout, open('%s/pvc_stderr.log' % cwd, 'a') as stderr:
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

    @staticmethod
    def create_pvc_env():
        env = os.environ.copy()
        env['PYTHONUNBUFFERED'] = '1'
        return env
