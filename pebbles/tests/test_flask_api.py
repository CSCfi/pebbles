import base64
import datetime
import json
import time
import unittest
import uuid

import dateutil

from pebbles.models import (
    User, Workspace, WorkspaceUserAssociation, EnvironmentTemplate, Environment,
    ActivationToken, Instance)
from pebbles.tests.base import db, BaseTestCase
from pebbles.tests.fixtures import primary_test_setup
from pebbles.views import activations

ADMIN_TOKEN = None
USER_TOKEN = None
COURSE_OWNER_TOKEN = None
COURSE_OWNER_TOKEN2 = None


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
        primary_test_setup(self)
        # conf = BaseConfig()

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
            ADMIN_TOKEN = self.get_auth_token({'eppn': 'admin@example.org', 'password': 'admin'})

        self.admin_token = ADMIN_TOKEN

        return self.make_authenticated_request(method, path, headers, data,
                                               auth_token=self.admin_token)

    def make_authenticated_user_request(self, method='GET', path='/', headers=None, data=None):
        global USER_TOKEN
        if not USER_TOKEN:
            USER_TOKEN = self.get_auth_token(creds={
                'eppn': self.known_user_eppn,
                'password': self.known_user_password}
            )
        self.user_token = USER_TOKEN
        return self.make_authenticated_request(method, path, headers, data,
                                               auth_token=self.user_token)

    def make_authenticated_workspace_owner_request(self, method='GET', path='/', headers=None, data=None):
        global COURSE_OWNER_TOKEN
        if not COURSE_OWNER_TOKEN:
            COURSE_OWNER_TOKEN = self.get_auth_token(creds={'eppn': 'workspace_owner@example.org', 'password': 'workspace_owner'})
        self.workspace_owner_token = COURSE_OWNER_TOKEN
        return self.make_authenticated_request(method, path, headers, data,
                                               auth_token=self.workspace_owner_token)

    def make_authenticated_workspace_owner2_request(self, method='GET', path='/', headers=None, data=None):
        global COURSE_OWNER_TOKEN2
        if not COURSE_OWNER_TOKEN2:
            COURSE_OWNER_TOKEN2 = self.get_auth_token(creds={'eppn': 'workspace_owner2@example.org', 'password': 'workspace_owner2'})
        self.workspace_owner_token2 = COURSE_OWNER_TOKEN2
        return self.make_authenticated_request(method, path, headers, data,
                                               auth_token=self.workspace_owner_token2)

    def assert_202(self, response):
        self.assert_status(response, 202)

    def test_deleted_user_cannot_get_token(self):
        response = self.make_request(
            method='POST',
            path='/api/v1/sessions',
            data=json.dumps({'eppn': 'user@example.org', 'password': 'user', 'email_id': None}))
        self.assert_200(response)
        response = self.make_authenticated_admin_request(
            method='DELETE',
            path='/api/v1/users/%s' % self.known_user_id
        )
        self.assert_200(response)
        response = self.make_request(
            method='POST',
            path='/api/v1/sessions',
            data=json.dumps({'eppn': 'user@example.org', 'password': 'user', 'email_id': None}))
        self.assert_401(response)

    def test_deleted_user_cannot_use_token(self):
        response = self.make_request(
            method='POST',
            path='/api/v1/sessions',
            data=json.dumps({'eppn': 'user@example.org', 'password': 'user'})
        )
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
            data=json.dumps({'environment': self.known_environment_id}),
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
            data=json.dumps({'environment': self.known_environment_id}),
            headers=headers)
        self.assert_401(response)

    def test_delete_user(self):
        eppn = "test@example.org"
        u = User(eppn, "testuser", is_admin=False)
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
        self.assertTrue(user.eppn != eppn)

    def test_make_workspace_owner(self):
        eppn = "test_owner@example.org"
        u = User(eppn, "testuser", is_admin=False)
        db.session.add(u)
        db.session.commit()
        # Anonymous
        response = self.make_request(
            method='PUT',
            path='/api/v1/users/%s/user_workspace_owner' % u.id,
            data=json.dumps({'make_workspace_owner': True})
        )
        self.assert_401(response)
        # Authenticated
        response = self.make_authenticated_user_request(
            method='PUT',
            path='/api/v1/users/%s/user_workspace_owner' % u.id,
            data=json.dumps({'make_workspace_owner': True})
        )
        self.assert_403(response)
        # Workspace Owner
        response = self.make_authenticated_workspace_owner_request(
            method='PUT',
            path='/api/v1/users/%s/user_workspace_owner' % u.id,
            data=json.dumps({'make_workspace_owner': True})
        )
        self.assert_403(response)
        # Admin
        # Make Workspace Owner
        response = self.make_authenticated_admin_request(
            method='PUT',
            path='/api/v1/users/%s/user_workspace_owner' % u.id,
            data=json.dumps({'make_workspace_owner': True})
        )
        self.assert_200(response)
        user = User.query.filter_by(id=u.id).first()
        self.assertTrue(user.is_workspace_owner)
        # Remove Workspace Owner
        response = self.make_authenticated_admin_request(
            method='PUT',
            path='/api/v1/users/%s/user_workspace_owner' % u.id,
            data=json.dumps({'make_workspace_owner': False})
        )
        self.assert_200(response)
        user = User.query.filter_by(id=u.id).first()
        self.assertFalse(user.is_workspace_owner)

    def test_remove_workspace_ownership(self):
        user = User.query.filter_by(id=self.known_workspace_owner_id).first()
        self.assertTrue(user.is_workspace_owner)
        response = self.make_authenticated_admin_request(
            method='PUT',
            path='/api/v1/users/%s/user_workspace_owner' % user.id,
            data=json.dumps({'make_workspace_owner': False})
        )
        self.assert_200(response)
        user = User.query.filter_by(id=self.known_workspace_owner_id).first()
        self.assertFalse(user.is_workspace_owner)

    def test_block_user(self):
        eppn = "test@example.org"
        u = User(eppn, "testuser", is_admin=False)
        db.session.add(u)
        db.session.commit()
        # Anonymous
        response = self.make_request(
            method='PUT',
            path='/api/v1/users/%s/user_blacklist' % u.id,
            data=json.dumps({'block': True})
        )
        self.assert_401(response)
        # Authenticated
        response = self.make_authenticated_user_request(
            method='PUT',
            path='/api/v1/users/%s/user_blacklist' % u.id,
            data=json.dumps({'block': True})
        )
        self.assert_403(response)
        response = self.make_authenticated_user_request(
            method='PUT',
            path='/api/v1/users/%s/user_blacklist' % u.id,
            data=json.dumps({'block': True})
        )
        self.assert_403(response)
        # Admin
        # Block
        response = self.make_authenticated_admin_request(
            method='PUT',
            path='/api/v1/users/%s/user_blacklist' % u.id,
            data=json.dumps({'block': True})
        )
        self.assert_200(response)
        user = User.query.filter_by(id=u.id).first()
        self.assertTrue(user.is_blocked)
        # Unblock
        response = self.make_authenticated_admin_request(
            method='PUT',
            path='/api/v1/users/%s/user_blacklist' % u.id,
            data=json.dumps({'block': False})
        )
        self.assert_200(response)
        user = User.query.filter_by(id=u.id).first()
        self.assertFalse(user.is_blocked)

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

    def test_get_total_users(self):
        # Anonymous
        response = self.make_request(path='/api/v1/users', method='PATCH')
        self.assert_401(response)
        # Authenticated
        response = self.make_authenticated_user_request(path='/api/v1/users', method='PATCH')
        self.assert_403(response)
        # Admin
        response = self.make_authenticated_admin_request(
            path='/api/v1/users',
            method='PATCH',
            data=json.dumps({'count': True})
        )
        self.assert_200(response)

    def test_export_statistics(self):
        dt1 = datetime.datetime(2012, 1, 1)
        dt2 = datetime.datetime(2015, 5, 5)
        dt3 = datetime.datetime(2018, 3, 3)
        u1 = User("test1@example.org", "testuser1", is_admin=False)
        u2 = User("test2@example.org", "testuser2", is_admin=False)
        u3 = User("test3@admin.org", "testuser3", is_admin=True)
        u1.joining_date = dt1
        u1.is_active = True
        u2.joining_date = dt2
        u2.is_active = True
        u3.joining_date = dt3
        u3.is_active = True
        db.session.add(u1)
        db.session.add(u2)
        db.session.add(u3)

        bp = Environment()
        i1 = Instance(bp, u1)
        i1.provisioned_at = dt2
        db.session.add(i1)

        db.session.commit()

        # Anonymous
        response = self.make_request(
            path='/api/v1/export_stats/export_statistics',
            method="GET"
        )
        self.assert_401(response)
        # Authenticated user
        response = self.make_authenticated_user_request(
            path='/api/v1/export_stats/export_statistics',
            method="GET",
            data=json.dumps({'stat': 'users'})
        )
        self.assert_403(response)
        # Authenticated workspace owner
        response = self.make_authenticated_workspace_owner_request(
            path='/api/v1/export_stats/export_statistics',
            method="GET",
            data=json.dumps({'stat': 'users'})
        )
        self.assert_403(response)
        # Authenticated admin
        response = self.make_authenticated_admin_request(
            path='/api/v1/export_stats/export_statistics',
            method='GET',
            data=json.dumps({'start': None, 'end': None, 'stat': 'users'})
        )
        self.assert_200(response)
        # Authenticated admin
        response = self.make_authenticated_admin_request(
            path='/api/v1/export_stats/export_statistics',
            method='GET',
            data=json.dumps({'start': None, 'end': None, 'stat': 'monthly_instances'})
        )
        self.assert_200(response)
        # Authenticated admin
        response = self.make_authenticated_admin_request(
            path='/api/v1/export_stats/export_statistics',
            method='GET',
            data=json.dumps({'start': None, 'end': None, 'stat': 'institutions'})
        )
        self.assert_200(response)
        # Authenticated admin
        response = self.make_authenticated_admin_request(
            path='/api/v1/export_stats/export_statistics',
            method='GET',
            data=json.dumps({'start': None, 'end': None, 'stat': 'quartals'})
        )
        self.assert_200(response)
        # Authenticated admin
        response = self.make_authenticated_admin_request(
            path='/api/v1/export_stats/export_statistics',
            method='GET',
            data=json.dumps({'start': None, 'end': None, 'stat': 'quartals_by_org'})
        )
        self.assert_200(response)
        # Authenticated admin, invalid date input
        response = self.make_authenticated_admin_request(
            path='/api/v1/export_stats/export_statistics',
            method='GET',
            data=json.dumps({'start': '02/02/2011', 'end': '01/01/2011', 'stat': 'users'})
        )
        self.assertStatus(response, 404)
        # Authenticated admin, invalid filter input
        response = self.make_authenticated_admin_request(
            path='/api/v1/export_stats/export_statistics',
            method='GET',
            data=json.dumps({'filter': 'not,in,institutions', 'stat': 'users', 'exclude': False})
        )
        self.assertStatus(response, 404)
        # Authenticated admin, no results
        response = self.make_authenticated_admin_request(
            path='/api/v1/export_stats/export_statistics',
            method='GET',
            data=json.dumps({'start': '02/02/2000', 'end': '03/03/2000', 'stat': 'users'})
        )
        self.assertStatus(response, 404)
        # Authenticated admin, wrong stat type
        response = self.make_authenticated_admin_request(
            path='/api/v1/export_stats/export_statistics',
            method='GET',
            data=json.dumps({'start': None, 'end': None, 'stat': 'wrong_stat'})
        )
        self.assertStatus(response, 404)
        # Authenticated admin, correct dates, correct filter, include
        response = self.make_authenticated_admin_request(
            path='/api/v1/export_stats/export_statistics',
            method='GET',
            data=json.dumps({'start': '01/01/2011', 'end': '01/01/2018', 'filter': 'example.org',
                             'exclude': False, 'stat': 'users'})
        )
        self.assert_200(response)

    def test_invite_multiple_users(self):
        # Admin
        response = self.make_authenticated_admin_request(
            path='/api/v1/users',
            method='PATCH',
            data=json.dumps({'addresses': 'invite1@example.org, invite2@example.org'})
        )
        self.assert_200(response)

        incorrect_response = self.make_authenticated_admin_request(
            path='/api/v1/users',
            method='PATCH',
            data=json.dumps({'addresses': 'bogus@example'})
        )
        self.assertStatus(incorrect_response, 422)

    def test_get_workspaces(self):
        # Anonymous
        response = self.make_request(path='/api/v1/workspaces')
        self.assert_401(response)
        # Authenticated User
        response = self.make_authenticated_user_request(path='/api/v1/workspaces')
        self.assert_200(response)
        self.assertEqual(1, len(response.json))
        # Authenticated Workspace Owner
        response = self.make_authenticated_workspace_owner_request(path='/api/v1/workspaces')
        self.assert_200(response)
        self.assertEqual(2, len(response.json))
        # Admin
        response = self.make_authenticated_admin_request(path='/api/v1/workspaces')
        self.assert_200(response)
        self.assertEqual(5, len(response.json))
        # Get One
        response = self.make_authenticated_admin_request(path='/api/v1/workspaces/%s' % self.known_workspace_id)
        self.assert_200(response)

    def test_create_workspace(self):

        data = {
            'name': 'TestWorkspace',
            'description': 'Workspace Details',
            'user_config': {
                'users': [{'id': self.known_user_id}],
                'banned_users': [],
                'owners': []
            }
        }
        data_2 = {
            'name': 'TestWorkspace2',
            'description': 'Workspace Details',
            'user_config': {
                'banned_users': [{'id': self.known_user_id}],
            }
        }
        data_3 = {
            'name': 'TestWorkspace',
            'description': 'Workspace Details',
            'user_config': {
            }
        }
        data_4 = {
            'name': 'TestWorkspace4',
            'description': 'Workspace Details',
            'user_config': {
            }
        }

        # Anonymous
        response = self.make_request(
            method='POST',
            path='/api/v1/workspaces',
            data=json.dumps(data))
        self.assertStatus(response, 401)
        # Authenticated User
        response = self.make_authenticated_user_request(
            method='POST',
            path='/api/v1/workspaces',
            data=json.dumps(data))
        self.assertStatus(response, 403)

        # increase workspace quota to 4 for owner 1
        response2 = self.make_authenticated_admin_request(
            method='PUT',
            path='/api/v1/quota/%s' % self.known_workspace_owner_id,
            data=json.dumps({'type': "absolute", 'value': 4, 'credits_type': 'workspace_quota_value'}))
        self.assert_200(response2)

        # Workspace Owner
        response = self.make_authenticated_workspace_owner_request(
            method='POST',
            path='/api/v1/workspaces',
            data=json.dumps(data))
        self.assertStatus(response, 200)

        response = self.make_authenticated_workspace_owner_request(
            method='POST',
            path='/api/v1/workspaces',
            data=json.dumps(data_2))
        self.assertStatus(response, 200)

        response = self.make_authenticated_workspace_owner_request(
            method='POST',
            path='/api/v1/workspaces',
            data=json.dumps(data_3))
        self.assertStatus(response, 200)

        response = self.make_authenticated_workspace_owner_request(
            method='POST',
            path='/api/v1/workspaces',
            data=json.dumps(data_4))
        self.assertStatus(response, 422)

        # Admin
        response = self.make_authenticated_admin_request(
            method='POST',
            path='/api/v1/workspaces',
            data=json.dumps(data))
        self.assertStatus(response, 200)

    def test_create_workspace_invalid_data(self):
        invalid_data = {
            'name': '',
            'description': 'Workspace Details',
        }
        # Try to create system level workspaces
        invalid_system_data = {
            'name': 'System.Workspace',
            'description': 'Workspace Details',
            'user_config': {
            }
        }
        invalid_system_data_2 = {
            'name': 'system workspace',
            'description': 'Workspace Details',
            'user_config': {
            }
        }
        invalid_response = self.make_authenticated_workspace_owner_request(
            method='POST',
            path='/api/v1/workspaces',
            data=json.dumps(invalid_data))
        self.assertStatus(invalid_response, 422)

        invalid_response = self.make_authenticated_workspace_owner_request(
            method='POST',
            path='/api/v1/workspaces',
            data=json.dumps(invalid_system_data))
        self.assertStatus(invalid_response, 422)

        invalid_response = self.make_authenticated_workspace_owner_request(
            method='POST',
            path='/api/v1/workspaces',
            data=json.dumps(invalid_system_data_2))
        self.assertStatus(invalid_response, 422)

    def test_modify_workspace(self):

        g = Workspace('TestWorkspaceModify')
        # g.owner_id = self.known_workspace_owner_id
        u1 = User.query.filter_by(id=self.known_user_id).first()
        gu1_obj = WorkspaceUserAssociation(user=u1, workspace=g)
        u2 = User.query.filter_by(id=self.known_workspace_owner_id_2).first()
        gu2_obj = WorkspaceUserAssociation(user=u2, workspace=g)
        u3 = User.query.filter_by(id=self.known_workspace_owner_id).first()
        gu3_obj = WorkspaceUserAssociation(user=u3, workspace=g, manager=True, owner=True)
        g.users.append(gu1_obj)
        g.users.append(gu2_obj)
        g.users.append(gu3_obj)
        db.session.add(g)
        db.session.commit()

        data_ban = {
            'name': 'TestWorkspaceModify',
            'description': 'Workspace Details',
            'user_config': {
                'banned_users': [{'id': u1.id}]
            }
        }
        data_manager = {
            'name': 'TestWorkspaceModify',
            'description': 'Workspace Details',
            'user_config': {
                'managers': [{'id': u2.id}]
            }
        }
        response_ban = self.make_authenticated_workspace_owner_request(
            method='PUT',
            path='/api/v1/workspaces/%s' % g.id,
            data=json.dumps(data_ban))
        self.assertStatus(response_ban, 200)

        response_manager = self.make_authenticated_workspace_owner_request(
            method='PUT',
            path='/api/v1/workspaces/%s' % g.id,
            data=json.dumps(data_manager))
        self.assertStatus(response_manager, 200)

    def test_modify_workspace_invalid_data(self):

        invalid_data = {
            'name': 'TestWorkspace bogus id',
            'description': 'Workspace Details',
            'user_config': {
                'banned_users': [{'id': 'bogusx10'}]
            }
        }
        invalid_data_1 = {
            'name': 'TestWorkspace manager cannot be banned',
            'description': 'Workspace Details',
            'user_config': {
                'banned_users': [{'id': self.known_user_id}],
                'managers': [{'id': self.known_user_id}]
            }
        }
        invalid_response = self.make_authenticated_workspace_owner_request(
            method='PUT',
            path='/api/v1/workspaces/%s' % self.known_workspace_id,
            data=json.dumps(invalid_data))
        self.assertStatus(invalid_response, 422)

        invalid_response = self.make_authenticated_workspace_owner_request(
            method='PUT',
            path='/api/v1/workspaces/%s' % self.known_workspace_id,
            data=json.dumps(invalid_data_1))
        self.assertStatus(invalid_response, 422)

    def test_delete_workspace(self):
        name = 'WorkspaceToBeDeleted'
        g = Workspace(name)
        g.owner_id = self.known_workspace_owner_id
        db.session.add(g)
        db.session.commit()
        # Anonymous
        response = self.make_request(
            method='DELETE',
            path='/api/v1/workspaces/%s' % g.id
        )
        self.assert_401(response)
        # Authenticated
        response = self.make_authenticated_user_request(
            method='DELETE',
            path='/api/v1/workspaces/%s' % g.id
        )
        self.assert_403(response)
        # Authenticated
        response = self.make_authenticated_workspace_owner_request(
            method='DELETE',
            path='/api/v1/workspaces/%s' % g.id
        )
        self.assert_403(response)
        # Admin
        invalid_response = self.make_authenticated_admin_request(
            method='DELETE',
            path='/api/v1/workspaces/%s' % self.system_default_workspace_id
        )
        self.assertStatus(invalid_response, 422)  # Cannot delete default system workspace
        response = self.make_authenticated_admin_request(
            method='DELETE',
            path='/api/v1/workspaces/%s' % g.id
        )
        self.assert_200(response)
        workspace = Workspace.query.filter_by(id=g.id).first()
        self.assertIsNone(workspace)

    def test_join_workspace(self):
        # Anonymous
        response = self.make_request(
            method='PUT',
            path='/api/v1/join_workspace/%s' % self.known_workspace_join_id)
        self.assertStatus(response, 401)
        # Authenticated User
        response = self.make_authenticated_user_request(
            method='PUT',
            path='/api/v1/join_workspace/%s' % self.known_workspace_join_id)
        self.assertStatus(response, 200)
        # Workspace Owner
        response = self.make_authenticated_workspace_owner_request(
            method='PUT',
            path='/api/v1/join_workspace/%s' % self.known_workspace_join_id)
        self.assertStatus(response, 200)

    def test_join_workspace_invalid(self):
        g = Workspace('InvalidTestWorkspace')
        g.owner_id = self.known_workspace_owner_id
        u = User.query.filter_by(id=self.known_user_id).first()
        gu_obj = WorkspaceUserAssociation()
        gu_obj.user = u
        gu_obj.workspace = g

        g.users.append(gu_obj)
        db.session.add(g)
        db.session.commit()
        # Authenticated User
        invalid_response = self.make_authenticated_user_request(
            method='PUT',
            path='/api/v1/join_workspace/')
        self.assertStatus(invalid_response, 405)  # Not allowed without joining code
        # Authenticated User Bogus Code
        invalid_response = self.make_authenticated_user_request(
            method='PUT',
            path='/api/v1/join_workspace/%s' % 'bogusx10')
        self.assertStatus(invalid_response, 422)
        # Workspace Owner Bogus Code
        invalid_response = self.make_authenticated_workspace_owner_request(
            method='PUT',
            path='/api/v1/join_workspace/%s' % 'bogusx10')
        self.assertStatus(invalid_response, 422)
        # Authenticated User - Trying to Join the same workspace again
        response = self.make_authenticated_user_request(
            method='PUT',
            path='/api/v1/join_workspace/%s' % g.join_code)
        self.assertStatus(response, 422)

    def test_join_workspace_banned_user(self):

        # Authenticated User
        banned_response = self.make_authenticated_user_request(
            method='PUT',
            path='/api/v1/join_workspace/%s' % self.known_banned_workspace_join_id)
        self.assertStatus(banned_response, 403)

        # Authenticated Workspace Owner
        banned_response = self.make_authenticated_workspace_owner_request(
            method='PUT',
            path='/api/v1/join_workspace/%s' % self.known_banned_workspace_join_id)
        self.assertStatus(banned_response, 403)

    def test_exit_workspace(self):
        g = Workspace('TestWorkspaceExit')
        g.owner_id = self.known_workspace_owner_id_2
        u = User.query.filter_by(id=self.known_user_id).first()
        gu_obj = WorkspaceUserAssociation(workspace=g, user=u)

        u_extra = User.query.filter_by(id=self.known_workspace_owner_id).first()  # extra user
        gu_extra_obj = WorkspaceUserAssociation(workspace=g, user=u_extra)

        g.users.append(gu_obj)
        g.users.append(gu_extra_obj)

        db.session.add(g)
        db.session.commit()
        # Anonymous
        response = self.make_request(
            method='PUT',
            path='/api/v1/workspaces/%s/exit' % g.id)
        self.assertStatus(response, 401)
        # Authenticated User of the workspace
        response = self.make_authenticated_user_request(
            method='PUT',
            path='/api/v1/workspaces/%s/exit' % g.id)
        self.assertStatus(response, 200)
        # self.assertEqual(len(g.users.all()), 1)
        # Workspace Owner who is just a user of the workspace
        response = self.make_authenticated_workspace_owner_request(
            method='PUT',
            path='/api/v1/workspaces/%s/exit' % g.id)
        self.assertStatus(response, 200)
        # self.assertEqual(len(g.users.all()), 0)

    def test_exit_workspace_invalid(self):
        g = Workspace('InvalidTestWorkspaceExit')
        u = User.query.filter_by(id=self.known_workspace_owner_id).first()
        gu_obj = WorkspaceUserAssociation(workspace=g, user=u, manager=True, owner=True)
        g.users.append(gu_obj)
        db.session.add(g)
        db.session.commit()
        # Authenticated User
        invalid_response = self.make_authenticated_user_request(
            method='PUT',
            path='/api/v1/workspaces/exit/')
        self.assertStatus(invalid_response, 405)  # can't put to workspaces
        # Authenticated User Bogus workspace id
        invalid_response = self.make_authenticated_user_request(
            method='PUT',
            path='/api/v1/workspaces/%s/exit' % 'bogusx10')
        self.assertStatus(invalid_response, 404)
        # Workspace Owner Bogus workspace id
        invalid_response = self.make_authenticated_workspace_owner_request(
            method='PUT',
            path='/api/v1/workspaces/%s/exit' % 'bogusx10')
        self.assertStatus(invalid_response, 404)
        # Authenticated User - Trying to exit a workspace without
        response = self.make_authenticated_user_request(
            method='PUT',
            path='/api/v1/workspaces/%s/exit' % g.id)
        self.assertStatus(response, 403)
        # Workspace Owner of the workspace
        response = self.make_authenticated_workspace_owner_request(
            method='PUT',
            path='/api/v1/workspaces/%s/exit' % g.id)
        self.assertStatus(response, 422)  # owner of the workspace cannot exit the workspace

    def test_get_workspace_users(self):

        # Authenticated User, not a manager
        response = self.make_authenticated_user_request(
            method='GET',
            path='/api/v1/workspaces/%s/list_users' % self.known_workspace_id)
        self.assertStatus(response, 403)

        # Authenticated Workspace Owner , who does not own the workspace
        response = self.make_authenticated_workspace_owner_request(
            method='GET',
            path='/api/v1/workspaces/%s/list_users' % self.known_workspace_id_2,
            data=json.dumps({})
        )
        self.assertStatus(response, 403)

        # Authenticated Workspace Owner , is a Manager too
        response = self.make_authenticated_workspace_owner_request(
            method='GET',
            path='/api/v1/workspaces/%s/list_users' % self.known_workspace_id,
            data=json.dumps({})
        )
        self.assertStatus(response, 200)
        self.assertEqual(len(response.json), 2)  # 1 normal user + 1 manager (1 workspace owner not taken into account)

        # Authenticated Workspace Owner , is a Manager too
        response = self.make_authenticated_admin_request(
            method='GET',
            path='/api/v1/workspaces/%s/list_users' % self.known_workspace_id,
            data=json.dumps({})
        )
        self.assertStatus(response, 200)
        self.assertEqual(len(response.json), 2)  # 1 normal user + 1 manager (1 workspace owner not taken into account)

        # Authenticated Workspace Owner , is a Manager too
        response = self.make_authenticated_workspace_owner_request(
            method='GET',
            path='/api/v1/workspaces/%s/list_users?banned_list=true' % self.known_workspace_id,
        )
        self.assertStatus(response, 200)
        self.assertEqual(len(response.json), 1)  # 1 normal user

    def test_clear_users_from_workspace(self):
        name = 'WorkspaceToBeCleared'
        g = Workspace(name)
        u1 = User.query.filter_by(id=self.known_user_id).first()
        gu1_obj = WorkspaceUserAssociation(user=u1, workspace=g)
        u2 = User.query.filter_by(id=self.known_workspace_owner_id_2).first()
        gu2_obj = WorkspaceUserAssociation(user=u2, workspace=g, manager=True, owner=False)
        u3 = User.query.filter_by(id=self.known_workspace_owner_id).first()
        gu3_obj = WorkspaceUserAssociation(user=u3, workspace=g, manager=True, owner=True)
        g.users.append(gu1_obj)
        g.users.append(gu2_obj)
        g.users.append(gu3_obj)
        db.session.add(g)
        db.session.commit()
        # Anonymous
        response = self.make_request(
            method='POST',
            path='/api/v1/workspaces/%s/clear_users' % g.id,
            data=json.dumps({})
        )
        self.assert_401(response)
        # Authenticated user
        response = self.make_authenticated_user_request(
            method='POST',
            path='/api/v1/workspaces/%s/clear_users' % g.id,
            data=json.dumps({})
        )
        self.assert_403(response)
        # Authenticated workspace owner
        response = self.make_authenticated_workspace_owner_request(
            method='POST',
            path='/api/v1/workspaces/%s/clear_users' % g.id,
            data=json.dumps({})
        )
        self.assert_200(response)
        # Authenticated workspace owner, invalid workspace id
        invalid_response = self.make_authenticated_workspace_owner_request(
            method='POST',
            path='/api/v1/workspaces/%s/clear_users' % '',
            data=json.dumps({})
        )
        self.assertStatus(invalid_response, 405)
        # Authenticated workspace manager
        response = self.make_authenticated_workspace_owner2_request(
            method='POST',
            path='/api/v1/workspaces/%s/clear_users' % g.id,
            data=json.dumps({})
        )
        self.assert_403(response)
        # Admin, system.default workspace
        invalid_response = self.make_authenticated_admin_request(
            method='POST',
            path='/api/v1/workspaces/%s/clear_users' % self.system_default_workspace_id,
            data=json.dumps({})
        )
        self.assertStatus(invalid_response, 422)
        # Admin
        response = self.make_authenticated_admin_request(
            method='POST',
            path='/api/v1/workspaces/%s/clear_users' % g.id,
            data=json.dumps({})
        )
        self.assert_200(response)

    def test_get_clusters(self):
        # Anonymous
        response = self.make_request(path='/api/v1/clusters')
        self.assert_401(response)
        # Authenticated
        response = self.make_authenticated_user_request(path='/api/v1/clusters')
        self.assert_403(response)
        # Admin
        response = self.make_authenticated_admin_request(path='/api/v1/clusters')
        self.assert_200(response)

    def test_get_environment_templates(self):
        # Anonymous
        response = self.make_request(path='/api/v1/environment_templates')
        self.assert_401(response)
        # Authenticated User
        response = self.make_authenticated_user_request(path='/api/v1/environment_templates')
        self.assert_403(response)
        # Authenticated Workspace Owner
        response = self.make_authenticated_workspace_owner_request(path='/api/v1/environment_templates')
        self.assert_200(response)
        self.assertEqual(len(response.json), 1)
        # Admin
        response = self.make_authenticated_admin_request(path='/api/v1/environment_templates')
        self.assert_200(response)
        self.assertEqual(len(response.json), 2)

    def test_get_environment_template(self):
        # Existing environment
        # Anonymous
        response = self.make_request(path='/api/v1/environment_templates/%s' % self.known_environment_id)
        self.assert_401(response)
        # Authenticated User
        response = self.make_authenticated_user_request(path='/api/v1/environment_templates/%s' % self.known_template_id)
        self.assert_403(response)
        # Workspace Owner
        response = self.make_authenticated_workspace_owner_request(path='/api/v1/environment_templates/%s' % self.known_template_id)
        self.assert_200(response)
        # Admin
        response = self.make_authenticated_admin_request(path='/api/v1/environment_templates/%s' % self.known_template_id)
        self.assert_200(response)

        # non-existing environment
        # Anonymous
        response = self.make_request(path='/api/v1/environment_templates/%s' % uuid.uuid4().hex)
        self.assert_401(response)
        # Authenticated User
        response = self.make_authenticated_user_request(path='/api/v1/environment_templates/%s' % uuid.uuid4().hex)
        self.assert_403(response)
        # Workspace Owner
        response = self.make_authenticated_workspace_owner_request(path='/api/v1/environment_templates/%s' % uuid.uuid4().hex)
        self.assert_404(response)
        # Admin
        response = self.make_authenticated_admin_request(path='/api/v1/environment_templates/%s' % uuid.uuid4().hex)
        self.assert_404(response)

    def test_create_environment_template(self):
        # Anonymous
        data = {'name': 'test_environment_template_1', 'config': '', 'cluster': 'dummy'}
        response = self.make_request(
            method='POST',
            path='/api/v1/environment_templates',
            data=json.dumps(data))
        self.assert_401(response)
        # Authenticated User
        data = {'name': 'test_environment_template_1', 'config': '', 'cluster': 'dummy'}
        response = self.make_authenticated_user_request(
            method='POST',
            path='/api/v1/environment_templates',
            data=json.dumps(data))
        self.assert_403(response)
        # Authenticated Workspace Owner
        data = {'name': 'test_environment_template_1', 'config': '', 'cluster': 'dummy'}
        response = self.make_authenticated_workspace_owner_request(
            method='POST',
            path='/api/v1/environment_templates',
            data=json.dumps(data))
        self.assert_403(response)
        # Admin
        data = {'name': 'test_environment_template_1', 'config': {'foo': 'bar'}, 'cluster': 'dummy'}
        response = self.make_authenticated_admin_request(
            method='POST',
            path='/api/v1/environment_templates',
            data=json.dumps(data))
        self.assert_200(response)
        # Admin
        data = {
            'name': 'test_environment_template_2',
            'config': {'foo': 'bar', 'maximum_lifetime': '1h'},
            'allowed_attrs': {'allowed_attrs': ['maximum_lifetime']},
            'cluster': 'dummy_cluster_1'
        }
        response = self.make_authenticated_admin_request(
            method='POST',
            path='/api/v1/environment_templates',
            data=json.dumps(data))
        self.assert_200(response)

    def test_modify_environment_template(self):
        t = EnvironmentTemplate()
        t.name = 'TestTemplate'
        t.cluster = 'dummy_cluster_1'
        t.config = {'memory_limit': '512m', 'maximum_lifetime': '1h'}
        t.allowed_attrs = ['maximum_lifetime']
        t.is_enabled = True
        db.session.add(t)
        db.session.commit()

        # Anonymous
        data = {'name': 'test_environment_template_1', 'config': '', 'cluster': 'dummy'}
        response = self.make_request(
            method='PUT',
            path='/api/v1/environment_templates/%s' % t.id,
            data=json.dumps(data))
        self.assert_401(response)
        # Authenticated User
        data = {'name': 'test_environment_template_1', 'config': '', 'cluster': 'dummy'}
        response = self.make_authenticated_user_request(
            method='PUT',
            path='/api/v1/environment_templates/%s' % t.id,
            data=json.dumps(data))
        self.assert_403(response)
        # Authenticated Workspace Owner
        data = {'name': 'test_environment_template_1', 'config': '', 'cluster': 'dummy'}
        response = self.make_authenticated_workspace_owner_request(
            method='PUT',
            path='/api/v1/environment_templates/%s' % t.id,
            data=json.dumps(data))
        self.assert_403(response)
        # Admin
        data = {'name': 'test_environment_template_1', 'config': {'foo': 'bar'}, 'cluster': 'dummy'}
        response = self.make_authenticated_admin_request(
            method='PUT',
            path='/api/v1/environment_templates/%s' % t.id,
            data=json.dumps(data))
        self.assert_200(response)
        # Admin
        data = {
            'name': 'test_environment_template_2',
            'config': {'foo': 'bar', 'maximum_lifetime': '1h'},
            'allowed_attrs': {'allowed_attrs': ['maximum_lifetime']},
            'cluster': 'dummy_cluster_1'
        }
        response = self.make_authenticated_admin_request(
            method='PUT',
            path='/api/v1/environment_templates/%s' % t.id,
            data=json.dumps(data))
        self.assert_200(response)

    def test_copy_environment_template(self):

        # Authenticated User
        response = self.make_authenticated_user_request(
            method='PUT',
            path='/api/v1/environment_templates/template_copy/%s' % self.known_template_id)
        self.assert_403(response)
        # Authenticated Workspace Owner
        response = self.make_authenticated_workspace_owner_request(
            method='PUT',
            path='/api/v1/environment_templates/template_copy/%s' % self.known_template_id)
        self.assert_403(response)
        # Admin
        response = self.make_authenticated_admin_request(
            method='PUT',
            path='/api/v1/environment_templates/template_copy/%s' % self.known_template_id)
        self.assert_200(response)

    def test_get_environments(self):
        # Anonymous
        response = self.make_request(path='/api/v1/environments')
        self.assert_401(response)
        # Authenticated User for Workspace 1
        response = self.make_authenticated_user_request(path='/api/v1/environments')
        self.assert_200(response)
        self.assertEqual(len(response.json), 2)
        # Authenticated Workspace Owner for Workspace 1 and Normal User for Workspace 2
        response = self.make_authenticated_workspace_owner_request(path='/api/v1/environments')
        self.assert_200(response)
        self.assertEqual(len(response.json), 4)
        # Admin
        response = self.make_authenticated_admin_request(path='/api/v1/environments')
        self.assert_200(response)
        self.assertEqual(len(response.json), 5)
        response = self.make_authenticated_admin_request(path='/api/v1/environments?show_all=true')
        self.assert_200(response)
        self.assertEqual(len(response.json), 7)

    def test_get_environment(self):
        # Existing environment
        # Anonymous
        response = self.make_request(path='/api/v1/environments/%s' % self.known_environment_id)
        self.assert_401(response)
        # Authenticated
        response = self.make_authenticated_user_request(path='/api/v1/environments/%s' % self.known_environment_id)
        self.assert_200(response)
        # Admin
        response = self.make_authenticated_admin_request(path='/api/v1/environments/%s' % self.known_environment_id)
        self.assert_200(response)

        # non-existing environment
        # Anonymous
        response = self.make_request(path='/api/v1/environments/%s' % uuid.uuid4().hex)
        self.assert_401(response)
        # Authenticated
        response = self.make_authenticated_user_request(path='/api/v1/environments/%s' % uuid.uuid4().hex)
        self.assert_404(response)
        # Admin
        response = self.make_authenticated_admin_request(path='/api/v1/environments/%s' % uuid.uuid4().hex)
        self.assert_404(response)

    def test_get_environment_labels(self):
        # Authenticated
        response = self.make_authenticated_user_request(path='/api/v1/environments/%s' % self.known_environment_id)
        self.assert_200(response)
        labels = response.json['labels']
        expected_labels = ['label1', 'label with space', 'label2']
        self.assertEquals(labels, expected_labels, 'label array matches')

    def test_create_environment(self):
        # Anonymous
        data = {'name': 'test_environment_1', 'config': '', 'template_id': self.known_template_id, 'workspace_id': self.known_workspace_id}
        response = self.make_request(
            method='POST',
            path='/api/v1/environments',
            data=json.dumps(data))
        self.assert_401(response)
        # Authenticated
        data = {'name': 'test_environment_1', 'config': '', 'template_id': self.known_template_id, 'workspace_id': self.known_workspace_id}
        response = self.make_authenticated_user_request(
            method='POST',
            path='/api/v1/environments',
            data=json.dumps(data))
        self.assert_403(response)
        # Workspace Owner 1
        data = {'name': 'test_environment_1', 'config': {'foo': 'bar'}, 'template_id': self.known_template_id, 'workspace_id': self.known_workspace_id}
        data_2 = {'name': 'test_environment_2', 'config': {'foo': 'bar'}, 'template_id': self.known_template_id, 'workspace_id': self.known_workspace_id}
        response = self.make_authenticated_workspace_owner_request(
            method='POST',
            path='/api/v1/environments',
            data=json.dumps(data))
        self.assert_200(response)
        # Workspace Owner 2 (extra owner added to workspace 1)
        response = self.make_authenticated_workspace_owner2_request(
            method='POST',
            path='/api/v1/environments',
            data=json.dumps(data))
        self.assert_200(response)
        # check if possible to create more environments than quota in the workspace
        response = self.make_authenticated_workspace_owner2_request(
            method='POST',
            path='/api/v1/environments',
            data=json.dumps(data_2))
        self.assertStatus(response, 422)
        # Admin ignores quota
        data = {'name': 'test_environment_1', 'config': {'foo': 'bar'}, 'template_id': self.known_template_id, 'workspace_id': self.known_workspace_id}
        response = self.make_authenticated_admin_request(
            method='POST',
            path='/api/v1/environments',
            data=json.dumps(data))
        self.assert_200(response)

    def test_create_environment_lifespan_months(self):

        data = dict(
            name='test_environment_1',
            config=dict(foo='bar'),
            template_id=self.known_template_id,
            workspace_id=self.known_workspace_id,
        )

        # test invalid negative lifespan
        data['lifespan_months'] = -1
        response = self.make_authenticated_admin_request(
            method='POST',
            path='/api/v1/environments',
            data=json.dumps(data))
        self.assert_status(response, 422)

        # test setting a non-default value and compare it to expected value
        data['lifespan_months'] = '5'
        response = self.make_authenticated_admin_request(
            method='POST',
            path='/api/v1/environments',
            data=json.dumps(data))
        self.assert_status(response, 200)

        environment = Environment.query.filter_by(name='test_environment_1').first()
        environment_id = environment.id

        get_response = self.make_authenticated_workspace_owner_request(
            method='GET',
            path='/api/v1/environments/%s' % environment_id)
        self.assert_200(get_response)
        environment_json = get_response.json
        # drop timezone info from expiry_ts with utcfromtimestamp()
        expiry_ts = datetime.datetime.utcfromtimestamp(dateutil.parser.parse(environment_json['expiry_time']).timestamp())
        expected_expiry_ts = (datetime.datetime.utcnow() + dateutil.relativedelta.relativedelta(months=+5))
        # two second tolerance
        if abs(expiry_ts.timestamp() - expected_expiry_ts.timestamp()) > 2:
            self.fail('Expiry timestamp %s does not match %s' % (expiry_ts, expected_expiry_ts))

    def test_create_environment_full_config(self):
        # Workspace Owner
        data = {
            'name': 'test_environment_2',
            'config': {
                'foo': 'bar',
                'memory_limit': '1024m',
                'maximum_lifetime': '10h'
            },
            'template_id': self.known_template_id,
            'workspace_id': self.known_workspace_id
        }

        post_response = self.make_authenticated_workspace_owner_request(
            method='POST',
            path='/api/v1/environments',
            data=json.dumps(data))
        self.assert_200(post_response)

        environment = Environment.query.filter_by(name='test_environment_2').first()
        environment_id = environment.id

        get_response = self.make_authenticated_workspace_owner_request(
            method='GET',
            path='/api/v1/environments/%s' % environment_id)
        self.assert_200(get_response)
        environment_json = get_response.json
        self.assertNotIn('foo', environment_json['full_config'])  # 'foo' exists in environment config but not in template config
        self.assertNotEqual(environment_json['full_config']['memory_limit'], '1024m')  # environment config value (memory_limit is not an allowed attribute)
        self.assertEquals(environment_json['full_config']['memory_limit'], '512m')  # environment template value (memory_limit is not an allowed attribute)
        self.assertEquals(environment_json['full_config']['maximum_lifetime'], '10h')  # environment config value overrides template value (allowed attribute)

    def test_create_modify_environment_timeformat(self):

        form_data = [
            {'name': 'test_environment_2', 'config': {"name": "foo", "maximum_lifetime": '1d 1h 40m'}, 'template_id': self.known_template_id, 'workspace_id': self.known_workspace_id},
            {'name': 'test_environment_2', 'config': {"name": "foo", "maximum_lifetime": '1d1h40m'}, 'template_id': self.known_template_id, 'workspace_id': self.known_workspace_id},
            {'name': 'test_environment_2', 'config': {"name": "foo", "maximum_lifetime": '1d'}, 'template_id': self.known_template_id, 'workspace_id': self.known_workspace_id},
            {'name': 'test_environment_2', 'config': {"name": "foo", "maximum_lifetime": '10h'}, 'template_id': self.known_template_id, 'workspace_id': self.known_workspace_id},
            {'name': 'test_environment_2', 'config': {"name": "foo", "maximum_lifetime": '30m'}, 'template_id': self.known_template_id, 'workspace_id': self.known_workspace_id},
            {'name': 'test_environment_2', 'config': {"name": "foo", "maximum_lifetime": '5h30m'}, 'template_id': self.known_template_id, 'workspace_id': self.known_workspace_id},
            {'name': 'test_environment_2', 'config': {"name": "foo", "maximum_lifetime": '1d12h'}, 'template_id': self.known_template_id, 'workspace_id': self.known_workspace_id},
            {'name': 'test_environment_2', 'config': {"name": "foo", "maximum_lifetime": '1d 10m'}, 'template_id': self.known_template_id, 'workspace_id': self.known_workspace_id},
            {'name': 'test_environment_2', 'config': {"name": "foo", "maximum_lifetime": '1h 1m'}, 'template_id': self.known_template_id, 'workspace_id': self.known_workspace_id},
            {'name': 'test_environment_2', 'config': {"name": "foo", "maximum_lifetime": '0d2h 30m'}, 'template_id': self.known_template_id, 'workspace_id': self.known_workspace_id},
            {'name': 'test_environment_2', 'config': {"name": "foo", "maximum_lifetime": ''}, 'template_id': self.known_template_id, 'workspace_id': self.known_workspace_id}
        ]
        expected_lifetimes = [92400, 92400, 86400, 36000, 1800, 19800, 129600, 87000, 3660, 9000, 3600]

        self.assertEquals(len(form_data), len(expected_lifetimes))

        for data, expected_lifetime in zip(form_data, expected_lifetimes):
            response = self.make_authenticated_admin_request(
                method='POST',
                path='/api/v1/environments',
                data=json.dumps(data))
            self.assert_200(response,
                            'testing time %s,%d failed' % (data['config']['maximum_lifetime'], expected_lifetime))

            put_response = self.make_authenticated_admin_request(
                method='PUT',
                path='/api/v1/environments/%s' % self.known_environment_id_2,
                data=json.dumps(data))
            self.assert_200(put_response)

            environment = Environment.query.filter_by(id=self.known_environment_id_2).first()
            self.assertEqual(environment.maximum_lifetime, expected_lifetime)

    def test_modify_environment_activate(self):
        data = {
            'name': 'test_environment_activate',
            'config': {
                "maximum_lifetime": "0h"
            },
            'template_id': self.known_template_id,
            'workspace_id': self.known_workspace_id
        }

        # Authenticated Normal User
        put_response = self.make_authenticated_user_request(
            method='PUT',
            path='/api/v1/environments/%s' % self.known_environment_id_disabled,
            data=json.dumps(data))
        self.assert_403(put_response)
        # Workspace owner not an owner of the environment workspace 2
        put_response = self.make_authenticated_workspace_owner_request(
            method='PUT',
            path='/api/v1/environments/%s' % self.known_environment_id_disabled_2,
            data=json.dumps(data))
        self.assert_403(put_response)
        # Workspace Owner is an owner of the environment workspace 1
        put_response = self.make_authenticated_workspace_owner_request(
            method='PUT',
            path='/api/v1/environments/%s' % self.known_environment_id_disabled,
            data=json.dumps(data))
        self.assert_200(put_response)
        # Workspace owner 2 is part of the environment workspace 1 as an additional owner
        put_response = self.make_authenticated_workspace_owner2_request(
            method='PUT',
            path='/api/v1/environments/%s' % self.known_environment_id_disabled,
            data=json.dumps(data))
        self.assert_200(put_response)
        # Workspace owner 2 owner of the environment workspace 2
        put_response = self.make_authenticated_workspace_owner2_request(
            method='PUT',
            path='/api/v1/environments/%s' % self.known_environment_id_disabled,
            data=json.dumps(data))
        self.assert_200(put_response)
        # Admin
        put_response = self.make_authenticated_admin_request(
            method='PUT',
            path='/api/v1/environments/%s' % self.known_environment_id_disabled,
            data=json.dumps(data))
        self.assert_200(put_response)

        environment = Environment.query.filter_by(id=self.known_environment_id_disabled).first()
        self.assertEqual(environment.is_enabled, False)

    def test_modify_environment_config_magic_vars_admin(self):
        data = {
            'name': 'test_environment_2',
            'config': {
                "name": "foo_modify",
                "maximum_lifetime": '0d2h30m',
                "cost_multiplier": '0.1',
            },
            'template_id': self.known_template_id,
            'workspace_id': self.known_workspace_id
        }
        put_response = self.make_authenticated_admin_request(
            method='PUT',
            path='/api/v1/environments/%s' % self.known_environment_id_2,
            data=json.dumps(data))
        self.assert_200(put_response)

        environment = Environment.query.filter_by(id=self.known_environment_id_2).first()
        self.assertEqual(environment.maximum_lifetime, 9000)
        self.assertEqual(environment.cost_multiplier, 0.1)

    def test_create_environment_admin_invalid_data(self):
        invalid_form_data = [
            {'name': '', 'config': 'foo: bar', 'template_id': self.known_template_id, 'workspace_id': self.known_workspace_id},
            {'name': 'test_environment_2', 'config': '', 'template_id': self.known_template_id, 'workspace_id': self.known_workspace_id},
            {'name': 'test_environment_2', 'config': 'foo: bar', 'template_id': self.known_template_id},
            {'name': 'test_environment_2', 'config': 'foo: bar', 'workspace_id': self.known_workspace_id},
            {'name': 'test_environment_2', 'config': {"name": "foo", "maximum_lifetime": ' '}, 'template_id': self.known_template_id, 'workspace_id': self.known_workspace_id},
            {'name': 'test_environment_2', 'config': {"name": "foo", "maximum_lifetime": '10 100'}, 'template_id': self.known_template_id, 'workspace_id': self.known_workspace_id},
            {'name': 'test_environment_2', 'config': {"name": "foo", "maximum_lifetime": '1hh'}, 'template_id': self.known_template_id, 'workspace_id': self.known_workspace_id},
            {'name': 'test_environment_2', 'config': {"name": "foo", "maximum_lifetime": '-1m'}, 'template_id': self.known_template_id, 'workspace_id': self.known_workspace_id},
            {'name': 'test_environment_2', 'config': {"name": "foo", "maximum_lifetime": '-10h'}, 'template_id': self.known_template_id, 'workspace_id': self.known_workspace_id},
            {'name': 'test_environment_2', 'config': {"name": "foo", "maximum_lifetime": '2d -10h'}, 'template_id': self.known_template_id, 'workspace_id': self.known_workspace_id},
            {'name': 'test_environment_2', 'config': {"name": "foo", "maximum_lifetime": '30s'}, 'template_id': self.known_template_id, 'workspace_id': self.known_workspace_id},
            {'name': 'test_environment_2', 'config': {"name": "foo", "maximum_lifetime": '10h'}, 'template_id': self.known_template_id, 'workspace_id': 'unknown'},
            {'name': 'test_environment_2', 'config': {"name": "foo", "maximum_lifetime": '10h'}, 'template_id': 'unknown', 'workspace_id': self.known_workspace_id},
        ]
        for data in invalid_form_data:
            response = self.make_authenticated_admin_request(
                method='POST',
                path='/api/v1/environments',
                data=json.dumps(data))
            self.assertStatus(response, 422)

    def test_create_environment_template_admin_invalid_data(self):
        invalid_form_data = [
            {'name': '', 'config': 'foo: bar'},
            {'name': 'test_template_2', 'config': ''},
            {'name': 'test_template_2', 'config': 'foo: bar'},
            {'name': 'test_template_2', 'config': {"name": "foo", "maximum_lifetime": ' '}},
            {'name': 'test_template_2', 'config': {"name": "foo", "maximum_lifetime": '10 100'}},
            {'name': 'test_template_2', 'config': {"name": "foo", "maximum_lifetime": '1hh'}},
            {'name': 'test_template_2', 'config': {"name": "foo", "maximum_lifetime": '-1m'}},
            {'name': 'test_template_2', 'config': {"name": "foo", "maximum_lifetime": '-10h'}},
            {'name': 'test_template_2', 'config': {"name": "foo", "maximum_lifetime": '2d -10h'}},
            {'name': 'test_template_2', 'config': {"name": "foo", "maximum_lifetime": '30s'}},
            {'name': 'test_template_2', 'config': {"name": "foo", "maximum_lifetime": '10h'}}
        ]
        for data in invalid_form_data:
            response = self.make_authenticated_admin_request(
                method='POST',
                path='/api/v1/environment_templates',
                data=json.dumps(data))
            self.assertStatus(response, 422)

    def test_create_environment_workspace_owner_invalid_data(self):
        invalid_form_data = [
            {'name': '', 'config': 'foo: bar', 'template_id': self.known_template_id, 'workspace_id': self.known_workspace_id},
            {'name': 'test_environment_2', 'config': '', 'template_id': self.known_template_id, 'workspace_id': self.known_workspace_id},
            {'name': 'test_environment_2', 'config': 'foo: bar', 'template_id': self.known_template_id},
            {'name': 'test_environment_2', 'config': 'foo: bar', 'workspace_id': self.known_workspace_id},
            {'name': 'test_environment_2', 'config': {"name": "foo", "maximum_lifetime": '10h'}, 'template_id': self.known_template_id, 'workspace_id': 'unknown'},
            {'name': 'test_environment_2', 'config': {"name": "foo", "maximum_lifetime": '10h'}, 'template_id': 'unknown', 'workspace_id': self.known_workspace_id},
        ]
        for data in invalid_form_data:
            response = self.make_authenticated_workspace_owner_request(
                method='POST',
                path='/api/v1/environments',
                data=json.dumps(data))
            self.assertStatus(response, 422)

        # Workspace owner is a user but not the owner of the workspace with id : known_workspace_id_2
        invalid_workspace_data = {'name': 'test_environment_2', 'config': {"name": "foo"}, 'template_id': self.known_template_id, 'workspace_id': self.known_workspace_id_2}
        response = self.make_authenticated_workspace_owner_request(
            method='POST',
            path='/api/v1/environments',
            data=json.dumps(invalid_workspace_data))
        self.assertStatus(response, 403)

        put_response = self.make_authenticated_workspace_owner_request(
            method='PUT',
            path='/api/v1/environments/%s' % self.known_environment_id_g2,
            data=json.dumps(invalid_workspace_data))
        self.assertStatus(put_response, 403)

    def test_copy_environments(self):

        # Authenticated User
        response = self.make_authenticated_user_request(
            method='PUT',
            path='/api/v1/environments/environment_copy/%s' % self.known_environment_id)
        self.assert_403(response)
        # Authenticated Workspace Owner
        response = self.make_authenticated_workspace_owner_request(
            method='PUT',
            path='/api/v1/environments/environment_copy/%s' % self.known_environment_id)
        self.assert_200(response)
        # Admin
        response = self.make_authenticated_admin_request(
            method='PUT',
            path='/api/v1/environments/environment_copy/%s' % self.known_environment_id)
        self.assert_200(response)

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
        data = {'eppn': 'test@example.org', 'is_admin': True, 'email_id': 'test@example.org'}
        response = self.make_authenticated_admin_request(
            method='POST',
            path='/api/v1/users',
            data=json.dumps(data))
        self.assert_200(response)
        user = User.query.filter_by(eppn='test@example.org').first()
        self.assertIsNotNone(user)
        self.assertFalse(user.is_active)
        self.assertTrue(user.is_admin)

        data = {'eppn': 'test2@example.org', 'is_admin': False, 'email_id': 'test2@example.org'}
        response = self.make_authenticated_admin_request(
            method='POST',
            path='/api/v1/users',
            data=json.dumps(data))
        self.assert_200(response)
        user = User.query.filter_by(eppn='test2@example.org').first()
        self.assertIsNotNone(user)
        self.assertFalse(user.is_active)
        self.assertFalse(user.is_admin)

    def test_admin_delete_invited_user_deletes_activation_tokens(self):
        data = {'eppn': 'test@example.org', 'email_id': 'test@example.org'}
        response = self.make_authenticated_admin_request(
            method='POST',
            path='/api/v1/users',
            data=json.dumps(data))
        self.assert_200(response)
        user = User.query.filter_by(eppn='test@example.org').first()
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
        user = User.query.filter_by(eppn='test@example.org').first()
        self.assertIsNone(user)
        data = {'eppn': 'test@example.org', 'password': None, 'is_admin': True, 'email_id': 'test@example.org'}
        response = self.make_authenticated_admin_request(
            method='POST',
            path='/api/v1/users',
            data=json.dumps(data))
        self.assert_200(response)
        user = User.query.filter_by(eppn='test@example.org').first()
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
        user = User.query.filter_by(eppn='test@example.org').first()
        default_workspace = Workspace.query.filter_by(name='System.default').first()
        self.assertIsNotNone(user)
        self.assertTrue(user.is_active)

        user_in_workspace = WorkspaceUserAssociation.query.filter_by(workspace_id=default_workspace.id, user_id=user.id).first()
        self.assertIsNotNone(user_in_workspace)  # Each active user gets added in the system default workspace

    def test_send_recovery_link(self):
        # positive test for existing user
        user = User.query.filter_by(id=self.known_user_id).first()
        self.assertIsNotNone(user)
        if user.email_id:
            data = {'email_id': user.email_id}
        else:
            data = {'email_id': user.eppn}
        response = self.make_request(
            method='POST',
            path='/api/v1/activations',
            data=json.dumps(data))
        self.assert_200(response)

        # negative test for existing user with too many tokens
        for i in range(1, activations.MAX_ACTIVATION_TOKENS_PER_USER):
            response = self.make_request(
                method='POST',
                path='/api/v1/activations',
                data=json.dumps(data))
            self.assert_200(response)
        response = self.make_request(
            method='POST',
            path='/api/v1/activations',
            data=json.dumps(data))
        self.assert_403(response)

        # negative test for non-existing user
        user = User.query.filter_by(eppn='not.here@example.org').first()
        self.assertIsNone(user)
        data = {'email_id': 'not.here@example.org'}
        response = self.make_request(
            method='POST',
            path='/api/v1/activations',
            data=json.dumps(data))
        self.assert_404(response)

    def test_anonymous_create_instance(self):
        data = {'environment_id': self.known_environment_id}
        response = self.make_request(
            method='POST',
            path='/api/v1/instances',
            data=json.dumps(data))
        self.assert_401(response)

    def test_user_create_instance(self):
        # User is not a part of the workspace (Workspace2)
        data = {'environment': self.known_environment_id_g2}
        response = self.make_authenticated_user_request(
            method='POST',
            path='/api/v1/instances',
            data=json.dumps(data))
        self.assert_403(response)
        # User is a part of the workspace (Workspace1)
        data = {'environment': self.known_environment_id}
        response = self.make_authenticated_user_request(
            method='POST',
            path='/api/v1/instances',
            data=json.dumps(data))
        self.assert_200(response)

    def test_user_create_instance_environment_disabled(self):
        response = self.make_authenticated_user_request(
            method='POST',
            path='/api/v1/instances',
            data=json.dumps({'environment': self.known_environment_id_disabled}),
        )
        self.assert_404(response)

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
        # Workspace Manager (His own instance + other instances from his managed workspaces)
        response = self.make_authenticated_workspace_owner_request(path='/api/v1/instances')
        self.assert_200(response)
        self.assertEqual(len(response.json), 3)
        # Admin
        response = self.make_authenticated_admin_request(path='/api/v1/instances')
        self.assert_200(response)
        self.assertEqual(len(response.json), 4)
        response = self.make_authenticated_admin_request(path='/api/v1/instances?show_only_mine=1')
        self.assert_200(response)
        self.assertEqual(len(response.json), 1)

    def test_get_instance(self):
        # Anonymous
        response = self.make_request(path='/api/v1/instances/%s' % self.known_instance_id)
        self.assert_401(response)
        # Authenticated
        response = self.make_authenticated_user_request(
            method='GET',
            path='/api/v1/instances/%s' % self.known_instance_id
        )
        self.assert_200(response)
        # Admin
        response = self.make_authenticated_admin_request(
            method='GET',
            path='/api/v1/instances/%s' % self.known_instance_id
        )
        self.assert_200(response)

        response = self.make_authenticated_user_request(
            method='POST',
            path='/api/v1/instances/%s' % self.known_instance_id,
            data=json.dumps({'send_email': False})
        )
        self.assert_200(response)

        response = self.make_authenticated_user_request(
            method='POST',
            path='/api/v1/instances/%s' % self.known_instance_id,
            data=json.dumps({'send_email': False})
        )

        self.assert_200(response)

    def test_delete_instance(self):
        environment = Environment.query.filter_by(id=self.known_environment_id).first()
        user = User.query.filter_by(id=self.known_user_id).first()
        i1 = Instance(environment, user)
        db.session.add(i1)
        db.session.commit()
        # Anonymous
        response = self.make_request(
            method='DELETE',
            path='/api/v1/instances/%s' % i1.id
        )
        self.assert_401(response)
        # Authenticated User of the instance
        response = self.make_authenticated_user_request(
            method='DELETE',
            path='/api/v1/instances/%s' % i1.id
        )
        self.assert_202(response)

        i2 = Instance(environment, user)
        db.session.add(i2)
        db.session.commit()
        # Authenticated Workspace Owner of the instance
        response = self.make_authenticated_workspace_owner_request(
            method='DELETE',
            path='/api/v1/instances/%s' % i2.id
        )
        self.assert_202(response)

        i3 = Instance(environment, user)
        db.session.add(i3)
        db.session.commit()
        # Authenticated Workspace Manager of the instance
        response = self.make_authenticated_workspace_owner2_request(
            method='DELETE',
            path='/api/v1/instances/%s' % i3.id
        )
        self.assert_202(response)

        i4 = Instance(environment, user)
        db.session.add(i4)
        db.session.commit()
        # Admin
        response = self.make_authenticated_admin_request(
            method='DELETE',
            path='/api/v1/instances/%s' % i4.id
        )
        self.assert_202(response)

        environment2 = Environment.query.filter_by(id=self.known_environment_id_g2).first()
        user2 = User.query.filter_by(id=self.known_workspace_owner_id_2).first()
        i5 = Instance(environment2, user2)
        db.session.add(i5)
        db.session.commit()
        # User is not part of the workspace
        response = self.make_authenticated_user_request(
            method='DELETE',
            path='/api/v1/instances/%s' % i5.id
        )
        self.assert_404(response)
        # Is just a Normal user of the workspace who didn't spawn the instance
        response = self.make_authenticated_workspace_owner_request(
            method='DELETE',
            path='/api/v1/instances/%s' % i5.id
        )
        self.assert_403(response)
        # Authenticated Workspace Owner of the workspace
        response = self.make_authenticated_workspace_owner2_request(
            method='DELETE',
            path='/api/v1/instances/%s' % i5.id
        )
        self.assert_202(response)

    def test_instance_logs(self):
        epoch_time = time.time()
        log_record = {
            'log_level': 'INFO',
            'log_type': 'provisioning',
            'timestamp': epoch_time,
            'message': 'log testing'
        }
        response_patch = self.make_authenticated_admin_request(
            method='PATCH',
            path='/api/v1/instances/%s/logs' % self.known_instance_id,
            data=json.dumps({'log_record': log_record})
        )
        self.assert_200(response_patch)

        response_get = self.make_authenticated_user_request(
            method='GET',
            path='/api/v1/instances/%s/logs' % self.known_instance_id,
            data=json.dumps({'log_type': 'provisioning'})
        )
        self.assert_200(response_get)
        self.assertEquals(response_get.json[0]['timestamp'], epoch_time)

        response_instance_get = self.make_authenticated_user_request(
            path='/api/v1/instances/%s' % self.known_instance_id
        )
        self.assert_200(response_instance_get)
        self.assertEquals(response_instance_get.json['logs'][0]['timestamp'], epoch_time)

    def test_get_activation_url(self):

        t1 = ActivationToken(User.query.filter_by(id=self.known_user_id).first())
        known_token = t1.token
        db.session.add(t1)

        # Anonymous
        response = self.make_request(path='/api/v1/users/%s/user_activation_url' % self.known_user_id)
        self.assert_401(response)
        response2 = self.make_request(path='/api/v1/users/%s/user_activation_url' % '0xBogus')
        self.assert_401(response2)
        # Authenticated
        response = self.make_authenticated_user_request(path='/api/v1/users/%s/user_activation_url' % self.known_user_id)
        self.assert_403(response)
        response2 = self.make_authenticated_user_request(path='/api/v1/users/%s/user_activation_url' % '0xBogus')
        self.assert_403(response2)
        # Admin
        response = self.make_authenticated_admin_request(
            path='/api/v1/users/%s/user_activation_url' % self.known_user_id
        )
        self.assert_200(response)
        token_check = known_token in response.json['activation_url']
        self.assertTrue(token_check)
        response2 = self.make_authenticated_admin_request(path='/api/v1/users/%s/activation_url' % '0xBogus')
        self.assert_404(response2)

    def test_update_admin_quota_relative(self):
        response = self.make_authenticated_admin_request(
            path='/api/v1/users'
        )
        # entry 3 is the workspace owner
        assert response.json[2]['workspace_quota'] == 2
        user_id = response.json[2]['id']
        response2 = self.make_authenticated_admin_request(
            method='PUT',
            path='/api/v1/quota/%s' % user_id,
            data=json.dumps({'type': 'relative', 'value': 10, 'credits_type': 'workspace_quota_value'}))
        self.assertEqual(response2.status_code, 200)
        response = self.make_authenticated_admin_request(
            path='/api/v1/users'
        )
        self.assertEqual(user_id, response.json[2]['id'])
        self.assertEqual(response.json[2]['workspace_quota'], 12)

    def test_user_cannot_update_user_quota_absolute(self):
        user_id = self.known_workspace_owner_id_2
        response2 = self.make_authenticated_user_request(
            method='PUT',
            path='/api/v1/quota/%s' % user_id,
            data=json.dumps({'type': "absolute", 'value': 10, 'credits_type': 'workspace_quota_value'}))
        self.assert_403(response2)

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
            path='/api/v1/quota/%s' % self.known_user_id,
            data=json.dumps({'type': "invalid_type", 'value': 10}))
        self.assertStatus(response, 422)
        response = self.make_authenticated_admin_request(
            method='PUT',
            path='/api/v1/quota/%s' % self.known_user_id,
            data=json.dumps({'type': "relative", 'value': "foof"}))
        self.assertStatus(response, 422)

    def test_user_cannot_see_other_users(self):
        response = self.make_authenticated_user_request(
            path='/api/v1/quota/%s' % self.known_admin_id
        )
        self.assert_403(response)

    def test_admin_acquire_lock(self):
        unique_id = 'abc123'
        response = self.make_authenticated_admin_request(
            method='PUT',
            path='/api/v1/locks/%s' % unique_id,
            data=json.dumps(dict(owner='test'))
        )
        self.assertStatus(response, 200)

        response2 = self.make_authenticated_admin_request(
            method='PUT',
            path='/api/v1/locks/%s' % unique_id,
            data=json.dumps(dict(owner='test'))
        )
        self.assertStatus(response2, 409)

        response3 = self.make_authenticated_admin_request(
            method='DELETE',
            path='/api/v1/locks/%s' % unique_id
        )

        self.assertStatus(response3, 200)

        response4 = self.make_authenticated_admin_request(
            method='DELETE',
            path='/api/v1/locks/%s' % unique_id
        )

        self.assertStatus(response4, 404)

        response = self.make_authenticated_admin_request(
            method='PUT',
            path='/api/v1/locks/%s' % unique_id,
            data=json.dumps(dict(owner='test'))
        )
        self.assertStatus(response, 200)

        # test deleting with an owner filter that does not match
        response = self.make_authenticated_admin_request(
            method='DELETE',
            path='/api/v1/locks/%s?owner=foo' % unique_id
        )
        self.assertStatus(response, 404)

        # test deleting with an owner filter
        response = self.make_authenticated_admin_request(
            method='DELETE',
            path='/api/v1/locks/%s?owner=test' % unique_id
        )
        self.assertStatus(response, 200)

    def test_user_and_workspace_owner_export_environment_templates(self):
        response = self.make_authenticated_user_request(path='/api/v1/import_export/environment_templates')
        self.assertStatus(response, 403)

        response = self.make_authenticated_workspace_owner_request(path='/api/v1/import_export/environment_templates')
        self.assertStatus(response, 403)

    def test_admin_export_environment_templates(self):

        response = self.make_authenticated_admin_request(path='/api/v1/import_export/environment_templates')
        self.assertStatus(response, 200)
        self.assertEquals(len(response.json), 2)  # There were total 2 templates initialized during setup

    def test_user_and_workspace_owner_import_environment_templates(self):

        environments_data = [
            {'name': 'foo',
             'config': {
                 'maximum_lifetime': '1h'
             },
             'cluster_name': 'dummy',
             'allowed_attrs': ['maximum_lifetime']
             },
            {'name': 'foobar',
             'config': {
                 'maximum_lifetime': '1d 10m', 'description': 'dummy environment'
             },
             'cluster_name': 'dummy',
             'allowed_attrs': []
             }
        ]
        # Authenticated User
        for environment_item in environments_data:
            response = self.make_authenticated_user_request(
                method='POST',
                path='/api/v1/import_export/environment_templates',
                data=json.dumps(environment_item))
            self.assertEqual(response.status_code, 403)
        # Workspace Owner
        for environment_item in environments_data:
            response = self.make_authenticated_workspace_owner_request(
                method='POST',
                path='/api/v1/import_export/environment_templates',
                data=json.dumps(environment_item))
            self.assertEqual(response.status_code, 403)

    def test_admin_import_environment_templates(self):

        environments_data = [
            {'name': 'foo',
             'config': {
                 'maximum_lifetime': '1h'
             },
             'cluster_name': 'dummy_cluster_1',
             'allowed_attrs': ['maximum_lifetime']
             },
            {'name': 'foobar',
             'config': {
                 'maximum_lifetime': '1d 10m', 'description': 'dummy environment'
             },
             'cluster_name': 'dummy_cluster_1',
             'allowed_attrs': []
             }
        ]
        # Admin
        for environment_item in environments_data:
            response = self.make_authenticated_admin_request(
                method='POST',
                path='/api/v1/import_export/environment_templates',
                data=json.dumps(environment_item))
            self.assertEqual(response.status_code, 200)

    def test_anonymous_export_environments(self):
        response = self.make_request(path='/api/v1/import_export/environments')
        self.assertStatus(response, 401)

    def test_user_export_environments(self):
        response = self.make_authenticated_user_request(path='/api/v1/import_export/environments')
        self.assertStatus(response, 403)

    def test_workspace_owner_export_environments(self):
        response = self.make_authenticated_workspace_owner_request(path='/api/v1/import_export/environments')
        self.assertStatus(response, 200)
        self.assertEquals(len(response.json), 3)

    def test_admin_export_environments(self):

        response = self.make_authenticated_admin_request(path='/api/v1/import_export/environments')
        self.assertStatus(response, 200)
        self.assertEquals(len(response.json), 7)  # There were total 7 environments initialized during setup

    def test_anonymous_import_environments(self):

        environments_data = [
            {'name': 'foo',
             'config': {
                 'maximum_lifetime': '1h'
             },
             'template_name': 'TestTemplate',
             'workspace_name': 'Workspace1'
             },
            {'name': 'foobar',
             'config': {
                 'maximum_lifetime': '1d 10m', 'description': 'dummy environment'
             },
             'template_name': 'TestTemplate',
             'workspace_name': 'Workspace1'
             }
        ]

        for environment_item in environments_data:
            response = self.make_request(  # Test for authenticated user
                method='POST',
                path='/api/v1/import_export/environments',
                data=json.dumps(environment_item))
            self.assertEqual(response.status_code, 401)

    def test_user_import_environments(self):

        environments_data = [
            {'name': 'foo',
             'config': {
                 'maximum_lifetime': '1h'
             },
             'template_name': 'TestTemplate',
             'workspace_name': 'Workspace1'
             },
            {'name': 'foobar',
             'config': {
                 'maximum_lifetime': '1d 10m', 'description': 'dummy environment'
             },
             'template_name': 'TestTemplate',
             'workspace_name': 'Workspace1'
             }
        ]

        for environment_item in environments_data:
            response = self.make_authenticated_user_request(  # Test for authenticated user
                method='POST',
                path='/api/v1/import_export/environments',
                data=json.dumps(environment_item))
            self.assertEqual(response.status_code, 403)

    def test_admin_import_environments(self):

        environments_data = [
            {'name': 'foo',
             'config': {
                 'maximum_lifetime': '1h'
             },
             'template_name': 'EnabledTestTemplate',
             'workspace_name': 'Workspace1'
             },
            {'name': 'foobar',
             'config': {
                 'maximum_lifetime': '1d 10m', 'description': 'dummy environment'
             },
             'template_name': 'EnabledTestTemplate',
             'workspace_name': 'Workspace1'
             }
        ]

        for environment_item in environments_data:
            response = self.make_authenticated_admin_request(
                method='POST',
                path='/api/v1/import_export/environments',
                data=json.dumps(environment_item))
            self.assertEqual(response.status_code, 200)

        environment_invalid1 = {'name': 'foo', 'template_name': 'EnabledTestTemplate', 'workspace_name': 'Workspace1'}
        response1 = self.make_authenticated_admin_request(
            method='POST',
            path='/api/v1/import_export/environments',
            data=json.dumps(environment_invalid1))
        self.assertEqual(response1.status_code, 422)

        environment_invalid2 = {'name': '', 'template_name': 'EnabledTestTemplate', 'workspace_name': 'Workspace1'}
        response2 = self.make_authenticated_admin_request(
            method='POST',
            path='/api/v1/import_export/environments',
            data=json.dumps(environment_invalid2))
        self.assertEqual(response2.status_code, 422)

        environment_invalid3 = {'name': 'foo', 'config': {'maximum_lifetime': '1h'}, 'template_name': '', 'workspace_name': 'Workspace1'}
        response3 = self.make_authenticated_admin_request(
            method='POST',
            path='/api/v1/import_export/environments',
            data=json.dumps(environment_invalid3))
        self.assertEqual(response3.status_code, 422)

        environment_invalid4 = {'name': 'foo', 'config': {'maximum_lifetime': '1h'}, 'template_name': 'EnabledTestTemplate', 'workspace_name': ''}
        response3 = self.make_authenticated_admin_request(
            method='POST',
            path='/api/v1/import_export/environments',
            data=json.dumps(environment_invalid4))
        self.assertEqual(response3.status_code, 422)

    def test_anonymous_get_messages(self):
        response = self.make_request(
            path='/api/v1/messages'
        )
        self.assert_401(response)

    def test_user_get_messages(self):
        response = self.make_authenticated_user_request(
            path='/api/v1/messages'
        )
        self.assert_200(response)
        self.assertEqual(len(response.json), 2)

    def test_anonymous_post_message(self):
        response = self.make_request(
            method='POST',
            path='/api/v1/messages',
            data=json.dumps({'subject': 'test subject', 'message': 'test message'})
        )
        self.assert_401(response)

    def test_user_post_message(self):
        response = self.make_authenticated_user_request(
            method='POST',
            path='/api/v1/messages',
            data=json.dumps({'subject': 'test subject', 'message': 'test message'})
        )
        self.assert_403(response)

    def test_admin_post_message(self):
        response = self.make_authenticated_admin_request(
            method='POST',
            path='/api/v1/messages',
            data=json.dumps({'subject': 'test subject', 'message': 'test message'})
        )
        self.assert_200(response)
        response = self.make_authenticated_user_request(
            path='/api/v1/messages'
        )
        self.assert_200(response)
        self.assertEqual(len(response.json), 3)

    def test_user_mark_message_as_seen(self):
        response = self.make_authenticated_user_request(
            method='PATCH',
            path='/api/v1/messages/%s' % self.known_message_id,
            data=json.dumps({'send_mail': False})
        )
        self.assert_200(response)

        response = self.make_authenticated_user_request(
            path='/api/v1/messages'
        )
        self.assert_200(response)
        self.assertEqual(len(response.json), 1)

        response = self.make_authenticated_user_request(
            method='PATCH',
            path='/api/v1/messages/%s' % self.known_message2_id,
            data=json.dumps({'send_mail': False})
        )
        self.assert_200(response)

        response = self.make_authenticated_user_request(
            path='/api/v1/messages'
        )
        self.assert_200(response)
        self.assertEqual(len(response.json), 0)

    def test_admin_update_message(self):
        subject_topic = 'NotificationABC'
        response = self.make_authenticated_admin_request(
            method='PUT',
            path='/api/v1/messages/%s' % self.known_message_id,
            data=json.dumps({'subject': subject_topic, 'message': 'XXX'}))
        self.assert_200(response)

        response = self.make_authenticated_admin_request(
            path='/api/v1/messages/%s' % self.known_message_id)
        self.assert_200(response)
        self.assertEqual(response.json['subject'], subject_topic)

    def test_admin_fetch_instance_usage_stats(self):
        response = self.make_authenticated_admin_request(
            method='GET',
            path='/api/v1/stats')
        self.assertStatus(response, 200)

        self.assertEqual(len(response.json['environments']), 3)  # 2 items as the instances are running across three environments
        for environment in response.json['environments']:
            # Tests for environment b2 EnabledTestEnvironment'
            if environment['name'] == 'EnabledTestEnvironment':
                self.assertEqual(environment['users'], 1)
                self.assertEqual(environment['launched_instances'], 1)
                self.assertEqual(environment['running_instances'], 1)
            # Tests for environment b3 EnabledTestEnvironmentClientIp
            elif environment['name'] == 'EnabledTestEnvironmentClientIp':
                self.assertEqual(environment['users'], 2)
                self.assertEqual(environment['launched_instances'], 3)
                self.assertEqual(environment['running_instances'], 2)
            # b4 EnabledTestEnvironmentOtherWorkspace
            else:
                self.assertEqual(environment['users'], 1)
                self.assertEqual(environment['launched_instances'], 1)
                self.assertEqual(environment['running_instances'], 1)

        self.assertEqual(response.json['overall_running_instances'], 4)

    def test_user_fetch_instance_usage_stats(self):
        response = self.make_authenticated_user_request(
            method='GET',
            path='/api/v1/stats')
        self.assertStatus(response, 403)

    def test_headers(self):
        """Test that we set headers for content caching and security"""
        response = self.make_request(path='/api/v1/config')

        required_headers = ('Cache-Control', 'Expires', 'Strict-Transport-Security', 'Content-Security-Policy')
        for h in required_headers:
            self.assertIn(h, response.headers.keys())

    def test_anonymous_get_environment_categories(self):
        response = self.make_request(
            path='/api/v1/environment_categories'
        )
        self.assert_401(response)

    def test_user_environment_categories(self):
        response = self.make_authenticated_user_request(
            path='/api/v1/environment_categories'
        )
        self.assert_200(response)
        self.assertGreater(len(response.json), 0)


if __name__ == '__main__':
    unittest.main()
