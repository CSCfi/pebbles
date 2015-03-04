import unittest
import base64
import json

from resource_cloud.tests.base import db, BaseTestCase
from resource_cloud.models import User, Resource, Plugin


class FlaskApiTestCase(BaseTestCase):
    def setUp(self):
        db.create_all()
        db.session.add(User("admin@admin.com", "admin", is_admin=True))
        db.session.add(User("user@user.com", "user", is_admin=False))
        p1 = Plugin()
        p1.name = "TestPlugin"
        self.known_plugin_id = p1.visual_id
        db.session.add(p1)

        r1 = Resource()
        r1.name = "TestResource"
        r1.plugin = p1.visual_id
        r2 = Resource()
        r2.name = "EnabledTestResource"
        r2.plugin = p1.visual_id
        r2.is_enabled = True
        db.session.add(r1)
        db.session.add(r2)
        db.session.commit()

    def make_request(self, method='GET', path='/', headers={}, data=None):
        methods = {
            'GET': self.client.get,
            'POST': self.client.post
        }

        assert method in methods

        if 'Content-Type' not in headers:
            headers['Content-Type'] = 'application/json'

        headers = [(x, y) for x, y in headers.items()]
        return methods[method](path, headers=headers, data=data)

    def make_authenticated_request(self, method='GET', path='/', headers={}, data=None, creds=None):
        assert creds is not None

        methods = {
            'GET': self.client.get,
            'POST': self.client.post
        }

        assert method in methods

        response = self.make_request('POST', '/api/v1/sessions',
                                     headers=headers,
                                     data=json.dumps(creds))
        token = '%s:' % response.json['token']
        token_b64 = base64.b64encode(bytes(token.encode('ascii'))).decode('utf-8')

        headers = {
            'Accept': 'application/json',
            'Authorization': 'Basic %s' % token_b64,
            'token': token_b64
        }
        return methods[method](path, headers=headers, data=data)

    def make_authenticated_admin_request(self, method='GET', path='/', headers={}, data=None):
        return self.make_authenticated_request(method, path, headers, data, creds={'email': 'admin@admin.com', 'password': 'admin'})

    def make_authenticated_user_request(self, method='GET', path='/', headers={}, data=None):
        return self.make_authenticated_request(method, path, headers, data, creds={'email': 'user@user.com', 'password': 'user'})

    def test_first_user(self):
        db.drop_all()
        db.create_all()
        response = self.make_request('POST',
                                     '/api/v1/initialize',
                                     data=json.dumps({'email': 'admin@admin.com',
                                                      'password': 'admin'}))
        self.assert_200(response)

    def test_anonymous_get_users(self):
        response = self.make_request(path='/api/v1/users')
        self.assert_401(response)

    def test_user_get_users(self):
        response = self.make_authenticated_user_request(path='/api/v1/users')
        self.assertEqual(len(json.loads(response.data)), 1)
        self.assert_200(response)

    def test_admin_get_users(self):
        response = self.make_authenticated_admin_request(path='/api/v1/users')
        self.assert_200(response)

    def test_anonymous_get_plugins(self):
        response = self.make_request(path='/api/v1/plugins')
        self.assert_401(response)

    def test_user_get_plugins(self):
        response = self.make_authenticated_user_request(path='/api/v1/plugins')
        self.assert_403(response)

    def test_admin_get_plugins(self):
        response = self.make_authenticated_admin_request(path='/api/v1/plugins')
        self.assert_200(response)

    def test_anonymous_get_single_plugin(self):
        response = self.make_request(path='/api/v1/plugins/%s' % self.known_plugin_id)
        self.assert_401(response)

    def test_authenticated_user_get_single_plugin(self):
        response = self.make_authenticated_user_request(path='/api/v1/plugins/%s' % self.known_plugin_id)
        self.assert_403(response)

    def test_authenticated_admin_get_single_plugin(self):
        response = self.make_authenticated_admin_request(path='/api/v1/plugins/%s' % self.known_plugin_id)
        self.assert_200(response)

    def test_anonymous_get_resources(self):
        response = self.make_request(path='/api/v1/resources')
        self.assert_401(response)
        self.assert_401(response)

    def test_user_get_resources(self):
        response = self.make_authenticated_user_request(path='/api/v1/resources')
        self.assert_200(response)
        resources = json.loads(response.data)
        self.assertEqual(len(resources), 1)

    def test_admin_get_resources(self):
        response = self.make_authenticated_admin_request(path='/api/v1/resources')
        self.assert_200(response)
        resources = json.loads(response.data)
        self.assertEqual(len(resources), 2)

if __name__ == '__main__':
    unittest.main()
