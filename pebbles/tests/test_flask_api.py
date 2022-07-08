import base64
import datetime
import json
import time
import unittest
import uuid

from dateutil.relativedelta import relativedelta

from pebbles.models import (
    User, Workspace, WorkspaceUserAssociation, ApplicationTemplate, Application,
    ApplicationSession, ApplicationSessionLog)
from pebbles.tests.base import db, BaseTestCase
from pebbles.tests.fixtures import primary_test_setup

ADMIN_TOKEN = None
USER_TOKEN = None
USER_2_TOKEN = None
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
            ADMIN_TOKEN = self.get_auth_token({'ext_id': 'admin@example.org', 'password': 'admin', 'agreement_sign': 'signed'})

        self.admin_token = ADMIN_TOKEN

        return self.make_authenticated_request(method, path, headers, data,
                                               auth_token=self.admin_token)

    def make_authenticated_user_request(self, method='GET', path='/', headers=None, data=None):
        global USER_TOKEN
        if not USER_TOKEN:
            USER_TOKEN = self.get_auth_token(creds={
                'ext_id': self.known_user_ext_id,
                'password': self.known_user_password,
                'agreement_sign': 'signed'}
            )
        self.user_token = USER_TOKEN
        return self.make_authenticated_request(method, path, headers, data,
                                               auth_token=self.user_token)

    def make_authenticated_user_2_request(self, method='GET', path='/', headers=None, data=None):
        global USER_2_TOKEN
        if not USER_2_TOKEN:
            USER_2_TOKEN = self.get_auth_token(creds={
                'ext_id': self.known_user_2_ext_id,
                'password': self.known_user_2_password,
                'agreement_sign': 'signed'}
            )
        self.user_token = USER_2_TOKEN
        return self.make_authenticated_request(method, path, headers, data,
                                               auth_token=self.user_token)

    def make_authenticated_workspace_owner_request(self, method='GET', path='/', headers=None, data=None):
        global COURSE_OWNER_TOKEN
        if not COURSE_OWNER_TOKEN:
            COURSE_OWNER_TOKEN = self.get_auth_token(creds={'ext_id': 'workspace_owner@example.org', 'password': 'workspace_owner', 'agreement_sign': 'signed'})
        self.workspace_owner_token = COURSE_OWNER_TOKEN
        return self.make_authenticated_request(method, path, headers, data,
                                               auth_token=self.workspace_owner_token)

    def make_authenticated_workspace_owner2_request(self, method='GET', path='/', headers=None, data=None):
        global COURSE_OWNER_TOKEN2
        if not COURSE_OWNER_TOKEN2:
            COURSE_OWNER_TOKEN2 = self.get_auth_token(creds={'ext_id': 'workspace_owner2@example.org', 'password': 'workspace_owner2', 'agreement_sign': 'signed'})
        self.workspace_owner_token2 = COURSE_OWNER_TOKEN2
        return self.make_authenticated_request(method, path, headers, data,
                                               auth_token=self.workspace_owner_token2)

    def assert_202(self, response):
        self.assert_status(response, 202)

    def test_deleted_user_cannot_get_token(self):
        response = self.make_request(
            method='POST',
            path='/api/v1/sessions',
            data=json.dumps({'ext_id': 'user@example.org', 'password': 'user', 'email_id': None, 'agreement_sign': 'signed'}))
        self.assert_200(response)
        response = self.make_authenticated_admin_request(
            method='DELETE',
            path='/api/v1/users/%s' % self.known_user_id
        )
        self.assert_200(response)
        response = self.make_request(
            method='POST',
            path='/api/v1/sessions',
            data=json.dumps({'ext_id': 'user@example.org', 'password': 'user', 'email_id': None, 'agreement_sign': 'signed'}))
        self.assert_401(response)

    def test_deleted_user_cannot_use_token(self):
        response = self.make_request(
            method='POST',
            path='/api/v1/sessions',
            data=json.dumps({'ext_id': 'user-2@example.org', 'password': 'user-2', 'agreement_sign': 'signed'})
        )
        self.assert_200(response)

        token = '%s:' % response.json['token']
        token_b64 = base64.b64encode(bytes(token.encode('ascii'))).decode('utf-8')

        headers = {
            'Accept': 'application/json',
            'Authorization': 'Basic %s' % token_b64,
            'token': token_b64
        }
        # Test application session creation works for the user before the test
        response = self.make_request(
            method='POST',
            path='/api/v1/application_sessions',
            data=json.dumps({'application_id': self.known_application_public}),
            headers=headers)
        self.assert_200(response)

        # Delete user-2 'u6' with admin credentials
        response = self.make_authenticated_admin_request(
            method='DELETE',
            path='/api/v1/users/%s' % 'u6'
        )
        self.assert_200(response)

        # Test application session creation fails for the user after the deletion
        response = self.make_request(
            method='POST',
            path='/api/v1/application_sessions',
            data=json.dumps({'application_id': self.known_application_public}),
            headers=headers)
        self.assert_401(response)

    def test_delete_user(self):
        ext_id = "test@example.org"
        u = User(ext_id, "testuser", is_admin=False)
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
        self.assertTrue(user.ext_id != ext_id)

    def test_block_user(self):
        ext_id = "test@example.org"
        u = User(ext_id, "testuser", is_admin=False)
        db.session.add(u)
        db.session.commit()
        # Anonymous
        response = self.make_request(
            method='PATCH',
            path='/api/v1/users/%s' % u.id,
            data=json.dumps({'is_blocked': True})
        )
        self.assert_401(response)
        # Authenticated
        response = self.make_authenticated_user_request(
            method='PATCH',
            path='/api/v1/users/%s' % u.id,
            data=json.dumps({'is_blocked': True})
        )
        self.assert_403(response)
        response = self.make_authenticated_user_request(
            method='PATCH',
            path='/api/v1/users/%s' % u.id,
            data=json.dumps({'is_blocked': True})
        )
        self.assert_403(response)
        # Admin
        # Block
        response = self.make_authenticated_admin_request(
            method='PATCH',
            path='/api/v1/users/%s' % u.id,
            data=json.dumps({'is_blocked': True})
        )
        self.assert_200(response)
        user = User.query.filter_by(id=u.id).first()
        self.assertTrue(user.is_blocked)
        # Unblock
        response = self.make_authenticated_admin_request(
            method='PATCH',
            path='/api/v1/users/%s' % u.id,
            data=json.dumps({'is_blocked': False})
        )
        self.assert_200(response)
        user = User.query.filter_by(id=u.id).first()
        self.assertFalse(user.is_blocked)

    def test_get_user(self):
        # Anonymous
        response = self.make_request(path='/api/v1/users/%s' % self.known_user_id)
        self.assert_401(response)

        # Authenticated, get user data for self
        response = self.make_authenticated_user_request(path='/api/v1/users/%s' % self.known_user_id)
        self.assert_200(response)
        self.assertEqual(self.known_user_ext_id, response.json['ext_id'])

        # Authenticated, get user data for another user
        response = self.make_authenticated_user_request(path='/api/v1/users/%s' % self.known_workspace_owner_id)
        self.assert_403(response)

        # Workspace owner, get user data for another user in workspace
        response = self.make_authenticated_workspace_owner_request(path='/api/v1/users/%s' % self.known_user_id)
        self.assert_403(response)

        # Admin
        response = self.make_authenticated_admin_request(path='/api/v1/users/%s' % self.known_user_id)
        self.assert_200(response)
        self.assertEqual(self.known_user_ext_id, response.json['ext_id'])

        # Admin, deleted user
        response = self.make_authenticated_admin_request(path='/api/v1/users/%s' % self.known_deleted_user_id)
        self.assert_404(response)

        # Admin, non-existent id
        response = self.make_authenticated_admin_request(path='/api/v1/users/%s' % 'no-such-id')
        self.assert_404(response)

    def test_get_users(self):
        # Anonymous
        response = self.make_request(path='/api/v1/users')
        self.assert_401(response)
        # Authenticated
        response = self.make_authenticated_user_request(path='/api/v1/users')
        self.assert_403(response)
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
        # System.default, one WS membership, one ban
        self.assertEqual(3, len(response.json))

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
        self.assertEqual(6, len(response.json))
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
            method='PATCH',
            path='/api/v1/users/%s' % self.known_workspace_owner_id,
            data=json.dumps(dict(workspace_quota=4))
        )
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

        invalid_response = self.make_authenticated_admin_request(
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
        invalid_data_system = {
            'name': 'System.TestWorkspaceModify',
            'description': 'Cannot rename to System.*',
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

        # should not be able to rename to System.*, even as an admin
        invalid_response = self.make_authenticated_workspace_owner_request(
            method='PUT',
            path='/api/v1/workspaces/%s' % self.known_workspace_id,
            data=json.dumps(invalid_data_system))
        self.assertStatus(invalid_response, 422)
        invalid_response = self.make_authenticated_admin_request(
            method='PUT',
            path='/api/v1/workspaces/%s' % self.known_workspace_id,
            data=json.dumps(invalid_data_system))
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

        # owner of the workspace with application sessions, check that application sessions are set to be deleted as well
        response = self.make_authenticated_workspace_owner_request(
            method='DELETE',
            path='/api/v1/workspaces/%s' % self.known_workspace_id
        )
        self.assert_200(response)
        for application in Workspace.query.filter_by(id=self.known_workspace_id).first().applications:
            for application_session in application.application_sessions:
                self.assertEqual(True, application_session.to_be_deleted)

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

    def test_get_workspace_members(self):
        # Anonymous
        response = self.make_request(
            method='GET',
            path='/api/v1/workspaces/%s/members' % self.known_workspace_id
        )
        self.assert_401(response)

        # Authenticated User, not a manager
        response = self.make_authenticated_user_request(
            method='GET',
            path='/api/v1/workspaces/%s/members' % self.known_workspace_id)
        self.assertStatus(response, 403)

        response = self.make_authenticated_user_request(
            method='GET',
            path='/api/v1/workspaces/%s/members?member_count=true' % self.known_workspace_id)
        self.assertStatus(response, 403)

        # Authenticated Workspace Owner , who does not own the workspace
        response = self.make_authenticated_workspace_owner_request(
            method='GET',
            path='/api/v1/workspaces/%s/members' % self.known_workspace_id_2,
            data=json.dumps({})
        )
        self.assertStatus(response, 403)

        response = self.make_authenticated_workspace_owner_request(
            method='GET',
            path='/api/v1/workspaces/%s/members?member_count=true' % self.known_workspace_id_2,
            data=json.dumps({})
        )
        self.assertStatus(response, 403)

        # Authenticated Workspace Owner (owners are managers, too)
        response = self.make_authenticated_workspace_owner_request(
            method='GET',
            path='/api/v1/workspaces/%s/members' % self.known_workspace_id,
            data=json.dumps({})
        )
        self.assertStatus(response, 200)
        # 1 normal user + 1 manager + 1 workspace owner
        self.assertEqual(
            len([member for member in response.json
                 if member['user_id'] == self.known_workspace_owner_id and member['is_owner']]
                ),
            1)
        self.assertEqual(len([member for member in response.json if member['is_manager']]), 2)
        self.assertEqual(len([member for member in response.json if not (member['is_manager'] or member['is_owner'])]), 2)
        self.assertEqual(len([member for member in response.json if member['is_banned']]), 0)

        response = self.make_authenticated_workspace_owner_request(
            method='GET',
            path='/api/v1/workspaces/%s/members?member_count=true' % self.known_workspace_id)
        self.assertEqual(response.json, 4)

        # Admins
        response = self.make_authenticated_admin_request(
            method='GET',
            path='/api/v1/workspaces/%s/members' % self.known_workspace_id,
            data=json.dumps({})
        )
        self.assertStatus(response, 200)

        # 2 normal users + 1 manager + 1 workspace owner
        self.assertEqual(
            len([member for member in response.json
                 if member['user_id'] == self.known_workspace_owner_id and member['is_owner']]
                ),
            1)
        self.assertEqual(len([member for member in response.json if member['is_manager']]), 2)
        self.assertEqual(len([member for member in response.json if not (member['is_manager'] or member['is_owner'])]), 2)
        self.assertEqual(len([member for member in response.json if member['is_banned']]), 0)

        response = self.make_authenticated_admin_request(
            method='GET',
            path='/api/v1/workspaces/%s/members?member_count=true' % self.known_workspace_id)
        self.assertEqual(response.json, 4)

    def test_promote_and_demote_workspace_members(self):
        # Anonymous
        response = self.make_request(
            method='PATCH',
            data=json.dumps(dict(user_id=self.known_user_id, operation='promote')),
            path='/api/v1/workspaces/%s/members' % self.known_workspace_id
        )
        self.assert_401(response)

        # Authenticated
        response = self.make_authenticated_user_request(
            method='PATCH',
            data=json.dumps(dict(user_id=self.known_user_id, operation='promote')),
            path='/api/v1/workspaces/%s/members' % self.known_workspace_id
        )
        self.assert_403(response)

        # Manager should be able to promote and demote
        response = self.make_authenticated_workspace_owner2_request(
            method='PATCH',
            data=json.dumps(dict(user_id=self.known_user_id, operation='promote')),
            path='/api/v1/workspaces/%s/members' % self.known_workspace_id
        )
        self.assert_200(response)
        response = self.make_authenticated_workspace_owner2_request(
            method='PATCH',
            data=json.dumps(dict(user_id=self.known_user_id, operation='demote')),
            path='/api/v1/workspaces/%s/members' % self.known_workspace_id
        )
        self.assert_200(response)

        # Manager should not be able to demote owner
        response = self.make_authenticated_workspace_owner2_request(
            method='PATCH',
            data=json.dumps(dict(user_id=self.known_workspace_owner_id, operation='demote')),
            path='/api/v1/workspaces/%s/members' % self.known_workspace_id
        )
        self.assert_403(response)

    def test_transfer_ownership_workspace(self):

        g = Workspace('TestWorkspaceTransferOwnership')
        g.id = 'TestWorkspaceId'
        g.cluster = 'dummy_cluster_1'

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

        # Anonymous
        response = self.make_request(
            method='PATCH',
            data=json.dumps(dict(new_owner_id=self.known_user_id)),
            path='/api/v1/workspaces/%s/transfer_ownership' % g.id
        )
        self.assert_401(response)

        # Authenticated user request
        response = self.make_authenticated_user_request(
            method='PATCH',
            data=json.dumps(dict(new_owner_id=u1.id)),
            path='/api/v1/workspaces/%s/transfer_ownership' % g.id
        )
        self.assert_403(response)

        # new_owner_to_be is a member of workspace but not owner
        response = self.make_authenticated_workspace_owner_request(
            method='PATCH',
            data=json.dumps(dict(new_owner_id=u1.id)),
            path='/api/v1/workspaces/%s/transfer_ownership' % g.id
        )
        self.assert_403(response)

        # new_owner_to_be not a member of workspace
        response = self.make_authenticated_workspace_owner_request(
            method='PATCH',
            data=json.dumps(dict(new_owner_id=self.known_user_2_ext_id)),
            path='/api/v1/workspaces/%s/transfer_ownership' % g.id
        )
        self.assert_403(response)

        # new_owner_to_be member of workspace and owner
        response = self.make_authenticated_workspace_owner_request(
            method='PATCH',
            data=json.dumps(dict(new_owner_id=u2.id)),
            path='/api/v1/workspaces/%s/transfer_ownership' % g.id
        )
        self.assert_200(response)

        # old owner tries to add new_owner again
        response = self.make_authenticated_workspace_owner_request(
            method='PATCH',
            data=json.dumps(dict(new_owner_id=u2.id)),
            path='/api/v1/workspaces/%s/transfer_ownership' % g.id
        )
        self.assert_403(response)

    def test_clear_members_from_workspace(self):
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
            path='/api/v1/workspaces/%s/clear_members' % g.id,
            data=json.dumps({})
        )
        self.assert_401(response)
        # Authenticated user
        response = self.make_authenticated_user_request(
            method='POST',
            path='/api/v1/workspaces/%s/clear_members' % g.id,
            data=json.dumps({})
        )
        self.assert_403(response)
        # Authenticated workspace owner
        response = self.make_authenticated_workspace_owner_request(
            method='POST',
            path='/api/v1/workspaces/%s/clear_members' % g.id,
            data=json.dumps({})
        )
        self.assert_200(response)
        # Authenticated workspace owner, invalid workspace id
        invalid_response = self.make_authenticated_workspace_owner_request(
            method='POST',
            path='/api/v1/workspaces/%s/clear_members' % '',
            data=json.dumps({})
        )
        self.assertStatus(invalid_response, 405)
        # Authenticated workspace manager
        response = self.make_authenticated_workspace_owner2_request(
            method='POST',
            path='/api/v1/workspaces/%s/clear_members' % g.id,
            data=json.dumps({})
        )
        self.assert_403(response)
        # Admin, system.default workspace
        invalid_response = self.make_authenticated_admin_request(
            method='POST',
            path='/api/v1/workspaces/%s/clear_members' % self.system_default_workspace_id,
            data=json.dumps({})
        )
        self.assertStatus(invalid_response, 422)
        # Admin
        response = self.make_authenticated_admin_request(
            method='POST',
            path='/api/v1/workspaces/%s/clear_members' % g.id,
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

    def test_get_application_templates(self):
        # Anonymous
        response = self.make_request(path='/api/v1/application_templates')
        self.assert_401(response)
        # Authenticated User
        response = self.make_authenticated_user_request(path='/api/v1/application_templates')
        self.assert_403(response)
        # Authenticated Workspace Owner
        response = self.make_authenticated_workspace_owner_request(path='/api/v1/application_templates')
        self.assert_200(response)
        self.assertEqual(len(response.json), 1)
        # Admin
        response = self.make_authenticated_admin_request(path='/api/v1/application_templates')
        self.assert_200(response)
        self.assertEqual(len(response.json), 2)

    def test_get_application_template(self):
        # Existing application
        # Anonymous
        response = self.make_request(path='/api/v1/application_templates/%s' % self.known_template_id)
        self.assert_401(response)
        # Authenticated User
        response = self.make_authenticated_user_request(path='/api/v1/application_templates/%s' % self.known_template_id)
        self.assert_403(response)
        # Workspace Owner
        response = self.make_authenticated_workspace_owner_request(path='/api/v1/application_templates/%s' % self.known_template_id)
        self.assert_200(response)
        # Admin
        response = self.make_authenticated_admin_request(path='/api/v1/application_templates/%s' % self.known_template_id)
        self.assert_200(response)

        # non-existing application
        # Anonymous
        response = self.make_request(path='/api/v1/application_templates/%s' % uuid.uuid4().hex)
        self.assert_401(response)
        # Authenticated User
        response = self.make_authenticated_user_request(path='/api/v1/application_templates/%s' % uuid.uuid4().hex)
        self.assert_403(response)
        # Workspace Owner
        response = self.make_authenticated_workspace_owner_request(path='/api/v1/application_templates/%s' % uuid.uuid4().hex)
        self.assert_404(response)
        # Admin
        response = self.make_authenticated_admin_request(path='/api/v1/application_templates/%s' % uuid.uuid4().hex)
        self.assert_404(response)

    def test_create_application_template(self):
        # Anonymous
        data = {'name': 'test_application_template_1', 'base_config': ''}
        response = self.make_request(
            method='POST',
            path='/api/v1/application_templates',
            data=json.dumps(data))
        self.assert_401(response)
        # Authenticated User
        data = {'name': 'test_application_template_1', 'base_config': ''}
        response = self.make_authenticated_user_request(
            method='POST',
            path='/api/v1/application_templates',
            data=json.dumps(data))
        self.assert_403(response)
        # Authenticated Workspace Owner
        data = {'name': 'test_application_template_1', 'base_config': ''}
        response = self.make_authenticated_workspace_owner_request(
            method='POST',
            path='/api/v1/application_templates',
            data=json.dumps(data))
        self.assert_403(response)
        # Admin
        data = {'name': 'test_application_template_1', 'base_config': {'foo': 'bar'}}
        response = self.make_authenticated_admin_request(
            method='POST',
            path='/api/v1/application_templates',
            data=json.dumps(data))
        self.assert_200(response)
        # Admin
        data = {
            'name': 'test_application_template_2',
            'base_config': {'foo': 'bar', 'maximum_lifetime': '1h'},
            'allowed_attrs': {'allowed_attrs': ['maximum_lifetime']},
        }
        response = self.make_authenticated_admin_request(
            method='POST',
            path='/api/v1/application_templates',
            data=json.dumps(data))
        self.assert_200(response)

    def test_modify_application_template(self):
        t = ApplicationTemplate()
        t.name = 'TestTemplate'
        t.base_config = {'memory_limit': '512m', 'maximum_lifetime': '1h'}
        t.allowed_attrs = ['maximum_lifetime']
        t.is_enabled = True
        db.session.add(t)
        db.session.commit()

        # Anonymous
        data = {'name': 'test_application_template_1', 'base_config': ''}
        response = self.make_request(
            method='PUT',
            path='/api/v1/application_templates/%s' % t.id,
            data=json.dumps(data))
        self.assert_401(response)
        # Authenticated User
        data = {'name': 'test_application_template_1', 'base_config': ''}
        response = self.make_authenticated_user_request(
            method='PUT',
            path='/api/v1/application_templates/%s' % t.id,
            data=json.dumps(data))
        self.assert_403(response)
        # Authenticated Workspace Owner
        data = {'name': 'test_application_template_1', 'base_config': ''}
        response = self.make_authenticated_workspace_owner_request(
            method='PUT',
            path='/api/v1/application_templates/%s' % t.id,
            data=json.dumps(data))
        self.assert_403(response)
        # Admin
        data = {'name': 'test_application_template_1', 'base_config': {'foo': 'bar'}}
        response = self.make_authenticated_admin_request(
            method='PUT',
            path='/api/v1/application_templates/%s' % t.id,
            data=json.dumps(data))
        self.assert_200(response)
        # Admin
        data = {
            'name': 'test_application_template_2',
            'base_config': {'foo': 'bar', 'maximum_lifetime': '1h'},
            'allowed_attrs': {'allowed_attrs': ['maximum_lifetime']},
        }
        response = self.make_authenticated_admin_request(
            method='PUT',
            path='/api/v1/application_templates/%s' % t.id,
            data=json.dumps(data))
        self.assert_200(response)

    def test_copy_application_template(self):

        # Authenticated User
        response = self.make_authenticated_user_request(
            method='PUT',
            path='/api/v1/application_templates/template_copy/%s' % self.known_template_id)
        self.assert_403(response)
        # Authenticated Workspace Owner
        response = self.make_authenticated_workspace_owner_request(
            method='PUT',
            path='/api/v1/application_templates/template_copy/%s' % self.known_template_id)
        self.assert_403(response)
        # Admin
        response = self.make_authenticated_admin_request(
            method='PUT',
            path='/api/v1/application_templates/template_copy/%s' % self.known_template_id)
        self.assert_200(response)

    def test_get_applications(self):
        # Anonymous
        response = self.make_request(path='/api/v1/applications')
        self.assert_401(response)
        # Authenticated User for Workspace 1
        response = self.make_authenticated_user_request(path='/api/v1/applications')
        self.assert_200(response)
        self.assertEqual(len(response.json), 4)
        response = self.make_authenticated_user_request(path='/api/v1/applications?workspace_id=%s' % self.known_workspace_id)
        self.assert_200(response)
        self.assertEqual(len(response.json), 3)
        response = self.make_authenticated_user_request(path='/api/v1/applications?workspace_id=%s&applications_count=true' % self.known_workspace_id)
        self.assert_200(response)
        self.assertEqual(response.json, 3)

        # Authenticated Workspace Owner for Workspace 1(with 4 apps) and Normal User for Workspace 2
        response = self.make_authenticated_workspace_owner_request(path='/api/v1/applications')
        self.assert_200(response)
        self.assertEqual(len(response.json), 6)

        response = self.make_authenticated_workspace_owner_request(path='/api/v1/applications?workspace_id=%s' % self.known_workspace_id)
        self.assert_200(response)
        self.assertEqual(len(response.json), 4)
        response = self.make_authenticated_workspace_owner_request(path='/api/v1/applications?workspace_id=%s&applications_count=true' % self.known_workspace_id)
        self.assert_200(response)
        self.assertEqual(response.json, 4)

        # Admin
        response = self.make_authenticated_admin_request(path='/api/v1/applications')
        self.assert_200(response)
        self.assertEqual(len(response.json), 10)
        response = self.make_authenticated_admin_request(path='/api/v1/applications?workspace_id=%s' % self.known_workspace_id)
        self.assert_200(response)
        self.assertEqual(len(response.json), 4)
        response = self.make_authenticated_admin_request(path='/api/v1/applications?workspace_id=%s&applications_count=true' % self.known_workspace_id)
        self.assert_200(response)
        self.assertEqual(response.json, 4)

        response = self.make_authenticated_admin_request(path='/api/v1/applications?show_all=true')
        self.assert_200(response)
        self.assertEqual(len(response.json), 12)

    def test_get_application(self):
        # Existing application
        # Anonymous
        response = self.make_request(path='/api/v1/applications/%s' % self.known_application_id)
        self.assert_401(response)
        # Authenticated
        response = self.make_authenticated_user_request(path='/api/v1/applications/%s' % self.known_application_id)
        self.assert_200(response)
        # Admin
        response = self.make_authenticated_admin_request(path='/api/v1/applications/%s' % self.known_application_id)
        self.assert_200(response)

        # non-existing application
        # Anonymous
        response = self.make_request(path='/api/v1/applications/%s' % uuid.uuid4().hex)
        self.assert_401(response)
        # Authenticated
        response = self.make_authenticated_user_request(path='/api/v1/applications/%s' % uuid.uuid4().hex)
        self.assert_404(response)
        # Admin
        response = self.make_authenticated_admin_request(path='/api/v1/applications/%s' % uuid.uuid4().hex)
        self.assert_404(response)

    def test_get_application_archived(self):
        # Anonymous
        response = self.make_request(path='/api/v1/applications/%s?show_all=1' % self.known_application_id_archived)
        self.assert_401(response)
        # Authenticated, user not in workspace
        response = self.make_authenticated_user_request(
            path='/api/v1/applications/%s?show_all=1' % self.known_application_id_archived)
        self.assert_404(response)
        # Authenticated, user is workspace owner
        response = self.make_authenticated_workspace_owner2_request(
            path='/api/v1/applications/%s?show_all=1' % self.known_application_id_archived)
        self.assert_404(response)
        # Admin
        response = self.make_authenticated_admin_request(
            path='/api/v1/applications/%s?show_all=1' % self.known_application_id_archived)
        self.assert_200(response)
        # Admin without show_all
        response = self.make_authenticated_admin_request(
            path='/api/v1/applications/%s' % self.known_application_id_archived)
        self.assert_404(response)

    def test_get_application_labels(self):
        # Authenticated
        response = self.make_authenticated_user_request(path='/api/v1/applications/%s' % self.known_application_id)
        self.assert_200(response)
        labels = response.json['labels']
        expected_labels = ['label1', 'label with space', 'label2']
        self.assertEqual(labels, expected_labels, 'label array matches')

    def test_create_application(self):
        # Anonymous
        data = {'name': 'test_application_1', 'config': '', 'template_id': self.known_template_id, 'workspace_id': self.known_workspace_id}
        response = self.make_request(
            method='POST',
            path='/api/v1/applications',
            data=json.dumps(data))
        self.assert_401(response)
        # Authenticated
        data = {'name': 'test_application_1', 'config': '', 'template_id': self.known_template_id, 'workspace_id': self.known_workspace_id}
        response = self.make_authenticated_user_request(
            method='POST',
            path='/api/v1/applications',
            data=json.dumps(data))
        self.assert_403(response)
        # Workspace Owner 1
        data = {'name': 'test_application_1', 'maximum_lifetime': 3600, 'config': {'foo': 'bar'}, 'template_id': self.known_template_id, 'workspace_id': self.known_workspace_id}
        data_2 = {'name': 'test_application_2', 'maximum_lifetime': 3600, 'config': {'foo': 'bar'}, 'template_id': self.known_template_id, 'workspace_id': self.known_workspace_id}
        response = self.make_authenticated_workspace_owner_request(
            method='POST',
            path='/api/v1/applications',
            data=json.dumps(data))
        self.assert_200(response)
        # Workspace Owner 2 (extra owner added to workspace 1)
        response = self.make_authenticated_workspace_owner2_request(
            method='POST',
            path='/api/v1/applications',
            data=json.dumps(data))
        self.assert_200(response)
        # check if possible to create more applications than quota in the workspace
        response = self.make_authenticated_workspace_owner2_request(
            method='POST',
            path='/api/v1/applications',
            data=json.dumps(data_2))
        self.assertStatus(response, 422)
        # Admin ignores quota
        data = {'name': 'test_application_1', 'maximum_lifetime': 3600, 'config': {'foo': 'bar'}, 'template_id': self.known_template_id, 'workspace_id': self.known_workspace_id}
        response = self.make_authenticated_admin_request(
            method='POST',
            path='/api/v1/applications',
            data=json.dumps(data))
        self.assert_200(response)

    def test_delete_application(self):
        # Anonymous
        response = self.make_request(
            method='DELETE',
            path='/api/v1/applications/%s' % self.known_application_id
        )
        self.assert_401(response)

        # Authenticated
        response = self.make_authenticated_user_request(
            method='DELETE',
            path='/api/v1/applications/%s' % self.known_application_id
        )
        self.assert_403(response)

        # Workspace Owner 1, an application in some other workspace
        response = self.make_authenticated_workspace_owner_request(
            method='DELETE',
            path='/api/v1/applications/%s' % self.known_application_id_g2
        )
        self.assert_403(response)

        # Workspace Owner 1
        response = self.make_authenticated_workspace_owner_request(
            method='DELETE',
            path='/api/v1/applications/%s' % self.known_application_id
        )
        self.assert_200(response)

        # Workspace Owner 2 (extra owner added to workspace 1)
        response = self.make_authenticated_workspace_owner2_request(
            method='DELETE',
            path='/api/v1/applications/%s' % self.known_application_id_2
        )
        self.assert_200(response)

        # Admin
        response = self.make_authenticated_admin_request(
            method='DELETE',
            path='/api/v1/applications/%s' % self.known_application_id_g2
        )
        self.assert_200(response)

    def test_modify_application_activate(self):
        data = {
            'name': 'test_application_activate',
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
            path='/api/v1/applications/%s' % self.known_application_id_disabled,
            data=json.dumps(data))
        self.assert_403(put_response)
        # Workspace owner not an owner of the application workspace 2
        put_response = self.make_authenticated_workspace_owner_request(
            method='PUT',
            path='/api/v1/applications/%s' % self.known_application_id_disabled_2,
            data=json.dumps(data))
        self.assert_403(put_response)
        # Workspace Owner is an owner of the application workspace 1
        put_response = self.make_authenticated_workspace_owner_request(
            method='PUT',
            path='/api/v1/applications/%s' % self.known_application_id_disabled,
            data=json.dumps(data))
        self.assert_200(put_response)
        # Workspace owner 2 is part of the application workspace 1 as an additional owner
        put_response = self.make_authenticated_workspace_owner2_request(
            method='PUT',
            path='/api/v1/applications/%s' % self.known_application_id_disabled,
            data=json.dumps(data))
        self.assert_200(put_response)
        # Workspace owner 2 owner of the application workspace 2
        put_response = self.make_authenticated_workspace_owner2_request(
            method='PUT',
            path='/api/v1/applications/%s' % self.known_application_id_disabled,
            data=json.dumps(data))
        self.assert_200(put_response)
        # Admin
        put_response = self.make_authenticated_admin_request(
            method='PUT',
            path='/api/v1/applications/%s' % self.known_application_id_disabled,
            data=json.dumps(data))
        self.assert_200(put_response)

        application = Application.query.filter_by(id=self.known_application_id_disabled).first()
        self.assertEqual(application.is_enabled, False)

    def test_create_application_admin_invalid_data(self):
        invalid_form_data = [
            {'name': '', 'config': 'foo: bar', 'template_id': self.known_template_id, 'workspace_id': self.known_workspace_id},
            {'name': 'test_application_2', 'config': '', 'template_id': self.known_template_id, 'workspace_id': self.known_workspace_id},
            {'name': 'test_application_2', 'config': 'foo: bar', 'template_id': self.known_template_id},
            {'name': 'test_application_2', 'config': 'foo: bar', 'workspace_id': self.known_workspace_id},
            {'name': 'test_application_2', 'config': {"name": "foo", "maximum_lifetime": ' '}, 'template_id': self.known_template_id, 'workspace_id': self.known_workspace_id},
            {'name': 'test_application_2', 'config': {"name": "foo", "maximum_lifetime": '10 100'}, 'template_id': self.known_template_id, 'workspace_id': self.known_workspace_id},
            {'name': 'test_application_2', 'config': {"name": "foo", "maximum_lifetime": '1hh'}, 'template_id': self.known_template_id, 'workspace_id': self.known_workspace_id},
            {'name': 'test_application_2', 'config': {"name": "foo", "maximum_lifetime": '-1m'}, 'template_id': self.known_template_id, 'workspace_id': self.known_workspace_id},
            {'name': 'test_application_2', 'config': {"name": "foo", "maximum_lifetime": '-10h'}, 'template_id': self.known_template_id, 'workspace_id': self.known_workspace_id},
            {'name': 'test_application_2', 'config': {"name": "foo", "maximum_lifetime": '2d -10h'}, 'template_id': self.known_template_id, 'workspace_id': self.known_workspace_id},
            {'name': 'test_application_2', 'config': {"name": "foo", "maximum_lifetime": '30s'}, 'template_id': self.known_template_id, 'workspace_id': self.known_workspace_id},
            {'name': 'test_application_2', 'config': {"name": "foo", "maximum_lifetime": '10h'}, 'template_id': self.known_template_id, 'workspace_id': 'unknown'},
            {'name': 'test_application_2', 'config': {"name": "foo", "maximum_lifetime": '10h'}, 'template_id': 'unknown', 'workspace_id': self.known_workspace_id},
        ]
        for data in invalid_form_data:
            response = self.make_authenticated_admin_request(
                method='POST',
                path='/api/v1/applications',
                data=json.dumps(data))
            self.assertStatus(response, 422)

    def test_create_application_template_admin_invalid_data(self):
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
                path='/api/v1/application_templates',
                data=json.dumps(data))
            self.assertStatus(response, 422)

    def test_create_application_workspace_owner_invalid_data(self):
        invalid_form_data = [
            {'name': '', 'config': 'foo: bar', 'template_id': self.known_template_id, 'workspace_id': self.known_workspace_id},
            {'name': 'test_application_2', 'config': '', 'template_id': self.known_template_id, 'workspace_id': self.known_workspace_id},
            {'name': 'test_application_2', 'config': 'foo: bar', 'template_id': self.known_template_id},
            {'name': 'test_application_2', 'config': 'foo: bar', 'workspace_id': self.known_workspace_id},
            {'name': 'test_application_2', 'config': {"name": "foo", "maximum_lifetime": '10h'}, 'template_id': self.known_template_id, 'workspace_id': 'unknown'},
            {'name': 'test_application_2', 'config': {"name": "foo", "maximum_lifetime": '10h'}, 'template_id': 'unknown', 'workspace_id': self.known_workspace_id},
        ]
        for data in invalid_form_data:
            response = self.make_authenticated_workspace_owner_request(
                method='POST',
                path='/api/v1/applications',
                data=json.dumps(data))
            self.assertStatus(response, 422)

        # Workspace owner is a user but not the owner of the workspace with id : known_workspace_id_2
        invalid_workspace_data = {'name': 'test_application_2', 'maximum_lifetime': 3600, 'config': {"name": "foo"}, 'template_id': self.known_template_id, 'workspace_id': self.known_workspace_id_2}
        response = self.make_authenticated_workspace_owner_request(
            method='POST',
            path='/api/v1/applications',
            data=json.dumps(invalid_workspace_data))
        self.assertStatus(response, 403)

        put_response = self.make_authenticated_workspace_owner_request(
            method='PUT',
            path='/api/v1/applications/%s' % self.known_application_id_g2,
            data=json.dumps(invalid_workspace_data))
        self.assertStatus(put_response, 403)

    def test_create_application_workspace_owner_quota(self):
        # Workspace Owner 1

        # delete all existing applications, these should no longer be counted towards quota after that
        ws_apps = self.make_authenticated_workspace_owner_request(
            path='/api/v1/applications?workspace_id=%s' % self.known_workspace_id
        )
        for application in ws_apps.json:
            resp = self.make_authenticated_workspace_owner_request(
                method='DELETE',
                path='/api/v1/applications/%s' % application['id']
            )
            self.assert_200(resp)
        ws_apps = self.make_authenticated_workspace_owner_request(
            path='/api/v1/applications?workspace_id=%s' % self.known_workspace_id
        )
        data = {'name': 'test_application_1', 'maximum_lifetime': 3600, 'config': {'foo': 'bar'}, 'template_id': self.known_template_id, 'workspace_id': self.known_workspace_id}

        # we should be able to create 6
        for i in range(6):
            response = self.make_authenticated_workspace_owner_request(
                method='POST',
                path='/api/v1/applications',
                data=json.dumps(data))
            self.assert_200(response)

        # ...and the 7th should fail
        response = self.make_authenticated_workspace_owner_request(
            method='POST',
            path='/api/v1/applications',
            data=json.dumps(data))
        self.assertStatus(response, 422)

    def test_copy_applications(self):

        # Authenticated User
        response = self.make_authenticated_user_request(
            method='PUT',
            path='/api/v1/applications/application_copy/%s' % self.known_application_id)
        self.assert_403(response)
        # Authenticated Workspace Owner
        response = self.make_authenticated_workspace_owner_request(
            method='PUT',
            path='/api/v1/applications/application_copy/%s' % self.known_application_id)
        self.assert_200(response)
        # Admin
        response = self.make_authenticated_admin_request(
            method='PUT',
            path='/api/v1/applications/application_copy/%s' % self.known_application_id)
        self.assert_200(response)

    def test_anonymous_create_application_session(self):
        data = {'application_id': self.known_application_id}
        response = self.make_request(
            method='POST',
            path='/api/v1/application_sessions',
            data=json.dumps(data))
        self.assert_401(response)

    def test_user_create_application_session(self):
        # User is not a part of the workspace (Workspace2)
        data = {'application_id': self.known_application_id_g2}
        response = self.make_authenticated_user_request(
            method='POST',
            path='/api/v1/application_sessions',
            data=json.dumps(data))
        self.assert_404(response)

        # User is a part of the workspace (Workspace1), but already has 2 non-deleted sessions
        data = {'application_id': self.known_application_id_empty}
        response = self.make_authenticated_user_request(
            method='POST',
            path='/api/v1/application_sessions',
            data=json.dumps(data))
        self.assertStatus(response, 409)

        # User-2 is a part of the workspace (Workspace1), no sessions previously
        data = {'application_id': self.known_application_id_empty}
        response = self.make_authenticated_user_2_request(
            method='POST',
            path='/api/v1/application_sessions',
            data=json.dumps(data))
        self.assert_200(response)

    def test_user_create_application_session_application_disabled(self):
        response = self.make_authenticated_user_request(
            method='POST',
            path='/api/v1/application_sessions',
            data=json.dumps({'application_id': self.known_application_id_disabled}),
        )
        self.assert_404(response)

    def test_user_create_application_session_application_deleted(self):
        response = self.make_authenticated_user_request(
            method='POST',
            path='/api/v1/application_sessions',
            data=json.dumps({'application_id': self.known_application_id_deleted}),
        )
        self.assert_404(response)

    def test_user_create_application_session_application_archived(self):
        response = self.make_authenticated_user_request(
            method='POST',
            path='/api/v1/application_sessions',
            data=json.dumps({'application_id': self.known_application_id_archived}),
        )
        self.assert_404(response)

    def test_create_application_session_memory_limit(self):
        # first launch by user-2 should work
        data = {'application_id': self.known_application_id_mem_limit_test_1}
        response = self.make_authenticated_user_2_request(
            method='POST',
            path='/api/v1/application_sessions',
            data=json.dumps(data))
        self.assert_200(response)

        # next launch by user-2 should fail, because we would be over memory limit
        data = {'application_id': self.known_application_id_mem_limit_test_2}
        response = self.make_authenticated_user_2_request(
            method='POST',
            path='/api/v1/application_sessions',
            data=json.dumps(data))
        self.assertEqual(response.status_code, 409, 'session launch should be rejected')

        # but we should be able to launch a smaller application
        data = {'application_id': self.known_application_id_mem_limit_test_3}
        response = self.make_authenticated_user_2_request(
            method='POST',
            path='/api/v1/application_sessions',
            data=json.dumps(data))
        self.assert_200(response)

        # even admin cannot launch a session
        data = {'application_id': self.known_application_id_mem_limit_test_2}
        response = self.make_authenticated_admin_request(
            method='POST',
            path='/api/v1/application_sessions',
            data=json.dumps(data))
        self.assertEqual(response.status_code, 409, 'session launch should be rejected')

    def test_owner_create_application_session_application_disabled(self):
        # Use Application in ws2 that is owned by owner2 and has owner1 as user

        # first, disable known_application_id_g2
        resp = self.make_authenticated_workspace_owner2_request(
            path='/api/v1/applications/%s' % self.known_application_id_g2
        )
        data = resp.json
        data['is_enabled'] = False
        put_response = self.make_authenticated_workspace_owner2_request(
            method='PUT',
            path='/api/v1/applications/%s' % self.known_application_id_g2,
            data=json.dumps(data))
        self.assert_200(put_response)

        # 'owner2' should be able to launch an application session
        response = self.make_authenticated_workspace_owner2_request(
            method='POST',
            path='/api/v1/application_sessions',
            data=json.dumps({'application_id': self.known_application_id_g2}),
        )
        self.assert_200(response)

        # 'owner' has a user role in this ws2, so this should be denied
        response = self.make_authenticated_workspace_owner_request(
            method='POST',
            path='/api/v1/application_sessions',
            data=json.dumps({'application_id': self.known_application_id_g2}),
        )
        self.assert_404(response)

    def test_get_application_sessions(self):
        # Anonymous
        response = self.make_request(path='/api/v1/application_sessions')
        self.assert_401(response)
        # Authenticated
        response = self.make_authenticated_user_request(path='/api/v1/application_sessions')
        self.assert_200(response)
        self.assertEqual(len(response.json), 2)
        # Workspace Manager (His own session + other sessions from his managed workspaces)
        response = self.make_authenticated_workspace_owner_request(path='/api/v1/application_sessions')
        self.assert_200(response)
        self.assertEqual(len(response.json), 3)
        # Admin
        response = self.make_authenticated_admin_request(path='/api/v1/application_sessions')
        self.assert_200(response)
        self.assertEqual(len(response.json), 4)

    def test_get_application_session(self):
        # Anonymous
        response = self.make_request(path='/api/v1/application_sessions/%s' % self.known_application_session_id)
        self.assert_401(response)

        # Authenticated, someone else's application session
        response = self.make_authenticated_user_request(
            method='GET',
            path='/api/v1/application_sessions/%s' % self.known_application_session_id_4
        )
        self.assert_404(response)

        # Authenticated
        response = self.make_authenticated_user_request(
            method='GET',
            path='/api/v1/application_sessions/%s' % self.known_application_session_id
        )
        self.assert_200(response)

        # Admin
        response = self.make_authenticated_admin_request(
            method='GET',
            path='/api/v1/application_sessions/%s' % self.known_application_session_id
        )
        self.assert_200(response)

    def test_patch_application_session(self):
        # Anonymous
        response = self.make_request(
            method='PATCH',
            path='/api/v1/application_sessions/%s' % self.known_application_session_id,
            data=json.dumps(dict(state='deleting'))
        )
        self.assert_401(response)

        # Authenticated
        response = self.make_authenticated_user_request(
            method='PATCH',
            path='/api/v1/application_sessions/%s' % self.known_application_session_id,
            data=json.dumps(dict(state='deleting'))
        )
        self.assert_403(response)

        # Owner
        response = self.make_authenticated_workspace_owner_request(
            method='PATCH',
            path='/api/v1/application_sessions/%s' % self.known_application_session_id,
            data=json.dumps(dict(state='deleting'))
        )
        self.assert_403(response)

        # Admin, invalid state
        response = self.make_authenticated_admin_request(
            method='PATCH',
            path='/api/v1/application_sessions/%s' % self.known_application_session_id,
            data=json.dumps(dict(state='bogus'))
        )
        self.assertEqual(422, response.status_code)

        # Admin, check that changing state to 'deleted' cleans logs. ApplicationSession 2 with logs.
        self.assertEqual(1, len(ApplicationSessionLog.query.filter_by(application_session_id=self.known_application_session_id_2).all()))
        response = self.make_authenticated_admin_request(
            method='PATCH',
            path='/api/v1/application_sessions/%s' % self.known_application_session_id_2,
            data=json.dumps(dict(state='deleted'))
        )
        self.assert_200(response)
        self.assertEqual(0, len(ApplicationSessionLog.query.filter_by(application_session_id=self.known_application_session_id_2).all()))

    def test_delete_application_session(self):
        application = Application.query.filter_by(id=self.known_application_id).first()
        user = User.query.filter_by(id=self.known_user_id).first()
        i1 = ApplicationSession(application, user)
        db.session.add(i1)
        db.session.commit()
        # Anonymous
        response = self.make_request(
            method='DELETE',
            path='/api/v1/application_sessions/%s' % i1.id
        )
        self.assert_401(response)
        # Authenticated User of the application session
        response = self.make_authenticated_user_request(
            method='DELETE',
            path='/api/v1/application_sessions/%s' % i1.id
        )
        self.assert_202(response)

        i2 = ApplicationSession(application, user)
        db.session.add(i2)
        db.session.commit()
        # Authenticated Workspace Owner of the application session
        response = self.make_authenticated_workspace_owner_request(
            method='DELETE',
            path='/api/v1/application_sessions/%s' % i2.id
        )
        self.assert_202(response)

        i3 = ApplicationSession(application, user)
        db.session.add(i3)
        db.session.commit()
        # Authenticated Workspace Manager of the application session
        response = self.make_authenticated_workspace_owner2_request(
            method='DELETE',
            path='/api/v1/application_sessions/%s' % i3.id
        )
        self.assert_202(response)

        i4 = ApplicationSession(application, user)
        db.session.add(i4)
        db.session.commit()
        # Admin
        response = self.make_authenticated_admin_request(
            method='DELETE',
            path='/api/v1/application_sessions/%s' % i4.id
        )
        self.assert_202(response)

        environment2 = Application.query.filter_by(id=self.known_application_id_g2).first()
        user2 = User.query.filter_by(id=self.known_workspace_owner_id_2).first()
        i5 = ApplicationSession(environment2, user2)
        db.session.add(i5)
        db.session.commit()
        # User is not part of the workspace
        response = self.make_authenticated_user_request(
            method='DELETE',
            path='/api/v1/application_sessions/%s' % i5.id
        )
        self.assert_404(response)
        # Is just a Normal user of the workspace who didn't spawn the application session
        response = self.make_authenticated_workspace_owner_request(
            method='DELETE',
            path='/api/v1/application_sessions/%s' % i5.id
        )
        self.assert_403(response)
        # Authenticated Workspace Owner of the workspace
        response = self.make_authenticated_workspace_owner2_request(
            method='DELETE',
            path='/api/v1/application_sessions/%s' % i5.id
        )
        self.assert_202(response)

    def test_application_session_logs(self):
        epoch_time = time.time()
        log_record = {
            'log_level': 'INFO',
            'log_type': 'provisioning',
            'timestamp': epoch_time,
            'message': 'log testing'
        }
        response_patch = self.make_authenticated_admin_request(
            method='PATCH',
            path='/api/v1/application_sessions/%s/logs' % self.known_application_session_id,
            data=json.dumps({'log_record': log_record})
        )
        self.assert_200(response_patch)

        response_get = self.make_authenticated_user_request(
            method='GET',
            path='/api/v1/application_sessions/%s/logs' % self.known_application_session_id,
            data=json.dumps({'log_type': 'provisioning'})
        )
        self.assert_200(response_get)
        self.assertEqual(response_get.json[0]['timestamp'], epoch_time)

        # delete logs as normal user
        response_delete = self.make_authenticated_user_request(
            method='DELETE',
            path='/api/v1/application_sessions/%s/logs' % self.known_application_session_id
        )
        self.assert_403(response_delete)

        # delete logs as admin
        response_delete = self.make_authenticated_admin_request(
            method='DELETE',
            path='/api/v1/application_sessions/%s/logs' % self.known_application_session_id
        )
        self.assert_200(response_delete)

        # check that logs are empty
        response_get = self.make_authenticated_user_request(
            method='GET',
            path='/api/v1/application_sessions/%s/logs' % self.known_application_session_id,
            data=json.dumps({'log_type': 'provisioning'})
        )
        self.assert_200(response_get)
        self.assertEqual(len(response_get.json), 0)

        # test patching running logs - should be replaced, not appended
        log_record['log_type'] = 'running'
        response_patch = self.make_authenticated_admin_request(
            method='PATCH',
            path='/api/v1/application_sessions/%s/logs' % self.known_application_session_id,
            data=json.dumps({'log_record': log_record})
        )
        self.assert_200(response_patch)
        log_record['message'] = 'patched running logs'
        response_patch = self.make_authenticated_admin_request(
            method='PATCH',
            path='/api/v1/application_sessions/%s/logs' % self.known_application_session_id,
            data=json.dumps({'log_record': log_record})
        )
        self.assert_200(response_patch)
        response_get = self.make_authenticated_user_request(
            method='GET',
            path='/api/v1/application_sessions/%s/logs' % self.known_application_session_id,
            data=json.dumps({})
        )
        self.assert_200(response_get)
        self.assertEqual(1, len(response_get.json))
        self.assertEqual('patched running logs', response_get.json[0]['message'])

    def test_user_workspace_quota(self):
        # Anonymous
        response = self.make_request(
            method='PATCH',
            path='/api/v1/users/%s' % self.known_user_id,
            data=json.dumps(dict(workspace_quota=1))
        )
        self.assert_401(response)

        # Authenticated
        response = self.make_authenticated_user_request(
            method='PATCH',
            path='/api/v1/users/%s' % self.known_user_id,
            data=json.dumps(dict(workspace_quota=1))
        )
        self.assert_403(response)

        # Admin
        response = self.make_authenticated_admin_request(
            method='PATCH',
            path='/api/v1/users/%s' % self.known_user_id,
            data=json.dumps(dict(workspace_quota=1))
        )
        self.assert_200(response)

        # invalid inputs
        for invalid_input in [-1, 1000 * 1000, 'foo']:
            response = self.make_authenticated_admin_request(
                method='PATCH',
                path='/api/v1/users/%s' % self.known_user_id,
                data=json.dumps(dict(workspace_quota=invalid_input))
            )
            self.assertTrue(response.status_code in [400, 422])

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

    def test_user_and_workspace_owner_export_application_templates(self):
        response = self.make_authenticated_user_request(path='/api/v1/import_export/application_templates')
        self.assertStatus(response, 403)

        response = self.make_authenticated_workspace_owner_request(path='/api/v1/import_export/application_templates')
        self.assertStatus(response, 403)

    def test_admin_export_application_templates(self):

        response = self.make_authenticated_admin_request(path='/api/v1/import_export/application_templates')
        self.assertStatus(response, 200)
        self.assertEqual(len(response.json), 2)  # There were total 2 templates initialized during setup

    def test_user_and_workspace_owner_import_application_templates(self):

        applications_data = [
            {'name': 'foo',
             'config': {
                 'maximum_lifetime': '1h'
             },
             'cluster_name': 'dummy',
             'allowed_attrs': ['maximum_lifetime']
             },
            {'name': 'foobar',
             'config': {
                 'maximum_lifetime': '1d 10m', 'description': 'dummy application'
             },
             'cluster_name': 'dummy',
             'allowed_attrs': []
             }
        ]
        # Authenticated User
        for application_item in applications_data:
            response = self.make_authenticated_user_request(
                method='POST',
                path='/api/v1/import_export/application_templates',
                data=json.dumps(application_item))
            self.assertEqual(response.status_code, 403)
        # Workspace Owner
        for application_item in applications_data:
            response = self.make_authenticated_workspace_owner_request(
                method='POST',
                path='/api/v1/import_export/application_templates',
                data=json.dumps(application_item))
            self.assertEqual(response.status_code, 403)

    def test_admin_import_application_templates(self):

        applications_data = [
            {'name': 'foo',
             'config': {
                 'maximum_lifetime': '1h'
             },
             'cluster_name': 'dummy_cluster_1',
             'allowed_attrs': ['maximum_lifetime']
             },
            {'name': 'foobar',
             'config': {
                 'maximum_lifetime': '1d 10m', 'description': 'dummy application'
             },
             'cluster_name': 'dummy_cluster_1',
             'allowed_attrs': []
             }
        ]
        # Admin
        for application_item in applications_data:
            response = self.make_authenticated_admin_request(
                method='POST',
                path='/api/v1/import_export/application_templates',
                data=json.dumps(application_item))
            self.assertEqual(response.status_code, 200)

    def test_anonymous_export_applications(self):
        response = self.make_request(path='/api/v1/import_export/applications')
        self.assertStatus(response, 401)

    def test_user_export_applications(self):
        response = self.make_authenticated_user_request(path='/api/v1/import_export/applications')
        self.assertStatus(response, 403)

    def test_workspace_owner_export_applications(self):
        response = self.make_authenticated_workspace_owner_request(path='/api/v1/import_export/applications')
        self.assertStatus(response, 200)
        self.assertEqual(len(response.json), 4)

    def test_admin_export_applications(self):

        response = self.make_authenticated_admin_request(path='/api/v1/import_export/applications')
        self.assertStatus(response, 200)
        self.assertEqual(len(response.json), 12)  # There were total 12 applications initialized during setup

    def test_anonymous_import_applications(self):

        applications_data = [
            {'name': 'foo',
             'config': {
                 'maximum_lifetime': '1h'
             },
             'template_name': 'TestTemplate',
             'workspace_name': 'Workspace1'
             },
            {'name': 'foobar',
             'config': {
                 'maximum_lifetime': '1d 10m', 'description': 'dummy application'
             },
             'template_name': 'TestTemplate',
             'workspace_name': 'Workspace1'
             }
        ]

        for application_item in applications_data:
            response = self.make_request(  # Test for authenticated user
                method='POST',
                path='/api/v1/import_export/applications',
                data=json.dumps(application_item))
            self.assertEqual(response.status_code, 401)

    def test_user_import_applications(self):

        applications_data = [
            {'name': 'foo',
             'config': {
                 'maximum_lifetime': '1h'
             },
             'template_name': 'TestTemplate',
             'workspace_name': 'Workspace1'
             },
            {'name': 'foobar',
             'config': {
                 'maximum_lifetime': '1d 10m', 'description': 'dummy application'
             },
             'template_name': 'TestTemplate',
             'workspace_name': 'Workspace1'
             }
        ]

        for application_item in applications_data:
            response = self.make_authenticated_user_request(  # Test for authenticated user
                method='POST',
                path='/api/v1/import_export/applications',
                data=json.dumps(application_item))
            self.assertEqual(response.status_code, 403)

    def test_admin_import_applications(self):

        applications_data = [
            {'name': 'foo',
             'config': {
                 'maximum_lifetime': '1h'
             },
             'template_name': 'EnabledTestTemplate',
             'workspace_name': 'Workspace1'
             },
            {'name': 'foobar',
             'config': {
                 'maximum_lifetime': '1d 10m', 'description': 'dummy application'
             },
             'template_name': 'EnabledTestTemplate',
             'workspace_name': 'Workspace1'
             }
        ]

        for application_item in applications_data:
            response = self.make_authenticated_admin_request(
                method='POST',
                path='/api/v1/import_export/applications',
                data=json.dumps(application_item))
            self.assertEqual(response.status_code, 200)

        application_invalid1 = {'name': 'foo', 'template_name': 'EnabledTestTemplate', 'workspace_name': 'Workspace1'}
        response1 = self.make_authenticated_admin_request(
            method='POST',
            path='/api/v1/import_export/applications',
            data=json.dumps(application_invalid1))
        self.assertEqual(response1.status_code, 422)

        application_invalid2 = {'name': '', 'template_name': 'EnabledTestTemplate', 'workspace_name': 'Workspace1'}
        response2 = self.make_authenticated_admin_request(
            method='POST',
            path='/api/v1/import_export/applications',
            data=json.dumps(application_invalid2))
        self.assertEqual(response2.status_code, 422)

        application_invalid3 = {'name': 'foo', 'config': {'maximum_lifetime': '1h'}, 'template_name': '', 'workspace_name': 'Workspace1'}
        response3 = self.make_authenticated_admin_request(
            method='POST',
            path='/api/v1/import_export/applications',
            data=json.dumps(application_invalid3))
        self.assertEqual(response3.status_code, 422)

        application_invalid4 = {'name': 'foo', 'config': {'maximum_lifetime': '1h'}, 'template_name': 'EnabledTestTemplate', 'workspace_name': ''}
        response3 = self.make_authenticated_admin_request(
            method='POST',
            path='/api/v1/import_export/applications',
            data=json.dumps(application_invalid4))
        self.assertEqual(response3.status_code, 422)

    def test_workspace_owner_import_applications(self):

        applications_data = [
            {'name': 'foo',
             'config': {
                 'maximum_lifetime': '1h'
             },
             'template_name': 'EnabledTestTemplate',
             'workspace_name': 'Workspace1'
             },
            {'name': 'foobar',
             'config': {
                 'maximum_lifetime': '1d 10m', 'description': 'dummy application'
             },
             'template_name': 'EnabledTestTemplate',
             'workspace_name': 'Workspace1'
             }
        ]

        for application in applications_data:
            response = self.make_authenticated_workspace_owner_request(
                method='POST',
                path='/api/v1/import_export/applications',
                data=json.dumps(application))
            self.assertEqual(response.status_code, 200)

        application_invalid = {
            'name': 'bar5',
            'config': {
                'maximum_lifetime': '1h'
            },
            'template_name': 'EnabledTestTemplate',
            'workspace_name': 'Workspace2'
        }
        # owner should not be able to import to other workspaces where he is normal user
        response1 = self.make_authenticated_workspace_owner_request(
            method='POST',
            path='/api/v1/import_export/applications',
            data=json.dumps(application_invalid))
        self.assertEqual(response1.status_code, 404)

        application_invalid_data = [
            {'name': 'foo', 'template_name': 'EnabledTestTemplate', 'workspace_name': 'Workspace1'},
            {'name': '', 'template_name': 'EnabledTestTemplate', 'workspace_name': 'Workspace1'},
            {'name': 'foo', 'config': {'maximum_lifetime': '1h'}, 'template_name': '', 'workspace_name': 'Workspace1'},
            {'name': 'foo', 'config': {'maximum_lifetime': '1h'}, 'template_name': 'EnabledTestTemplate',
             'workspace_name': ''}
        ]

        for application in application_invalid_data:
            response1 = self.make_authenticated_workspace_owner_request(
                method='POST',
                path='/api/v1/import_export/applications',
                data=json.dumps(application))
            self.assertStatus(response1, 422)

    def test_workspace_manager_import_applications(self):
        g = Workspace('Workspace1')
        u4 = User.query.filter_by(id=self.known_workspace_owner_id_2).first()
        wmu4_obj = WorkspaceUserAssociation(user=u4, workspace=g, is_manager=True, is_owner=False)
        g.user_associations.append(wmu4_obj)
        db.session.add(g)
        db.session.commit()

        applications_data = [
            {'name': 'foo',
             'config': {
                 'maximum_lifetime': '1h'
             },
             'template_name': 'EnabledTestTemplate',
             'workspace_name': 'Workspace1'
             },
            {'name': 'foobar',
             'config': {
                 'maximum_lifetime': '1d 10m', 'description': 'dummy application'
             },
             'template_name': 'EnabledTestTemplate',
             'workspace_name': 'Workspace1'
             }
        ]

        for application in applications_data:
            response = self.make_authenticated_workspace_owner2_request(
                method='POST',
                path='/api/v1/import_export/applications',
                data=json.dumps(application))
            self.assertEqual(response.status_code, 200)

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

    def test_anonymous_get_application_categories(self):
        response = self.make_request(
            path='/api/v1/application_categories'
        )
        self.assert_401(response)

    def test_user_application_categories(self):
        response = self.make_authenticated_user_request(
            path='/api/v1/application_categories'
        )
        self.assert_200(response)
        self.assertGreater(len(response.json), 0)

    def test_get_alerts_access(self):
        response = self.make_request(
            path='/api/v1/alerts'
        )
        self.assert_401(response)

        response = self.make_authenticated_user_request(
            path='/api/v1/alerts'
        )
        self.assert_403(response)

        response = self.make_authenticated_workspace_owner_request(
            path='/api/v1/alerts'
        )
        self.assert_403(response)

    def test_alerts_admin(self):
        alert1 = dict(
            target='cluster-1',
            source='prometheus',
            status='firing',
            data=[dict(some_key='value')]
        )
        alert2 = dict(
            target='cluster-2',
            source='prometheus',
            status='ok',
            data=[dict(some_key='different value')]
        )

        # add alerts
        response = self.make_authenticated_admin_request(
            method='POST',
            path='/api/v1/alerts',
            data=json.dumps(alert1)
        )
        self.assertStatus(response, 200)
        response = self.make_authenticated_admin_request(
            method='POST',
            path='/api/v1/alerts',
            data=json.dumps(alert2)
        )
        self.assertStatus(response, 200)

        # query a single alert
        response = self.make_authenticated_admin_request(
            path='/api/v1/alerts/%s/%s' % (alert1['target'], alert1['source']),
        )
        self.assertStatus(response, 200)
        self.assertEqual(response.json['target'], 'cluster-1')
        self.assertEqual(response.json['source'], 'prometheus')
        self.assertEqual(response.json['data'][0]['some_key'], 'value')

        # query list
        response = self.make_authenticated_admin_request(
            path='/api/v1/alerts',
        )
        self.assertStatus(response, 200)
        self.assertEqual(len(response.json), 2)

        # modify alert
        alert1['status'] = 'ok'
        alert1['data'] = []
        response = self.make_authenticated_admin_request(
            method='POST',
            path='/api/v1/alerts',
            data=json.dumps(alert1)
        )
        self.assertStatus(response, 200)
        response = self.make_authenticated_admin_request(
            path='/api/v1/alerts/%s/%s' % (alert1['target'], alert1['source']),
        )
        self.assertStatus(response, 200)
        self.assertEqual(response.json['target'], 'cluster-1')
        self.assertEqual(response.json['source'], 'prometheus')
        self.assertEqual(response.json['status'], 'ok')

        # invalid data
        alert1['target'] = None
        response = self.make_authenticated_admin_request(
            method='POST',
            path='/api/v1/alerts',
            data=json.dumps(alert1)
        )
        self.assertStatus(response, 422)

    def test_workspace_accounting(self):
        # Anonymous
        response = self.make_request(
            method='GET',
            path='/api/v1/workspaces/%s/accounting' % self.known_workspace_id
        )
        self.assert_401(response)

        # Authenticated User, not a manager
        response = self.make_authenticated_user_request(
            method='GET',
            path='/api/v1/workspaces/%s/accounting' % self.known_workspace_id)
        self.assertStatus(response, 403)

        # Authenticated Workspace Owner , who does not own the workspace
        response = self.make_authenticated_workspace_owner_request(
            method='GET',
            path='/api/v1/workspaces/%s/accounting' % self.known_workspace_id_2,
            data=json.dumps({})
        )
        self.assertStatus(response, 403)

        # Admins
        response = self.make_authenticated_admin_request(
            method='GET',
            path='/api/v1/workspaces/%s/accounting' % self.known_workspace_id,
            data=json.dumps({})
        )
        self.assertStatus(response, 200)

        # Test total gibs are returned right
        response = self.make_authenticated_admin_request(
            method='GET',
            path='/api/v1/workspaces/%s/accounting' % self.known_workspace_id,
            data=json.dumps({})
        )
        self.assertStatus(response, 200)
        self.assertEqual(response.json['gib_hours'], 28)

    def test_get_tasks_access(self):
        response = self.make_request(
            path='/api/v1/tasks'
        )
        self.assert_401(response)

        response = self.make_authenticated_user_request(
            path='/api/v1/tasks'
        )
        self.assert_403(response)

        response = self.make_authenticated_workspace_owner_request(
            path='/api/v1/tasks'
        )
        self.assert_403(response)

    def test_tasks_admin(self):
        task1 = dict(
            kind='workspace_backup',
            data=[dict(some_key='value1')]
        )
        task2 = dict(
            kind='workspace_backup',
            data=[dict(some_key='value2')]
        )

        # add tasks
        t1_response = self.make_authenticated_admin_request(
            method='POST',
            path='/api/v1/tasks',
            data=json.dumps(task1)
        )
        self.assertStatus(t1_response, 200)

        t2_response = self.make_authenticated_admin_request(
            method='POST',
            path='/api/v1/tasks',
            data=json.dumps(task2)
        )
        self.assertStatus(t2_response, 200)

        # query a single task
        response = self.make_authenticated_admin_request(
            path='/api/v1/tasks/%s' % t1_response.json.get('id'),
        )
        self.assertStatus(response, 200)
        self.assertEqual(response.json['kind'], 'workspace_backup')
        self.assertEqual(response.json['data'][0]['some_key'], 'value1')

        # query list
        response = self.make_authenticated_admin_request(
            path='/api/v1/tasks',
        )
        self.assertStatus(response, 200)
        self.assertEqual(len(response.json), 2)

        # update task 1 state to processing
        response = self.make_authenticated_admin_request(
            method='PATCH',
            path='/api/v1/tasks/%s' % t1_response.json.get('id'),
            data=json.dumps(dict(state='processing'))
        )
        self.assertStatus(response, 200)

        # query list of all unfinished tasks
        response = self.make_authenticated_admin_request(
            path='/api/v1/tasks?unfinished=1',
        )
        self.assertStatus(response, 200)
        self.assertEqual(len(response.json), 2)

        # update task 1 state to finished
        response = self.make_authenticated_admin_request(
            method='PATCH',
            path='/api/v1/tasks/%s' % t1_response.json.get('id'),
            data=json.dumps(dict(state='finished'))
        )
        self.assertStatus(response, 200)

        # query list of all unfinished tasks
        response = self.make_authenticated_admin_request(
            path='/api/v1/tasks?unfinished=1',
        )
        self.assertStatus(response, 200)
        self.assertEqual(len(response.json), 1)

        # query list of all finished tasks
        response = self.make_authenticated_admin_request(
            path='/api/v1/tasks?state=finished',
        )
        self.assertStatus(response, 200)
        self.assertEqual(len(response.json), 1)

        # invalid data
        task1['kind'] = 'foo'
        response = self.make_authenticated_admin_request(
            method='POST',
            path='/api/v1/tasks',
            data=json.dumps(task1)
        )
        self.assertStatus(response, 422)

        # missing data
        task1['kind'] = None
        response = self.make_authenticated_admin_request(
            method='POST',
            path='/api/v1/tasks',
            data=json.dumps(task1)
        )
        self.assertStatus(response, 422)

        # try patching with invalid state
        response = self.make_authenticated_admin_request(
            method='PATCH',
            path='/api/v1/tasks/%s' % t1_response.json.get('id'),
            data=json.dumps(dict(state='asdfasdf'))
        )
        self.assertStatus(response, 422)


if __name__ == '__main__':
    unittest.main()
