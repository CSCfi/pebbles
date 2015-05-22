import unittest
import base64
import json

from pouta_blueprints.tests.base import db, BaseTestCase
from pouta_blueprints.models import User, Blueprint, Plugin, ActivationToken, Instance


class FlaskApiTestCase(BaseTestCase):
    def setUp(self):
        self.methods = {
            'GET': self.client.get,
            'POST': self.client.post,
            'PUT': self.client.put,
            'PATCH': self.client.patch,
            'DELETE': self.client.delete,
        }
        db.create_all()
        u1 = User("admin@example.org", "admin", is_admin=True)
        u2 = User("user@example.org", "user", is_admin=False)
        self.known_user_id = u2.id

        db.session.add(u1)
        db.session.add(u2)
        p1 = Plugin()
        p1.name = "TestPlugin"
        self.known_plugin_id = p1.id
        db.session.add(p1)

        b1 = Blueprint()
        b1.name = "TestBlueprint"
        b1.plugin = p1.id
        db.session.add(b1)

        b2 = Blueprint()
        b2.name = "EnabledTestBlueprint"
        b2.plugin = p1.id
        b2.is_enabled = True
        db.session.add(b2)
        self.known_blueprint_id = b2.id

        b3 = Blueprint()
        b3.name = "EnabledTestBlueprintClientIp"
        b3.plugin = p1.id
        b3.is_enabled = True
        b3.config = {'allow_update_client_connectivity': True}
        db.session.add(b3)
        self.known_blueprint_id_2 = b3.id

        db.session.commit()

        i1 = Instance(
            Blueprint.query.filter_by(id=b2.id).first(),
            User.query.filter_by(email="user@example.org").first())
        db.session.add(i1)
        self.known_instance_id = i1.id

        i2 = Instance(
            Blueprint.query.filter_by(id=b3.id).first(),
            User.query.filter_by(email="user@example.org").first())
        db.session.add(i2)
        self.known_instance_id_2 = i2.id

        db.session.commit()

    def make_request(self, method='GET', path='/', headers=None, data=None):
        assert method in self.methods

        if not headers:
            headers = {}

        if 'Content-Type' not in headers:
            headers['Content-Type'] = 'application/json'

        headers = [(x, y) for x, y in headers.items()]
        return self.methods[method](path, headers=headers, data=data, content_type='application/json')

    def make_authenticated_request(self, method='GET', path='/', headers=None, data=None, creds=None):
        assert creds is not None

        assert method in self.methods

        if not headers:
            headers = {}

        response = self.make_request('POST', '/api/v1/sessions',
                                     headers=headers,
                                     data=json.dumps(creds))
        token = '%s:' % response.json['token']
        token_b64 = base64.b64encode(bytes(token.encode('ascii'))).decode('utf-8')

        headers.update({
            'Accept': 'application/json',
            'Authorization': 'Basic %s' % token_b64,
            'token': token_b64
        })
        return self.methods[method](path, headers=headers, data=data, content_type='application/json')

    def make_authenticated_admin_request(self, method='GET', path='/', headers=None, data=None):
        return self.make_authenticated_request(method, path, headers, data,
                                               creds={'email': 'admin@example.org', 'password': 'admin'})

    def make_authenticated_user_request(self, method='GET', path='/', headers=None, data=None):
        return self.make_authenticated_request(method, path, headers, data,
                                               creds={'email': 'user@example.org', 'password': 'user'})

    def test_first_user(self):
        db.drop_all()
        db.create_all()
        response = self.make_request(
            'POST',
            '/api/v1/initialize',
            data=json.dumps({'email': 'admin@example.org',
                             'password': 'admin'}))
        self.assert_200(response)

    def test_deleted_user_cannot_get_token(self):
        response = self.make_request(
            method='POST',
            path='/api/v1/sessions',
            data=json.dumps({'email': 'user@example.org', 'password': 'user'}))
        self.assert_200(response)
        response = self.make_authenticated_admin_request(
            method='DELETE',
            path='/api/v1/users/%s' % self.known_user_id
        )
        response = self.make_request(
            method='POST',
            path='/api/v1/sessions',
            data=json.dumps({'email': 'user@example.org', 'password': 'user'}))
        self.assert_401(response)

    def test_a_deleted_user_cannot_use_token(self):
        response = self.make_request(
            method='POST',
            path='/api/v1/sessions',
            data=json.dumps({'email': 'user@example.org', 'password': 'user'}))
        self.assert_200(response)

        token = '%s:' % response.json['token']
        token_b64 = base64.b64encode(bytes(token.encode('ascii'))).decode('utf-8')

        headers = {
            'Accept': 'application/json',
            'Authorization': 'Basic %s' % token_b64,
            'token': token_b64
        }
        # Test instance creation still works for the user
        response = self.make_request(
            method='POST',
            path='/api/v1/instances',
            data=json.dumps({'blueprint': self.known_blueprint_id}),
            headers=headers)
        self.assert_200(response)
        # Delete the user with admin credentials
        response = self.make_authenticated_admin_request(
            method='DELETE',
            path='/api/v1/users/%s' % self.known_user_id
        )
        # Test instance creation fails for the user
        response = self.make_request(
            method='POST',
            path='/api/v1/instances',
            data=json.dumps({'blueprint': self.known_blueprint_id}),
            headers=headers)
        self.assert_401(response)

    def test_anonymous_delete_user(self):
        u = User("test@example.org", "testuser", is_admin=False)
        db.session.add(u)
        db.session.commit()

        response = self.make_request(
            method='DELETE',
            path='/api/v1/users/%s' % u.id
        )
        self.assert_401(response)

    def test_user_delete_user(self):
        u = User("test@example.org", "testuser", is_admin=False)
        db.session.add(u)
        db.session.commit()

        response = self.make_authenticated_user_request(
            method='DELETE',
            path='/api/v1/users/%s' % u.id
        )
        self.assert_403(response)

    def test_admin_delete_user(self):
        email = "test@example.org"
        u = User(email, "testuser", is_admin=False)
        db.session.add(u)
        db.session.commit()

        response = self.make_authenticated_admin_request(
            method='DELETE',
            path='/api/v1/users/%s' % u.id
        )
        self.assert_200(response)
        user = User.query.filter_by(id=u.id).first()
        self.assertTrue(user.email != email)

    def test_anonymous_get_users(self):
        response = self.make_request(path='/api/v1/users')
        self.assert_401(response)

    def test_user_get_users(self):
        response = self.make_authenticated_user_request(path='/api/v1/users')
        self.assertEqual(len(response.json), 1)
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

    def test_anonymous_get_blueprints(self):
        response = self.make_request(path='/api/v1/blueprints')
        self.assert_401(response)

    def test_user_get_blueprints(self):
        response = self.make_authenticated_user_request(path='/api/v1/blueprints')
        self.assert_200(response)
        self.assertEqual(len(response.json), 2)

    def test_admin_get_blueprints(self):
        response = self.make_authenticated_admin_request(path='/api/v1/blueprints')
        self.assert_200(response)
        self.assertEqual(len(response.json), 3)

    def test_anonymous_create_blueprint(self):
        data = {'name': 'test_blueprint_1', 'config': '', 'plugin': 'dummy'}
        response = self.make_request(
            method='POST',
            path='/api/v1/blueprints',
            data=json.dumps(data))
        self.assert_401(response)

    def test_create_blueprint_user(self):
        data = {'name': 'test_blueprint_1', 'config': '', 'plugin': 'dummy'}
        response = self.make_authenticated_user_request(
            method='POST',
            path='/api/v1/blueprints',
            data=json.dumps(data))
        self.assert_403(response)

    def test_create_blueprint_admin(self):
        data = {'name': 'test_blueprint_1', 'config': 'foo: bar', 'plugin': 'dummy'}
        response = self.make_authenticated_admin_request(
            method='POST',
            path='/api/v1/blueprints',
            data=json.dumps(data))
        self.assert_200(response)

    def test_create_blueprint_admin_invalid_data(self):
        invalid_form_data = [
            {'name': '', 'config': 'foo: bar', 'plugin': 'dummy'},
            {'name': 'test_blueprint_2', 'config': '', 'plugin': 'dummy'},
            {'name': 'test_blueprint_2', 'config': 'foo: bar', 'plugin': ''},
        ]
        for data in invalid_form_data:
            response = self.make_authenticated_admin_request(
                method='POST',
                path='/api/v1/blueprints',
                data=json.dumps(data))
            self.assertStatus(response, 422)

    def test_anonymous_invite_user(self):
        data = {'email': 'test@example.org', 'password': 'test', 'is_admin': True}
        response = self.make_request(
            method='POST',
            path='/api/v1/users',
            data=json.dumps(data))
        self.assert_401(response)

    def test_user_invite_user(self):
        data = {'email': 'test@example.org', 'password': 'test', 'is_admin': True}
        response = self.make_authenticated_user_request(
            method='POST',
            path='/api/v1/users',
            data=json.dumps(data))
        self.assert_403(response)

    def test_admin_invite_user(self):
        data = {'email': 'test@example.org', 'password': 'test', 'is_admin': True}
        response = self.make_authenticated_admin_request(
            method='POST',
            path='/api/v1/users',
            data=json.dumps(data))
        self.assert_200(response)
        user = User.query.filter_by(email='test@example.org').first()
        self.assertIsNotNone(user)
        self.assertTrue(user.is_admin)

    def test_accept_invite(self):
        user = User.query.filter_by(email='test@example.org').first()
        self.assertIsNone(user)
        data = {'email': 'test@example.org', 'password': None, 'is_admin': True}
        response = self.make_authenticated_admin_request(
            method='POST',
            path='/api/v1/users',
            data=json.dumps(data))
        self.assert_200(response)
        user = User.query.filter_by(email='test@example.org').first()
        self.assertIsNotNone(user)
        self.assertFalse(user.is_active)
        token = ActivationToken.query.filter_by(user_id=user.id).first()
        self.assertIsNotNone(token)
        data = {'password': 'testtest'}
        response = self.make_request(
            method='POST',
            path='/api/v1/activations/%s' % token.token,
            data=json.dumps(data))
        self.assert_200(response)
        user = User.query.filter_by(email='test@example.org').first()
        self.assertIsNotNone(user)
        self.assertTrue(user.is_active)

    def test_anonymous_create_instance(self):
        data = {'blueprint_id': self.known_blueprint_id}
        response = self.make_request(
            method='POST',
            path='/api/v1/instances',
            data=json.dumps(data))
        self.assert_401(response)

    def test_user_create_instance(self):
        data = {'blueprint': self.known_blueprint_id}
        response = self.make_authenticated_user_request(
            method='POST',
            path='/api/v1/instances',
            data=json.dumps(data))
        self.assert_200(response)

    def test_anonymous_update_client_ip(self):
        data = {'client_ip': '1.1.1.1'}
        response = self.make_request(
            method='PATCH',
            path='/api/v1/instances/%s' % self.known_instance_id_2,
            data=json.dumps(data))
        self.assert_401(response)

    def test_update_client_ip(self):
        # first test with an instance from a blueprint that does not allow setting client ip
        data = {'client_ip': '1.1.1.1'}
        response = self.make_authenticated_user_request(
            method='PUT',
            path='/api/v1/instances/%s' % self.known_instance_id,
            data=json.dumps(data))
        self.assert_400(response)

        # then a positive test case
        data = {'client_ip': '1.1.1.1'}
        response = self.make_authenticated_user_request(
            method='PUT',
            path='/api/v1/instances/%s' % self.known_instance_id_2,
            data=json.dumps(data))
        self.assert_200(response)

        # test illegal ips
        for ip in ['1.0.0.0.0', '256.0.0.1', 'a.1.1.1', '10.10.10.']:
            data = {'client_ip': ip}
            response = self.make_authenticated_user_request(
                method='PUT',
                path='/api/v1/instances/%s' % self.known_instance_id_2,
                data=json.dumps(data))
            self.assertStatus(response, 422)

    def test_anonymous_get_instances(self):
        response = self.make_request(path='/api/v1/instances')
        self.assert_401(response)

    def test_user_get_instances(self):
        response = self.make_authenticated_user_request(path='/api/v1/instances')
        self.assert_200(response)
        self.assertEqual(len(response.json), 2)

    def test_admin_get_instances(self):
        response = self.make_authenticated_admin_request(path='/api/v1/instances')
        self.assert_200(response)
        self.assertEqual(len(response.json), 2)

    def test_anonymous_get_instance(self):
        response = self.make_request(path='/api/v1/instances/%s' % self.known_instance_id)
        self.assert_401(response)

    def test_user_get_instance(self):
        response = self.make_authenticated_user_request(path='/api/v1/instances/%s' % self.known_instance_id)
        self.assert_200(response)

    def test_admin_get_instance(self):
        response = self.make_authenticated_admin_request(path='/api/v1/instances/%s' % self.known_instance_id)
        self.assert_200(response)

    def test_anonymous_get_keypairs(self):
        response = self.make_request(path='/api/v1/users/%s/keypairs' % self.known_user_id)
        self.assert_401(response)
        response2 = self.make_request(path='/api/v1/users/%s/keypairs' % '0xBogus')
        self.assert_401(response2)

    def test_user_get_keypairs(self):
        response = self.make_authenticated_user_request(path='/api/v1/users/%s/keypairs' % self.known_user_id)
        self.assert_200(response)
        self.assertEqual(len(response.json), 0)
        response2 = self.make_authenticated_user_request(path='/api/v1/users/%s/keypairs' % '0xBogus')
        self.assert_403(response2)

    def test_admin_get_keypairs(self):
        response = self.make_authenticated_admin_request(path='/api/v1/users/%s/keypairs' % self.known_user_id)
        self.assert_200(response)
        self.assertEqual(len(response.json), 0)
        response2 = self.make_authenticated_admin_request(path='/api/v1/users/%s/keypairs' % '0xBogus')
        self.assert_404(response2)

    def test_anonymous_what_is_my_ip(self):
        response = self.make_request(path='/api/v1/what_is_my_ip')
        self.assert_401(response)

    def test_what_is_my_ip(self):
        response = self.make_authenticated_user_request(path='/api/v1/what_is_my_ip')
        self.assert_200(response)


if __name__ == '__main__':
    unittest.main()
