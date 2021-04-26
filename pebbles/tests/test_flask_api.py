import base64
import datetime
import json
import time
import unittest
import uuid

from dateutil.relativedelta import relativedelta

from pebbles.models import (
    User, Workspace, WorkspaceUserAssociation, EnvironmentTemplate, Environment,
    Instance)
from pebbles.tests.base import db, BaseTestCase
from pebbles.tests.fixtures import primary_test_setup

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
            data=json.dumps({'environment': self.known_environment_id_empty}),
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
            data=json.dumps({'environment': self.known_environment_id_empty}),
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

    def test_get_user_workspace_associations(self):
        # Anonymous
        response = self.make_request(
            path='/api/v1/users/%s/workspace_associations' % self.known_user_id
        )
        self.assert_401(response)

        # Authenticated but different user
        response = self.make_authenticated_user_request(
            path='/api/v1/users/%s/workspace_associations' % self.known_workspace_owner_id
        )
        self.assert_403(response)

        # Authenticated
        response = self.make_authenticated_user_request(
            path='/api/v1/users/%s/workspace_associations' % self.known_user_id
        )
        self.assert_200(response)
        # one membership, one ban
        self.assertEqual(len(response.json), 2)

        # Owner should not be able to query user
        response = self.make_authenticated_workspace_owner_request(
            path='/api/v1/users/%s/workspace_associations' % self.known_user_id
        )
        self.assert_403(response)

        # Admin
        response = self.make_authenticated_admin_request(
            path='/api/v1/users/%s/workspace_associations' % self.known_user_id
        )
        self.assert_200(response)

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
        # also check expiry time
        self.assertEqual(
            int(response.json['expiry_ts']),
            int((datetime.datetime.fromtimestamp(response.json['create_ts']) + relativedelta(months=+6)).timestamp())
        )

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
        gu3_obj = WorkspaceUserAssociation(user=u3, workspace=g, is_manager=True, is_owner=True)
        g.user_associations.append(gu1_obj)
        g.user_associations.append(gu2_obj)
        g.user_associations.append(gu3_obj)
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

    def test_archive_workspace(self):
        # Anonymous
        response = self.make_request(
            method='PATCH',
            data=dict(status=Workspace.STATUS_ARCHIVED),
            path='/api/v1/workspaces/%s' % self.known_workspace_id
        )
        self.assert_401(response)
        # Authenticated
        response = self.make_authenticated_user_request(
            method='PATCH',
            data=json.dumps(dict(status=Workspace.STATUS_ARCHIVED)),
            path='/api/v1/workspaces/%s' % self.known_workspace_id
        )
        self.assert_403(response)
        # Owner should be able to archive
        response = self.make_authenticated_workspace_owner_request(
            method='PATCH',
            data=json.dumps(dict(status=Workspace.STATUS_ARCHIVED)),
            path='/api/v1/workspaces/%s' % self.known_workspace_id
        )
        self.assert_200(response)
        workspace = Workspace.query.filter_by(id=self.known_workspace_id).first()
        self.assertEqual(Workspace.STATUS_ARCHIVED, workspace.status)

        # Even admin cannot archive System.default
        invalid_response = self.make_authenticated_admin_request(
            method='PATCH',
            data=json.dumps(dict(status=Workspace.STATUS_ARCHIVED)),
            path='/api/v1/workspaces/%s' % self.system_default_workspace_id
        )
        self.assertStatus(invalid_response, 422)  # Cannot archive default system workspace
        # Admin
        response = self.make_authenticated_admin_request(
            method='PATCH',
            data=json.dumps(dict(status=Workspace.STATUS_ARCHIVED)),
            path='/api/v1/workspaces/%s' % self.known_workspace_id_2
        )
        self.assert_200(response)
        workspace = Workspace.query.filter_by(id=self.known_workspace_id_2).first()
        self.assertEqual(Workspace.STATUS_ARCHIVED, workspace.status)

    def test_delete_workspace(self):
        owner_1 = User.query.filter_by(id=self.known_workspace_owner_id).first()
        name = 'WorkspaceToBeDeleted'
        ws = Workspace(name)
        ws.owner_id = owner_1.id
        ws.user_associations.append(WorkspaceUserAssociation(user=owner_1, is_manager=True, is_owner=True))
        db.session.add(ws)
        db.session.commit()

        # Anonymous
        response = self.make_request(
            method='DELETE',
            path='/api/v1/workspaces/%s' % ws.id
        )
        self.assert_401(response)

        # Authenticated
        response = self.make_authenticated_user_request(
            method='DELETE',
            path='/api/v1/workspaces/%s' % ws.id
        )
        self.assert_403(response)

        # Owner, but not the owner of the workspace
        response = self.make_authenticated_workspace_owner_request(
            method='DELETE',
            path='/api/v1/workspaces/%s' % self.known_workspace_id_3
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
            path='/api/v1/workspaces/%s' % ws.id
        )
        self.assert_200(response)
        workspace = Workspace.query.filter_by(id=ws.id).first()
        self.assertEqual(Workspace.STATUS_DELETED, workspace.status)

        # owner of the workspace with instances, check that instances are set to be deleted as well
        response = self.make_authenticated_workspace_owner_request(
            method='DELETE',
            path='/api/v1/workspaces/%s' % self.known_workspace_id
        )
        self.assert_200(response)
        for environment in Workspace.query.filter_by(id=self.known_workspace_id).first().environments:
            for instance in environment.instances:
                self.assertEqual(True, instance.to_be_deleted)

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

        g.user_associations.append(gu_obj)
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

        g.user_associations.append(gu_obj)
        g.user_associations.append(gu_extra_obj)

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
        gu_obj = WorkspaceUserAssociation(workspace=g, user=u, is_manager=True, is_owner=True)
        g.user_associations.append(gu_obj)
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
        # 1 normal user + 1 manager + 1 workspace owner
        self.assertTrue(response.json['owner']['id'] == self.known_workspace_owner_id)
        self.assertEqual(len(response.json['manager_users']), 2)
        self.assertEqual(len(response.json['normal_users']), 1)
        self.assertEqual(len(response.json['banned_users']), 0)

        # Authenticated Workspace Owner , is a Manager too
        response = self.make_authenticated_admin_request(
            method='GET',
            path='/api/v1/workspaces/%s/list_users' % self.known_workspace_id,
            data=json.dumps({})
        )
        self.assertStatus(response, 200)
        # 1 normal user + 1 manager + 1 workspace owner
        self.assertTrue(response.json['owner']['id'] == self.known_workspace_owner_id)
        self.assertEqual(len(response.json['manager_users']), 2)
        self.assertEqual(len(response.json['normal_users']), 1)
        self.assertEqual(len(response.json['banned_users']), 0)

    def test_clear_users_from_workspace(self):
        name = 'WorkspaceToBeCleared'
        g = Workspace(name)
        u1 = User.query.filter_by(id=self.known_user_id).first()
        gu1_obj = WorkspaceUserAssociation(user=u1, workspace=g)
        u2 = User.query.filter_by(id=self.known_workspace_owner_id_2).first()
        gu2_obj = WorkspaceUserAssociation(user=u2, workspace=g, is_manager=True, is_owner=False)
        u3 = User.query.filter_by(id=self.known_workspace_owner_id).first()
        gu3_obj = WorkspaceUserAssociation(user=u3, workspace=g, is_manager=True, is_owner=True)
        g.user_associations.append(gu1_obj)
        g.user_associations.append(gu2_obj)
        g.user_associations.append(gu3_obj)
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
        response = self.make_request(path='/api/v1/environment_templates/%s' % self.known_template_id)
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
        data = {'name': 'test_environment_template_1', 'base_config': '', 'cluster': 'dummy'}
        response = self.make_request(
            method='POST',
            path='/api/v1/environment_templates',
            data=json.dumps(data))
        self.assert_401(response)
        # Authenticated User
        data = {'name': 'test_environment_template_1', 'base_config': '', 'cluster': 'dummy'}
        response = self.make_authenticated_user_request(
            method='POST',
            path='/api/v1/environment_templates',
            data=json.dumps(data))
        self.assert_403(response)
        # Authenticated Workspace Owner
        data = {'name': 'test_environment_template_1', 'base_config': '', 'cluster': 'dummy'}
        response = self.make_authenticated_workspace_owner_request(
            method='POST',
            path='/api/v1/environment_templates',
            data=json.dumps(data))
        self.assert_403(response)
        # Admin
        data = {'name': 'test_environment_template_1', 'base_config': {'foo': 'bar'}, 'cluster': 'dummy'}
        response = self.make_authenticated_admin_request(
            method='POST',
            path='/api/v1/environment_templates',
            data=json.dumps(data))
        self.assert_200(response)
        # Admin
        data = {
            'name': 'test_environment_template_2',
            'base_config': {'foo': 'bar', 'maximum_lifetime': '1h'},
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
        t.base_config = {'memory_limit': '512m', 'maximum_lifetime': '1h'}
        t.allowed_attrs = ['maximum_lifetime']
        t.is_enabled = True
        db.session.add(t)
        db.session.commit()

        # Anonymous
        data = {'name': 'test_environment_template_1', 'base_config': '', 'cluster': 'dummy'}
        response = self.make_request(
            method='PUT',
            path='/api/v1/environment_templates/%s' % t.id,
            data=json.dumps(data))
        self.assert_401(response)
        # Authenticated User
        data = {'name': 'test_environment_template_1', 'base_config': '', 'cluster': 'dummy'}
        response = self.make_authenticated_user_request(
            method='PUT',
            path='/api/v1/environment_templates/%s' % t.id,
            data=json.dumps(data))
        self.assert_403(response)
        # Authenticated Workspace Owner
        data = {'name': 'test_environment_template_1', 'base_config': '', 'cluster': 'dummy'}
        response = self.make_authenticated_workspace_owner_request(
            method='PUT',
            path='/api/v1/environment_templates/%s' % t.id,
            data=json.dumps(data))
        self.assert_403(response)
        # Admin
        data = {'name': 'test_environment_template_1', 'base_config': {'foo': 'bar'}, 'cluster': 'dummy'}
        response = self.make_authenticated_admin_request(
            method='PUT',
            path='/api/v1/environment_templates/%s' % t.id,
            data=json.dumps(data))
        self.assert_200(response)
        # Admin
        data = {
            'name': 'test_environment_template_2',
            'base_config': {'foo': 'bar', 'maximum_lifetime': '1h'},
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
        self.assertEqual(len(response.json), 3)
        # Authenticated Workspace Owner for Workspace 1 and Normal User for Workspace 2
        response = self.make_authenticated_workspace_owner_request(path='/api/v1/environments')
        self.assert_200(response)
        self.assertEqual(len(response.json), 5)
        # Admin
        response = self.make_authenticated_admin_request(path='/api/v1/environments')
        self.assert_200(response)
        self.assertEqual(len(response.json), 6)
        response = self.make_authenticated_admin_request(path='/api/v1/environments?show_all=true')
        self.assert_200(response)
        self.assertEqual(len(response.json), 8)

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

    def test_get_environment_archived(self):
        # Anonymous
        response = self.make_request(path='/api/v1/environments/%s?show_all=1' % self.known_environment_id_archived)
        self.assert_401(response)
        # Authenticated, user not in workspace
        response = self.make_authenticated_user_request(
            path='/api/v1/environments/%s?show_all=1' % self.known_environment_id_archived)
        self.assert_404(response)
        # Authenticated, user is workspace owner
        response = self.make_authenticated_workspace_owner2_request(
            path='/api/v1/environments/%s?show_all=1' % self.known_environment_id_archived)
        self.assert_404(response)
        # Admin
        response = self.make_authenticated_admin_request(
            path='/api/v1/environments/%s?show_all=1' % self.known_environment_id_archived)
        self.assert_200(response)
        # Admin without show_all
        response = self.make_authenticated_admin_request(
            path='/api/v1/environments/%s' % self.known_environment_id_archived)
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
        data = {'name': 'test_environment_1', 'maximum_lifetime': 3600, 'config': {'foo': 'bar'}, 'template_id': self.known_template_id, 'workspace_id': self.known_workspace_id}
        data_2 = {'name': 'test_environment_2', 'maximum_lifetime': 3600, 'config': {'foo': 'bar'}, 'template_id': self.known_template_id, 'workspace_id': self.known_workspace_id}
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
        data = {'name': 'test_environment_1', 'maximum_lifetime': 3600, 'config': {'foo': 'bar'}, 'template_id': self.known_template_id, 'workspace_id': self.known_workspace_id}
        response = self.make_authenticated_admin_request(
            method='POST',
            path='/api/v1/environments',
            data=json.dumps(data))
        self.assert_200(response)

    def test_delete_environment(self):
        # Anonymous
        response = self.make_request(
            method='DELETE',
            path='/api/v1/environments/%s' % self.known_environment_id
        )
        self.assert_401(response)

        # Authenticated
        response = self.make_authenticated_user_request(
            method='DELETE',
            path='/api/v1/environments/%s' % self.known_environment_id
        )
        self.assert_403(response)

        # Workspace Owner 1, an environment in some other workspace
        response = self.make_authenticated_workspace_owner_request(
            method='DELETE',
            path='/api/v1/environments/%s' % self.known_environment_id_g2
        )
        self.assert_403(response)

        # Workspace Owner 1
        response = self.make_authenticated_workspace_owner_request(
            method='DELETE',
            path='/api/v1/environments/%s' % self.known_environment_id
        )
        self.assert_200(response)

        # Workspace Owner 2 (extra owner added to workspace 1)
        response = self.make_authenticated_workspace_owner2_request(
            method='DELETE',
            path='/api/v1/environments/%s' % self.known_environment_id_2
        )
        self.assert_200(response)

        # Admin
        response = self.make_authenticated_admin_request(
            method='DELETE',
            path='/api/v1/environments/%s' % self.known_environment_id_g2
        )
        self.assert_200(response)

    def test_create_environment_full_config(self):
        # Workspace Owner
        data = {
            'name': 'test_environment_2',
            'maximum_lifetime': 3600,
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

    def test_modify_environment_activate(self):
        data = {
            'name': 'test_environment_activate',
            'maximum_lifetime': 3600,
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
        invalid_workspace_data = {'name': 'test_environment_2', 'maximum_lifetime': 3600, 'config': {"name": "foo"}, 'template_id': self.known_template_id, 'workspace_id': self.known_workspace_id_2}
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
        data = {'environment': self.known_environment_id_empty}
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
        self.assert_403(response)

    def test_owner_create_instance_environment_disabled(self):
        # Use Environment in ws2 that is owned by owner2 and has owner1 as user

        # first, disable known_environment_id_g2
        resp = self.make_authenticated_workspace_owner2_request(
            path='/api/v1/environments/%s' % self.known_environment_id_g2
        )
        data = resp.json
        data['is_enabled'] = False
        put_response = self.make_authenticated_workspace_owner2_request(
            method='PUT',
            path='/api/v1/environments/%s' % self.known_environment_id_g2,
            data=json.dumps(data))
        self.assert_200(put_response)

        # 'owner2' should be able to launch an instance
        response = self.make_authenticated_workspace_owner2_request(
            method='POST',
            path='/api/v1/instances',
            data=json.dumps({'environment': self.known_environment_id_g2}),
        )
        self.assert_200(response)

        # 'owner' has a user role in this ws2, so this should be denied
        response = self.make_authenticated_workspace_owner_request(
            method='POST',
            path='/api/v1/instances',
            data=json.dumps({'environment': self.known_environment_id_g2}),
        )
        self.assert_403(response)

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
        self.assertEquals(len(response.json), 4)

    def test_admin_export_environments(self):

        response = self.make_authenticated_admin_request(path='/api/v1/import_export/environments')
        self.assertStatus(response, 200)
        self.assertEquals(len(response.json), 8)  # There were total 8 environments initialized during setup

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
            path='/api/v1/messages?show_unread=1'
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
            path='/api/v1/messages?show_unread=1'
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
