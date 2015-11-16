import unittest
import datetime
import base64
import json
import uuid

from pouta_blueprints.tests.base import db, BaseTestCase
from pouta_blueprints.models import User, Blueprint, Plugin, ActivationToken, Instance, Variable
from pouta_blueprints.config import BaseConfig

ADMIN_TOKEN = None
USER_TOKEN = None


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

        # Fix user IDs to be the same for all tests, in order to reuse the same token
        # for multiple tests
        u1.id = 'u1'
        u2.id = 'u2'
        self.known_admin_id = u1.id
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
        self.known_blueprint_id_disabled = b1.id

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
        i3 = Instance(
            Blueprint.query.filter_by(id=b3.id).first(),
            User.query.filter_by(email="user@example.org").first())
        db.session.add(i3)
        i3.state = Instance.STATE_DELETED

        db.session.commit()

        conf = BaseConfig()
        for var_name in BaseConfig.__dict__:
            if not var_name.isupper():
                continue
            variable = Variable(var_name, conf[var_name])
            db.session.add(variable)
        db.session.commit()

    def make_request(self, method='GET', path='/', headers=None, data=None):
        assert method in self.methods

        if not headers:
            headers = {}

        if 'Content-Type' not in headers:
            headers['Content-Type'] = 'application/json'

        header_tuples = [(x, y) for x, y in headers.items()]
        return self.methods[method](path, headers=header_tuples, data=data, content_type='application/json')

    def get_auth_token(self, creds, headers=None):
        if not headers:
            headers = {}
        response = self.make_request('POST', '/api/v1/sessions',
                                     headers=headers,
                                     data=json.dumps(creds))
        token = '%s:' % response.json['token']
        return base64.b64encode(bytes(token.encode('ascii'))).decode('utf-8')

    def make_authenticated_request(self, method='GET', path='/', headers=None, data=None, creds=None,
                                   auth_token=None):
        assert creds is not None or auth_token is not None

        assert method in self.methods

        if not headers:
            headers = {}

        if not auth_token:
            auth_token = self.get_auth_token(headers, creds)

        headers.update({
            'Accept': 'application/json',
            'Authorization': 'Basic %s' % auth_token,
            'token': auth_token
        })
        return self.methods[method](path, headers=headers, data=data, content_type='application/json')

    def make_authenticated_admin_request(self, method='GET', path='/', headers=None, data=None):
        global ADMIN_TOKEN
        if not ADMIN_TOKEN:
            ADMIN_TOKEN = self.get_auth_token({'email': 'admin@example.org', 'password': 'admin'})

        self.admin_token = ADMIN_TOKEN

        return self.make_authenticated_request(method, path, headers, data,
                                               auth_token=self.admin_token)

    def make_authenticated_user_request(self, method='GET', path='/', headers=None, data=None):
        global USER_TOKEN
        if not USER_TOKEN:
            USER_TOKEN = self.get_auth_token(creds={'email': 'user@example.org', 'password': 'user'})
        self.user_token = USER_TOKEN
        return self.make_authenticated_request(method, path, headers, data,
                                               auth_token=self.user_token)

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
        self.assert_200(response)
        response = self.make_request(
            method='POST',
            path='/api/v1/sessions',
            data=json.dumps({'email': 'user@example.org', 'password': 'user'}))
        self.assert_401(response)

    def test_deleted_user_cannot_use_token(self):
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
        self.assert_200(response)
        # Test instance creation fails for the user
        response = self.make_request(
            method='POST',
            path='/api/v1/instances',
            data=json.dumps({'blueprint': self.known_blueprint_id}),
            headers=headers)
        self.assert_401(response)

    def test_delete_user(self):
        email = "test@example.org"
        u = User(email, "testuser", is_admin=False)
        # Anonymous
        db.session.add(u)
        db.session.commit()

        response = self.make_request(
            method='DELETE',
            path='/api/v1/users/%s' % u.id
        )
        self.assert_401(response)
        # Authenticated
        response = self.make_authenticated_user_request(
            method='DELETE',
            path='/api/v1/users/%s' % u.id
        )
        self.assert_403(response)
        # Admin
        response = self.make_authenticated_admin_request(
            method='DELETE',
            path='/api/v1/users/%s' % u.id
        )
        self.assert_200(response)
        user = User.query.filter_by(id=u.id).first()
        self.assertTrue(user.email != email)

    def test_get_users(self):
        # Anonymous
        response = self.make_request(path='/api/v1/users')
        self.assert_401(response)
        # Authenticated
        response = self.make_authenticated_user_request(path='/api/v1/users')
        self.assertEqual(len(response.json), 1)
        self.assert_200(response)
        # Admin
        response = self.make_authenticated_admin_request(path='/api/v1/users')
        self.assert_200(response)

    def test_get_plugins(self):
        # Anonymous
        response = self.make_request(path='/api/v1/plugins')
        self.assert_401(response)
        # Authenticated
        response = self.make_authenticated_user_request(path='/api/v1/plugins')
        self.assert_403(response)
        # Admin
        response = self.make_authenticated_admin_request(path='/api/v1/plugins')
        self.assert_200(response)

    def test_get_single_plugin(self):
        # Anonymous
        response = self.make_request(path='/api/v1/plugins/%s' % self.known_plugin_id)
        self.assert_401(response)
        # Authenticated
        response = self.make_authenticated_user_request(path='/api/v1/plugins/%s' % self.known_plugin_id)
        self.assert_403(response)
        # Admin
        response = self.make_authenticated_admin_request(path='/api/v1/plugins/%s' % self.known_plugin_id)
        self.assert_200(response)

        response = self.make_authenticated_admin_request(path='/api/v1/plugins/%s' % 'doesnotexists')
        self.assert_404(response)

    def test_admin_create_plugin(self):
        data = {
            'plugin': 'TestPlugin',
            'schema': json.dumps({}),
            'form': json.dumps({}),
            'model': json.dumps({})
        }
        response = self.make_authenticated_admin_request(
            method='POST',
            path='/api/v1/plugins',
            data=json.dumps(data))
        self.assert_200(response)

        data = {
            'plugin': 'TestPluginNew',
            'schema': json.dumps({}),
            'form': json.dumps({}),
            'model': json.dumps({})
        }
        response = self.make_authenticated_admin_request(
            method='POST',
            path='/api/v1/plugins',
            data=json.dumps(data))
        self.assert_200(response)

        data = {
            'plugin': 'TestPlugin',
            'schema': None,
            'form': json.dumps({}),
            'model': json.dumps({})
        }
        response = self.make_authenticated_admin_request(
            method='POST',
            path='/api/v1/plugins',
            data=json.dumps(data))
        self.assertStatus(response, 422)

    def test_get_blueprints(self):
        # Anonymous
        response = self.make_request(path='/api/v1/blueprints')
        self.assert_401(response)
        # Authenticated
        response = self.make_authenticated_user_request(path='/api/v1/blueprints')
        self.assert_200(response)
        self.assertEqual(len(response.json), 2)
        # Admin
        response = self.make_authenticated_admin_request(path='/api/v1/blueprints')
        self.assert_200(response)
        self.assertEqual(len(response.json), 3)

    def test_get_blueprint(self):
        # Existing blueprint
        # Anonymous
        response = self.make_request(path='/api/v1/blueprints/%s' % self.known_blueprint_id)
        self.assert_401(response)
        # Authenticated
        response = self.make_authenticated_user_request(path='/api/v1/blueprints/%s' % self.known_blueprint_id)
        self.assert_200(response)
        # Admin
        response = self.make_authenticated_admin_request(path='/api/v1/blueprints/%s' % self.known_blueprint_id)
        self.assert_200(response)

        # non-existing blueprint
        # Anonymous
        response = self.make_request(path='/api/v1/blueprints/%s' % uuid.uuid4().hex)
        self.assert_401(response)
        # Authenticated
        response = self.make_authenticated_user_request(path='/api/v1/blueprints/%s' % uuid.uuid4().hex)
        self.assert_404(response)
        # Admin
        response = self.make_authenticated_admin_request(path='/api/v1/blueprints/%s' % uuid.uuid4().hex)
        self.assert_404(response)

    def test_create_blueprint(self):
        # Anonymous
        data = {'name': 'test_blueprint_1', 'config': '', 'plugin': 'dummy'}
        response = self.make_request(
            method='POST',
            path='/api/v1/blueprints',
            data=json.dumps(data))
        self.assert_401(response)
        # Authenticated
        data = {'name': 'test_blueprint_1', 'config': '', 'plugin': 'dummy'}
        response = self.make_authenticated_user_request(
            method='POST',
            path='/api/v1/blueprints',
            data=json.dumps(data))
        self.assert_403(response)
        # Admin
        data = {'name': 'test_blueprint_1', 'config': 'foo: bar', 'plugin': 'dummy'}
        response = self.make_authenticated_admin_request(
            method='POST',
            path='/api/v1/blueprints',
            data=json.dumps(data))
        self.assert_200(response)

    def test_create_modify_blueprint_timeformat(self):

        form_data = [
            {'name': 'test_blueprint_2', 'config': {"name": "foo", "maximum_lifetime": '1d 1h 40m'}, 'plugin': 'dummy'},
            {'name': 'test_blueprint_2', 'config': {"name": "foo", "maximum_lifetime": '1d1h40m'}, 'plugin': 'dummy'},
            {'name': 'test_blueprint_2', 'config': {"name": "foo", "maximum_lifetime": '1d'}, 'plugin': 'dummy'},
            {'name': 'test_blueprint_2', 'config': {"name": "foo", "maximum_lifetime": '10h'}, 'plugin': 'dummy'},
            {'name': 'test_blueprint_2', 'config': {"name": "foo", "maximum_lifetime": '30m'}, 'plugin': 'dummy'},
            {'name': 'test_blueprint_2', 'config': {"name": "foo", "maximum_lifetime": '5h30m'}, 'plugin': 'dummy'},
            {'name': 'test_blueprint_2', 'config': {"name": "foo", "maximum_lifetime": '1d12h'}, 'plugin': 'dummy'},
            {'name': 'test_blueprint_2', 'config': {"name": "foo", "maximum_lifetime": '1d 10m'}, 'plugin': 'dummy'},
            {'name': 'test_blueprint_2', 'config': {"name": "foo", "maximum_lifetime": '1h 1m'}, 'plugin': 'dummy'},
            {'name': 'test_blueprint_2', 'config': {"name": "foo", "maximum_lifetime": '0d2h 30m'}, 'plugin': 'dummy'},
            {'name': 'test_blueprint_2', 'config': {"name": "foo", "maximum_lifetime": ''}, 'plugin': 'dummy'}
        ]
        expected_lifetimes = [92400, 92400, 86400, 36000, 1800, 19800, 129600, 87000, 3660, 9000, 3600]

        self.assertEquals(len(form_data), len(expected_lifetimes))

        for data, expected_lifetime in zip(form_data, expected_lifetimes):
            response = self.make_authenticated_admin_request(
                method='POST',
                path='/api/v1/blueprints',
                data=json.dumps(data))
            self.assert_200(response,
                            'testing time %s,%d failed' % (data['config']['maximum_lifetime'], expected_lifetime))

            put_response = self.make_authenticated_admin_request(
                method='PUT',
                path='/api/v1/blueprints/%s' % self.known_blueprint_id_2,
                data=json.dumps(data))
            self.assert_200(put_response)

            blueprint = Blueprint.query.filter_by(id=self.known_blueprint_id_2).first()
            self.assertEqual(blueprint.maximum_lifetime, expected_lifetime)

    def test_modify_blueprint_config_magic_vars_admin(self):
        data = {
            'name': 'test_blueprint_2',
            'config': {
                "name": "foo",
                "maximum_lifetime": '0d2h30m',
                "cost_multiplier": '0.1',
                "preallocated_credits": "true",
            },
            'plugin': self.known_plugin_id
        }
        put_response = self.make_authenticated_admin_request(
            method='PUT',
            path='/api/v1/blueprints/%s' % self.known_blueprint_id_2,
            data=json.dumps(data))
        self.assert_200(put_response)

        blueprint = Blueprint.query.filter_by(id=self.known_blueprint_id_2).first()
        self.assertEqual(blueprint.maximum_lifetime, 9000)
        self.assertEqual(blueprint.cost_multiplier, 0.1)
        self.assertEqual(blueprint.preallocated_credits, True)

    def test_create_blueprint_admin_invalid_data(self):
        invalid_form_data = [
            {'name': '', 'config': 'foo: bar', 'plugin': 'dummy'},
            {'name': 'test_blueprint_2', 'config': '', 'plugin': 'dummy'},
            {'name': 'test_blueprint_2', 'config': 'foo: bar', 'plugin': ''},
            {'name': 'test_blueprint_2', 'config': {"name": "foo", "maximum_lifetime": ' '}, 'plugin': 'dummy'},
            {'name': 'test_blueprint_2', 'config': {"name": "foo", "maximum_lifetime": '10 100'}, 'plugin': 'dummy'},
            {'name': 'test_blueprint_2', 'config': {"name": "foo", "maximum_lifetime": '1hh'}, 'plugin': 'dummy'},
            {'name': 'test_blueprint_2', 'config': {"name": "foo", "maximum_lifetime": '-1m'}, 'plugin': 'dummy'},
            {'name': 'test_blueprint_2', 'config': {"name": "foo", "maximum_lifetime": '-10h'}, 'plugin': 'dummy'},
            {'name': 'test_blueprint_2', 'config': {"name": "foo", "maximum_lifetime": '2d -10h'}, 'plugin': 'dummy'},
            {'name': 'test_blueprint_2', 'config': {"name": "foo", "maximum_lifetime": '30s'}, 'plugin': 'dummy'},
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
        data = {'email': 'test@example.org', 'is_admin': True}
        response = self.make_authenticated_admin_request(
            method='POST',
            path='/api/v1/users',
            data=json.dumps(data))
        self.assert_200(response)
        user = User.query.filter_by(email='test@example.org').first()
        self.assertIsNotNone(user)
        self.assertFalse(user.is_active)
        self.assertTrue(user.is_admin)

        data = {'email': 'test2@example.org', 'is_admin': False}
        response = self.make_authenticated_admin_request(
            method='POST',
            path='/api/v1/users',
            data=json.dumps(data))
        self.assert_200(response)
        user = User.query.filter_by(email='test2@example.org').first()
        self.assertIsNotNone(user)
        self.assertFalse(user.is_active)
        self.assertFalse(user.is_admin)

    def test_admin_delete_invited_user_deletes_activation_tokens(self):
        data = {'email': 'test@example.org'}
        response = self.make_authenticated_admin_request(
            method='POST',
            path='/api/v1/users',
            data=json.dumps(data))
        self.assert_200(response)
        user = User.query.filter_by(email='test@example.org').first()
        self.assertIsNotNone(user)
        self.assertFalse(user.is_admin)
        self.assertFalse(user.is_active)
        self.assertEqual(ActivationToken.query.filter_by(user_id=user.id).count(), 1)
        response = self.make_authenticated_admin_request(
            method='DELETE',
            path='/api/v1/users/%s' % user.id
        )
        self.assert_200(response)
        self.assertEqual(ActivationToken.query.filter_by(user_id=user.id).count(), 0)

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

    def test_user_create_instance_blueprint_disabled(self):
        response = self.make_authenticated_user_request(
            method='POST',
            path='/api/v1/instances',
            data=json.dumps({'blueprint': self.known_blueprint_id_disabled}),
        )
        self.assert_404(response)

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

    def test_get_instances(self):
        # Anonymous
        response = self.make_request(path='/api/v1/instances')
        self.assert_401(response)
        # Authenticated
        response = self.make_authenticated_user_request(path='/api/v1/instances')
        self.assert_200(response)
        self.assertEqual(len(response.json), 2)
        response = self.make_authenticated_user_request(path='/api/v1/instances?show_deleted=true')
        self.assert_200(response)
        self.assertEqual(len(response.json), 3)

        # Admin
        response = self.make_authenticated_admin_request(path='/api/v1/instances')
        self.assert_200(response)
        self.assertEqual(len(response.json), 2)
        response = self.make_authenticated_admin_request(path='/api/v1/instances?show_only_mine=1')
        self.assert_200(response)
        self.assertEqual(len(response.json), 0)

    def test_get_instance(self):
        # Anonymous
        response = self.make_request(path='/api/v1/instances/%s' % self.known_instance_id)
        self.assert_401(response)
        # Authenticated
        response = self.make_authenticated_user_request(path='/api/v1/instances/%s' % self.known_instance_id)
        self.assert_200(response)
        # Admin
        response = self.make_authenticated_admin_request(path='/api/v1/instances/%s' % self.known_instance_id)
        self.assert_200(response)

    def test_get_keypairs(self):
        # Anonymous
        response = self.make_request(path='/api/v1/users/%s/keypairs' % self.known_user_id)
        self.assert_401(response)
        response2 = self.make_request(path='/api/v1/users/%s/keypairs' % '0xBogus')
        self.assert_401(response2)
        # Authenticated
        response = self.make_authenticated_user_request(path='/api/v1/users/%s/keypairs' % self.known_user_id)
        self.assert_200(response)
        self.assertEqual(len(response.json), 0)
        response2 = self.make_authenticated_user_request(path='/api/v1/users/%s/keypairs' % '0xBogus')
        self.assert_403(response2)
        # Admin
        response = self.make_authenticated_admin_request(
            path='/api/v1/users/%s/keypairs' % self.known_user_id
        )
        self.assert_200(response)
        self.assertEqual(len(response.json), 0)
        response2 = self.make_authenticated_admin_request(path='/api/v1/users/%s/keypairs' % '0xBogus')
        self.assert_404(response2)

    def test_user_over_quota_cannot_launch_instances(self):
        data = {'blueprint': self.known_blueprint_id}
        response = self.make_authenticated_user_request(
            method='POST',
            path='/api/v1/instances',
            data=json.dumps(data)).json
        instance = Instance.query.filter_by(id=response['id']).first()
        instance.provisioned_at = datetime.datetime(2015, 1, 1, 0, 0, 0)
        instance.deprovisioned_at = datetime.datetime(2015, 1, 1, 1, 0, 0)

        db.session.commit()
        response2 = self.make_authenticated_user_request(
            method='POST',
            path='/api/v1/instances',
            data=json.dumps(data))
        self.assertEqual(response2.status_code, 409)

    def test_update_admin_quota_relative(self):
        response = self.make_authenticated_admin_request(
            path='/api/v1/users'
        )
        assert abs(response.json[0]['credits_quota'] - 1) < 0.001
        user_id = response.json[0]['id']
        response2 = self.make_authenticated_admin_request(
            method='PUT',
            path='/api/v1/quota/%s' % user_id,
            data=json.dumps({'type': 'relative', 'value': 10}))
        self.assertEqual(response2.status_code, 200)
        response = self.make_authenticated_admin_request(
            path='/api/v1/users'
        )
        self.assertEqual(user_id, response.json[0]['id'])
        assert abs(response.json[0]['credits_quota'] - 11) < 0.001

    def test_update_quota_absolute(self):
        response = self.make_authenticated_admin_request(
            path='/api/v1/users'
        )

        for user in response.json:
            assert abs(user['credits_quota'] - 1) < 0.001

        response2 = self.make_authenticated_admin_request(
            method='PUT',
            path='/api/v1/quota',
            data=json.dumps({'type': 'absolute', 'value': 42}))
        self.assertEqual(response2.status_code, 200)

        response3 = self.make_authenticated_admin_request(
            path='/api/v1/users'
        )

        for user in response3.json:
            assert abs(user['credits_quota'] - 42) < 0.001

    def test_user_cannot_update_user_quota_absolute(self):
        response = self.make_authenticated_user_request(
            path='/api/v1/users'
        )
        self.assertEqual(len(response.json), 1)
        user_id = response.json[0]['id']
        response2 = self.make_authenticated_user_request(
            method='PUT',
            path='/api/v1/quota/%s' % user_id,
            data=json.dumps({'type': "absolute", 'value': 10}))
        self.assert_403(response2)

    def test_user_cannot_update_quotas(self):
        response = self.make_authenticated_user_request(
            method='PUT',
            path='/api/v1/quota',
            data=json.dumps({'type': "absolute", 'value': 10}))
        self.assert_403(response)

    def test_anonymous_cannot_see_quota_list(self):
        response = self.make_request(
            path='/api/v1/quota'
        )
        self.assert_401(response)

    def test_user_cannot_see_quota_list(self):
        response = self.make_authenticated_user_request(
            path='/api/v1/quota'
        )
        self.assert_403(response)

    def test_admin_get_quota_list(self):
        response = self.make_authenticated_admin_request(
            path='/api/v1/quota'
        )
        self.assert_200(response)

    def test_anonymous_cannot_see_user_quota(self):
        response2 = self.make_request(
            path='/api/v1/quota/%s' % self.known_user_id
        )
        self.assert_401(response2)

    def test_user_get_own_quota(self):
        response = self.make_authenticated_user_request(
            path='/api/v1/quota/%s' % self.known_user_id
        )
        self.assert_200(response)

    def test_parse_invalid_quota_update(self):
        response = self.make_authenticated_admin_request(
            method='PUT',
            path='/api/v1/quota',
            data=json.dumps({'type': "invalid_type", 'value': 10}))
        self.assertStatus(response, 422)
        response = self.make_authenticated_admin_request(
            method='PUT',
            path='/api/v1/quota',
            data=json.dumps({'type': "relative", 'value': "foof"}))
        self.assertStatus(response, 422)

    def test_user_cannot_see_other_users(self):
        response = self.make_authenticated_user_request(
            path='/api/v1/quota/%s' % self.known_admin_id
        )
        self.assert_403(response)

    def test_anonymous_what_is_my_ip(self):
        response = self.make_request(path='/api/v1/what_is_my_ip')
        self.assert_401(response)

    def test_what_is_my_ip(self):
        response = self.make_authenticated_user_request(path='/api/v1/what_is_my_ip')
        self.assert_200(response)

    def test_get_variables(self):
        # Anonymous
        response = self.make_request(path='/api/v1/variables')
        self.assert_401(response)
        # Authenticated
        response = self.make_authenticated_user_request(path='/api/v1/variables')
        self.assert_403(response)
        # Admin
        response = self.make_authenticated_admin_request(path='/api/v1/variables')
        self.assert_200(response)

    def test_get_variable(self):
        # Anonymous
        response = self.make_request(path='/api/v1/variables/DEBUG')
        self.assert_401(response)
        # Authenticated
        response = self.make_authenticated_user_request(path='/api/v1/variables/DEBUG')
        self.assert_403(response)
        # Admin
        response = self.make_authenticated_admin_request(path='/api/v1/variables/DEBUG')
        self.assert_200(response)

    def test_anonymous_set_variable(self):
        response = self.make_request(
            method='PUT',
            path='/api/v1/variables/DEBUG',
            data=json.dumps({'key': 'DEBUG', 'value': True})
        )
        self.assert_401(response)

    def test_user_set_variable(self):
        response = self.make_authenticated_user_request(
            method='PUT',
            path='/api/v1/variables/DEBUG',
            data=json.dumps({'key': 'DEBUG', 'value': True})
        )
        self.assert_403(response)

    def test_admin_set_variable(self):
        var_data = self.make_authenticated_admin_request(path='/api/v1/variables/DEBUG').json
        response = self.make_authenticated_admin_request(
            method='PUT',
            path='/api/v1/variables/%s' % var_data['id'],
            data=json.dumps({'key': 'DEBUG', 'value': str(not var_data['value'])})
        )
        self.assert_200(response)
        new_var_data = self.make_authenticated_admin_request(path='/api/v1/variables/DEBUG').json
        self.assertNotEquals(new_var_data['value'], var_data['value'])

    def test_admin_set_ro_variable(self):
        var_data = self.make_authenticated_admin_request(path='/api/v1/variables/SECRET_KEY').json

        response = self.make_authenticated_admin_request(
            method='PUT',
            path='/api/v1/variables/%s' % var_data['id'],
            data=json.dumps({'key': 'SECRET_KEY', 'value': 'foo'})
        )
        self.assertEquals(response.status_code, 409)
        new_var_data = self.make_authenticated_admin_request(path='/api/v1/variables/SECRET_KEY').json
        self.assertEquals(new_var_data['value'], var_data['value'])

    def test_admin_acquire_lock(self):
        unique_id = 'abc123'
        response = self.make_authenticated_admin_request(
            method='PUT',
            path='/api/v1/locks/%s' % unique_id)
        self.assertStatus(response, 200)

        response2 = self.make_authenticated_admin_request(
            method='PUT',
            path='/api/v1/locks/%s' % unique_id)
        self.assertStatus(response2, 409)

        response3 = self.make_authenticated_admin_request(
            method='DELETE',
            path='/api/v1/locks/%s' % unique_id)
        self.assertStatus(response3, 200)

        response4 = self.make_authenticated_admin_request(
            method='DELETE',
            path='/api/v1/locks/%s' % unique_id)
        self.assertStatus(response4, 404)

        unique_id = 'abc123'
        response = self.make_authenticated_admin_request(
            method='PUT',
            path='/api/v1/locks/%s' % unique_id)
        self.assertStatus(response, 200)


if __name__ == '__main__':
    unittest.main()
