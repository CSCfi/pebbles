import base64
import requests


class PBClient(object):
    def __init__(self, token, api_base_url, ssl_verify=True):
        self.token = token
        self.api_base_url = api_base_url
        self.ssl_verify = ssl_verify
        self.auth = base64.encodestring('%s:%s' % (token, '')).replace('\n', '')

    def do_get(self, object_url, payload=None):
        headers = {'Accept': 'text/plain',
                   'Authorization': 'Basic %s' % self.auth}
        url = '%s/%s' % (self.api_base_url, object_url)
        resp = requests.get(url, data=payload, headers=headers, verify=self.ssl_verify)
        return resp

    def do_patch(self, object_url, payload):
        headers = {'Content-type': 'application/x-www-form-urlencoded',
                   'Accept': 'text/plain',
                   'Authorization': 'Basic %s' % self.auth}
        url = '%s/%s' % (self.api_base_url, object_url)
        resp = requests.patch(url, data=payload, headers=headers, verify=self.ssl_verify)
        return resp

    def do_post(self, object_url, payload=None):
        headers = {'Content-type': 'application/x-www-form-urlencoded',
                   'Accept': 'text/plain',
                   'Authorization': 'Basic %s' % self.auth}
        url = '%s/%s' % (self.api_base_url, object_url)
        resp = requests.post(url, data=payload, headers=headers, verify=self.ssl_verify)
        return resp

    def do_put(self, object_url, payload=None):
        headers = {'Content-type': 'application/x-www-form-urlencoded',
                   'Accept': 'text/plain',
                   'Authorization': 'Basic %s' % self.auth}
        url = '%s/%s' % (self.api_base_url, object_url)
        resp = requests.put(url, data=payload, headers=headers, verify=self.ssl_verify)
        return resp

    def do_delete(self, object_url):
        headers = {'Content-type': 'application/x-www-form-urlencoded',
                   'Accept': 'text/plain',
                   'Authorization': 'Basic %s' % self.auth}
        url = '%s/%s' % (self.api_base_url, object_url)
        resp = requests.delete(url, headers=headers, verify=self.ssl_verify)
        return resp

    def do_instance_patch(self, instance_id, payload):
        url = 'instances/%s' % instance_id
        resp = self.do_patch(url, payload)
        return resp

    def get_instance_description(self, instance_id):
        resp = self.do_get('instances/%s' % instance_id)
        if resp.status_code != 200:
            raise RuntimeError('Cannot fetch data for provisioned blueprints, %s' % resp.reason)
        return resp.json()

    def get_blueprint_description(self, blueprint_id):
        resp = self.do_get('blueprints/%s' % blueprint_id)
        if resp.status_code != 200:
            raise RuntimeError('Cannot fetch data for provisioned blueprints, %s' % resp.reason)
        return resp.json()

    def get_user_key_data(self, user_id):
        return self.do_get('users/%s/keypairs' % user_id)

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

    def get_instance_parent_data(self, instance_id):
        blueprint_id = self.get_instance(instance_id)['blueprint_id']

        resp = self.do_get('blueprints/%s' % blueprint_id)
        if resp.status_code != 200:
            raise RuntimeError('Error loading blueprint data: %s, %s' % (blueprint_id, resp.reason))

        return resp.json()

    def clear_running_instance_logs(self, instance_id):
        headers = {'Accept': 'text/plain',
                   'Authorization': 'Basic %s' % self.auth}
        url = '%s/instances/%s/logs' % (self.api_base_url, instance_id)
        params = {'log_type': 'running'}
        resp = requests.delete(url, params=params, headers=headers, verify=self.ssl_verify)
        if resp.status_code != 200:
            raise RuntimeError('Unable to delete running logs for instance %s, %s' % (instance_id, resp.reason))
        return resp

    def get_plugin_data(self, plugin_id):
        resp = self.do_get('plugins/%s' % plugin_id)
        if resp.status_code != 200:
            raise RuntimeError('Error loading plugin data: %s, %s' % (plugin_id, resp.reason))

        return resp.json()

    def obtain_lock(self, lock_id):
        resp = self.do_put('locks/%s' % lock_id)
        if resp.status_code == 200:
            return lock_id
        elif resp.status_code == 409:
            return None
        else:
            raise RuntimeError('Error obtaining lock: %s, %s' % (lock_id, resp.reason))

    def release_lock(self, lock_id):
        resp = self.do_delete('locks/%s' % lock_id)
        if resp.status_code == 200:
            return lock_id
        else:
            raise RuntimeError('Error deleting lock: %s, %s' % (lock_id, resp.reason))

    def get_namespaced_keyvalues(self, payload=None):
        resp = self.do_get('namespaced_keyvalues', payload)
        if resp.status_code == 200:
            return resp.json()
        else:
            raise RuntimeError('Error getting namespaced records: %s' % resp.reason)

    def get_namespaced_keyvalue(self, namespace, key):
        resp = self.do_get('namespaced_keyvalues/%s/%s' % (namespace, key))
        if resp.status_code == 200:
            return resp.json()
        return None

    def create_or_modify_namespaced_keyvalue(self, namespace, key, payload):
        headers = {'Accept': 'text/plain',
                   'Authorization': 'Basic %s' % self.auth}
        ns_record = self.get_namespaced_keyvalue(namespace, key)
        if not ns_record:
            url = '%s/%s' % (self.api_base_url, 'namespaced_keyvalues')
            resp = requests.post(url, json=payload, headers=headers, verify=self.ssl_verify)
        else:
            updated_version_ts = ns_record['updated_ts']
            payload['updated_version_ts'] = updated_version_ts
            url = '%s/%s/%s/%s' % (self.api_base_url, 'namespaced_keyvalues', namespace, key)
            resp = requests.put(url, json=payload, headers=headers, verify=self.ssl_verify)

        if resp.status_code == 200:
            return resp.json()
        else:
            raise RuntimeError('Error creating / modifying namespaced record: %s %s, %s' % (namespace, key, resp.reason))

    def delete_namespaced_keyvalue(self, namespace, key):
        headers = {'Accept': 'text/plain',
                   'Authorization': 'Basic %s' % self.auth}
        url = '%s/%s/%s/%s' % (self.api_base_url, 'namespaced_keyvalues', namespace, key)
        resp = requests.delete(url, headers=headers, verify=self.ssl_verify)
        if resp.status_code == 200:
            return resp.json()
        else:
            raise RuntimeError('Error deleting record: %s %s, %s' % (namespace, key, resp.reason))
