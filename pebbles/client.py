import json
import logging
from time import time

import requests
from jose import jwt

import pebbles.utils


class PBClient:
    def __init__(self, token, api_base_url, ssl_verify=True):
        self.token = token
        self.api_base_url = api_base_url
        self.ssl_verify = ssl_verify
        self.auth = pebbles.utils.b64encode_string('%s:%s' % (token, '')).replace('\n', '')

    def check_and_refresh_session(self, ext_id, password):
        # renew worker session 15 minutes before expiration
        try:
            claims = jwt.get_unverified_claims(self.token)
            remaining_time = claims['exp'] - time()
            if remaining_time < 900:
                logging.info("Token will expire soon, relogin %s" % ext_id)
                self.login(ext_id, password)
        except Exception as e:
            logging.warning(e)

    def login(self, ext_id, password):
        auth_url = '%s/sessions' % self.api_base_url
        auth_credentials = {
            'ext_id': ext_id,
            'password': password
        }
        r = requests.post(auth_url, auth_credentials, verify=self.ssl_verify)
        self.token = json.loads(r.text).get('token')
        self.auth = pebbles.utils.b64encode_string('%s:%s' % (self.token, '')).replace('\n', '')

    def do_get(self, object_url, payload=None):
        headers = {'Accept': 'text/plain',
                   'Authorization': 'Basic %s' % self.auth}
        url = '%s/%s' % (self.api_base_url, object_url)
        resp = requests.get(url, data=payload, headers=headers, verify=self.ssl_verify)
        return resp

    modify_methods = dict(
        post=requests.post,
        put=requests.put,
        patch=requests.patch,
        delete=requests.delete
    )

    def do_modify(self, method, object_url, form_data=None, json_data=None):
        content_type = 'application/x-www-form-urlencoded' if form_data else 'application/json'

        headers = {
            'Content-type': content_type,
            'Accept': 'text/plain',
            'Authorization': 'Basic %s' % self.auth}
        url = '%s/%s' % (self.api_base_url, object_url)
        resp = self.modify_methods[method](url, data=form_data, json=json_data, headers=headers, verify=self.ssl_verify)
        return resp

    def do_patch(self, object_url, form_data=None, json_data=None):
        return self.do_modify(method='patch', object_url=object_url, form_data=form_data, json_data=json_data)

    def do_post(self, object_url, form_data=None, json_data=None):
        return self.do_modify(method='post', object_url=object_url, form_data=form_data, json_data=json_data)

    def do_put(self, object_url, form_data=None, json_data=None):
        return self.do_modify(method='put', object_url=object_url, form_data=form_data, json_data=json_data)

    def do_delete(self, object_url, form_data=None, json_data=None):
        return self.do_modify(method='delete', object_url=object_url, form_data=form_data, json_data=json_data)

    def do_instance_patch(self, instance_id, form_data=None, json_data=None):
        url = 'instances/%s' % instance_id
        resp = self.do_patch(url, form_data=form_data, json_data=json_data)
        return resp

    def get_user(self, user_id):
        resp = self.do_get('users/%s' % user_id)
        if resp.status_code != 200:
            raise RuntimeError('Cannot fetch data for user %s, %s' % (user_id, resp.reason))
        return resp.json()

    def get_workspace_user_associations(self, workspace_id=None, user_id=None):
        if user_id:
            resp = self.do_get('users/%s/workspace_associations' % user_id)
        elif workspace_id:
            raise NotImplementedError('Fetching with workspace_id not implemented yet')
        else:
            raise RuntimeError('get_workspace_user_associations() needs either workspace_id or user_id')

        if resp.status_code != 200:
            raise RuntimeError('Cannot fetch data for workspace_user_associations %s, %s' % (user_id, resp.reason))

        return resp.json()

    def get_instances(self):
        resp = self.do_get('instances')
        if resp.status_code != 200:
            raise RuntimeError('Cannot fetch data for instances, %s' % resp.reason)
        return resp.json()

    def get_instance(self, instance_id):
        resp = self.do_get('instances/%s' % instance_id)
        if resp.status_code != 200:
            raise RuntimeError('Cannot fetch data for instances %s, %s' % (instance_id, resp.reason))
        return resp.json()

    def get_instance_environment(self, instance_id):
        environment_id = self.get_instance(instance_id)['environment_id']

        # try to get all environments to cover the case where the environment has been just archived
        resp = self.do_get('environments/%s?show_all=1' % environment_id)
        if resp.status_code != 200:
            raise RuntimeError('Error loading environment data: %s, %s' % (environment_id, resp.reason))

        return resp.json()

    def add_provisioning_log(self, instance_id, message, timestamp=None, log_type='provisioning', log_level='info'):
        payload = dict(
            log_record=dict(
                timestamp=timestamp if timestamp else time(),
                log_type=log_type,
                log_level=log_level,
                message=message
            )
        )
        self.do_patch('instances/%s/logs' % instance_id, json_data=payload)

    def update_instance_running_logs(self, instance_id, logs):
        payload = dict(
            log_record=dict(
                log_type='running',
                log_level='INFO',
                timestamp=time(),
                message=logs
            )
        )
        self.do_patch('instances/%s/logs' % instance_id, json_data=payload)

    def clear_running_instance_logs(self, instance_id):
        headers = {'Accept': 'text/plain',
                   'Authorization': 'Basic %s' % self.auth}
        url = '%s/instances/%s/logs' % (self.api_base_url, instance_id)
        params = {'log_type': 'running'}
        resp = requests.delete(url, params=params, headers=headers, verify=self.ssl_verify)
        if resp.status_code != 200:
            raise RuntimeError('Unable to delete running logs for instance %s, %s' % (instance_id, resp.reason))
        return resp

    def query_locks(self, lock_id=None):
        if lock_id:
            resp = self.do_get('locks/%s' % lock_id)
        else:
            resp = self.do_get('locks')

        if resp.status_code == 200:
            return resp.json()
        if resp.status_code == 404:
            return None

        raise RuntimeError('Error querying lock: %s, %s' % (lock_id, resp.reason))

    def obtain_lock(self, lock_id, owner):
        resp = self.do_put('locks/%s' % lock_id, json_data=dict(owner=owner))
        if resp.status_code == 200:
            return lock_id
        if resp.status_code == 409:
            return None

        raise RuntimeError('Error obtaining lock: %s, %s' % (lock_id, resp.reason))

    def release_lock(self, lock_id, owner=None):
        if owner:
            resp = self.do_delete('locks/%s?owner=%s' % (lock_id, owner))
        else:
            resp = self.do_delete('locks/%s' % lock_id)
        if resp.status_code == 200:
            return lock_id

        raise RuntimeError('Error deleting lock: %s, %s' % (lock_id, resp.reason))
