#
# PyTest global setup and fixture file
#
import base64
import datetime
import json
import os
import time

import pytest

from pebbles.models import (
    User, Workspace, WorkspaceMembership, ApplicationTemplate, Application,
    Message, ServiceAnnouncement, ApplicationSession, ApplicationSessionLog)
from pebbles.models import db

# set unittesting configuration before initializing Flask
os.environ['UNITTEST'] = '1'
from pebbles.server import app

ADMIN_TOKEN = None
USER_TOKEN = None
USER_2_TOKEN = None
COURSE_OWNER_TOKEN = None
COURSE_OWNER_TOKEN2 = None


@pytest.fixture
def pri_data():
    with app.app_context():
        pd = PrimaryData()
        yield pd
        db.session.remove()
        db.drop_all()


class PrimaryData:
    def __init__(self):
        def fill_application_from_template(application, template):
            application.base_config = template.base_config.copy()
            application.attribute_limits = template.attribute_limits.copy()
            application.application_type = template.application_type

        db.create_all()

        self.known_admin_ext_id = "admin@example.org"
        self.known_admin_password = "admin"
        self.known_user_ext_id = "user@example.org"
        self.known_user_password = "user"
        self.known_user_2_ext_id = "user-2@example.org"
        self.known_user_2_password = "user-2"

        u1 = User(self.known_admin_ext_id, self.known_admin_password, is_admin=True)
        u2 = User(self.known_user_ext_id, self.known_user_password, is_admin=False)
        u3 = User("workspace_owner@example.org", "workspace_owner")
        u4 = User("workspace_owner2@example.org", "workspace_owner2")
        u5 = User("deleted_user1@example.org", "deleted_user1")
        u5.is_deleted = True
        u6 = User(self.known_user_2_ext_id, self.known_user_2_password, is_admin=False)
        u7 = User("expired_user@example.org", "expired_user")
        u7.expiry_ts = 10000000

        # Fix user IDs to be the same for all tests, in order to reuse the same token
        # for multiple tests
        u1.id = 'u1'
        u2.id = 'u2'
        self.known_admin_id = u1.id
        self.known_admin_id = u1.id
        self.known_user_id = u2.id
        u3.id = 'u3'
        u3.workspace_quota = 2
        u4.id = 'u4'
        u4.workspace_quota = 2
        u5.id = 'u5'
        u6.id = 'u6'
        u7.id = 'u7'

        self.known_admin_id = u1.id
        self.known_user_id = u2.id
        self.known_deleted_user_id = u5.id
        self.known_workspace_owner_id = u3.id
        self.known_workspace_owner_id_2 = u4.id
        self.known_expired_user_id = u7.id

        db.session.add(u1)
        db.session.add(u2)
        db.session.add(u3)
        db.session.add(u4)
        db.session.add(u5)
        db.session.add(u6)
        db.session.add(u7)

        ws0 = Workspace('System.default')
        ws0.id = 'ws0'
        ws0.memberships.append(WorkspaceMembership(user=u1, is_owner=True))
        ws0.memberships.append(WorkspaceMembership(user=u2))
        ws0.memberships.append(WorkspaceMembership(user=u3))
        ws0.memberships.append(WorkspaceMembership(user=u4))
        ws0.memberships.append(WorkspaceMembership(user=u5))
        ws0.memberships.append(WorkspaceMembership(user=u6))
        ws0.memberships.append(WorkspaceMembership(user=u7))
        db.session.add(ws0)

        ws1 = Workspace('Workspace1')
        ws1.id = 'ws1'
        ws1.cluster = 'dummy_cluster_1'
        ws1.application_quota = 6
        ws1.memberships.append(WorkspaceMembership(user=u2))
        ws1.memberships.append(WorkspaceMembership(user=u3, is_manager=True, is_owner=True))
        ws1.memberships.append(WorkspaceMembership(user=u4, is_manager=True))
        ws1.memberships.append(WorkspaceMembership(user=u6))
        db.session.add(ws1)

        ws2 = Workspace('Workspace2')
        ws2.id = 'ws2'
        ws2.cluster = 'dummy_cluster_1'
        ws2.memberships.append(WorkspaceMembership(user=u3))
        ws2.memberships.append(WorkspaceMembership(user=u4, is_manager=True, is_owner=True))
        db.session.add(ws2)

        ws3 = Workspace('Workspace3')
        ws3.id = 'ws3'
        ws3.cluster = 'dummy_cluster_2'
        ws3.memberships.append(WorkspaceMembership(user=u4, is_manager=True, is_owner=True))
        ws3.memberships.append(WorkspaceMembership(user=u2, is_banned=True))
        ws3.memberships.append(WorkspaceMembership(user=u3, is_banned=True))
        db.session.add(ws3)

        ws4 = Workspace('Workspace4')
        ws4.id = 'ws4'
        ws4.cluster = 'dummy_cluster_2'
        ws4.memberships.append(WorkspaceMembership(user=u1, is_manager=True, is_owner=True))
        db.session.add(ws4)

        # deleted workspace
        ws5 = Workspace('Workspace5')
        ws5.id = 'ws5'
        ws5.cluster = 'dummy_cluster_1'
        ws5.status = 'deleted'
        ws5.memberships.append(WorkspaceMembership(user=u2, is_manager=True, is_owner=True))
        db.session.add(ws5)

        ws6 = Workspace('Workspace6')
        ws6.id = 'ws6'
        ws6.description = 'workspace for memory limit testing'
        ws6.cluster = 'dummy_cluster_1'
        ws6.application_quota = 6
        ws6.memory_limit_gib = 10
        ws6.memberships.append(WorkspaceMembership(user=u6))
        db.session.add(ws6)

        ws7 = Workspace('Workspace7')
        ws7.id = 'ws7'
        ws7.description = 'workspace with workspace membership expiry policy'
        ws7.cluster = 'dummy_cluster_1'
        ws7.membership_expiry_policy = dict(kind=Workspace.MEP_ACTIVITY_TIMEOUT, timeout_days=30)
        ws7.memberships.append(WorkspaceMembership(user=u6))
        ws7.expiry_ts = time.time() - 3600 * 24 * 2
        db.session.add(ws7)

        ws8 = Workspace('Workspace8')
        ws8.id = 'ws8'
        ws8.description = 'expired workspace beyond grace'
        ws8.cluster = 'dummy_cluster_1'
        ws8.expiry_ts = time.time() - 3600 * 24 * 30 * 7
        db.session.add(ws8)

        self.known_workspace_id = ws1.id
        self.known_workspace_id_2 = ws2.id
        self.known_workspace_id_3 = ws3.id
        self.known_banned_workspace_join_id = ws3.join_code
        self.known_workspace_join_id = ws4.join_code
        self.system_default_workspace_id = ws0.id

        t1 = ApplicationTemplate()
        t1.name = 'TestTemplate'
        t1.application_type = 'generic'
        t1.base_config = {}
        db.session.add(t1)
        self.known_template_id_disabled = t1.id

        t2 = ApplicationTemplate()
        t2.name = 'EnabledTestTemplate'
        t2.application_type = 'generic'
        t2.base_config = {
            'labels': '["label1", "label with space", "label2"]',
            'cost_multiplier': '1.0',
            'maximum_lifetime': 3600,
            'memory_gib': 8,
            'allow_update_client_connectivity': False
        }
        t2.attribute_limits = [
            dict(name='maximum_lifetime', min=0, max=3600 * 12),
            dict(name='memory_gib', min=0, max=8),
        ]
        t2.is_enabled = True
        db.session.add(t2)
        self.known_template_id = t2.id

        a0 = Application()
        a0.name = "Public application"
        a0.labels = ['label1', 'label with space', 'label2']
        a0.template_id = t2.id
        a0.workspace_id = ws0.id
        a0.is_enabled = True
        fill_application_from_template(a0, t2)
        db.session.add(a0)
        self.known_application_public = a0.id

        a1 = Application()
        a1.name = "TestApplication"
        a1.labels = ['label1', 'label with space', 'label2']
        a1.template_id = t2.id
        a1.workspace_id = ws1.id
        fill_application_from_template(a1, t2)
        db.session.add(a1)
        self.known_application_id_disabled = a1.id

        a2 = Application()
        a2.name = "EnabledTestApplication"
        a2.labels = ['label1', 'label with space', 'label2']
        a2.template_id = t2.id
        a2.workspace_id = ws1.id
        a2.is_enabled = True
        fill_application_from_template(a2, t2)
        a2.config = dict(maximum_lifetime=3600)
        db.session.add(a2)
        self.known_application_id = a2.id

        a3 = Application()
        a3.name = "EnabledTestApplicationClientIp"
        a3.labels = ['label1', 'label with space', 'label2']
        a3.template_id = t2.id
        a3.workspace_id = ws1.id
        a3.is_enabled = True
        a3.config = {'allow_update_client_connectivity': True}
        fill_application_from_template(a3, t2)
        db.session.add(a3)
        self.known_application_id_2 = a3.id

        a4 = Application()
        a4.name = "EnabledTestApplicationOtherWorkspace"
        a2.labels = ['label1', 'label with space', 'label2']
        a4.template_id = t2.id
        a4.workspace_id = ws2.id
        a4.is_enabled = True
        fill_application_from_template(a4, t2)
        db.session.add(a4)
        self.known_application_id_g2 = a4.id

        a5 = Application()
        a5.name = "DisabledTestApplicationOtherWorkspace"
        a5.labels = ['label1', 'label with space', 'label2']
        a5.template_id = t2.id
        a5.workspace_id = ws2.id
        fill_application_from_template(a5, t2)
        db.session.add(a5)
        self.known_application_id_disabled_2 = a5.id

        a6 = Application()
        a6.name = "TestArchivedApplication"
        a6.labels = ['label1', 'label with space', 'label2']
        a6.template_id = t2.id
        a6.workspace_id = ws2.id
        a6.status = Application.STATUS_ARCHIVED
        fill_application_from_template(a6, t2)
        db.session.add(a6)
        self.known_application_id_archived = a6.id

        a7 = Application()
        a7.name = "TestDeletedApplication"
        a7.labels = ['label1', 'label with space', 'label2']
        a7.template_id = t2.id
        a7.workspace_id = ws2.id
        a7.status = Application.STATUS_DELETED
        fill_application_from_template(a7, t2)
        db.session.add(a7)
        self.known_application_id_deleted = a7.id

        a8 = Application()
        a8.name = "EnabledTestApplication"
        a8.labels = ['label1', 'label with space', 'label2']
        a8.template_id = t2.id
        a8.workspace_id = ws1.id
        a8.is_enabled = True
        fill_application_from_template(a8, t2)
        db.session.add(a8)
        self.known_application_id_empty = a8.id

        a9 = Application()
        a9.name = "MemLimitTest 1"
        a9.labels = ['label1', 'label with space', 'label2']
        a9.template_id = t2.id
        a9.workspace_id = ws6.id
        a9.is_enabled = True
        fill_application_from_template(a9, t2)
        db.session.add(a9)
        self.known_application_id_mem_limit_test_1 = a9.id

        a10 = Application()
        a10.name = "MemLimitTest 2"
        a10.labels = ['label1', 'label with space', 'label2']
        a10.template_id = t2.id
        a10.workspace_id = ws6.id
        a10.is_enabled = True
        fill_application_from_template(a10, t2)
        db.session.add(a10)
        self.known_application_id_mem_limit_test_2 = a10.id

        a11 = Application()
        a11.name = "MemLimitTest 3"
        a11.labels = ['label1', 'label with space', 'label2']
        a11.template_id = t2.id
        a11.workspace_id = ws6.id
        a11.is_enabled = True
        fill_application_from_template(a11, t2)
        # we need to modify and assign the full base_config here due to how hybrid properties behave
        base_config = a11.base_config
        base_config['memory_gib'] = 1.0
        a11.base_config = base_config
        db.session.add(a11)
        self.known_application_id_mem_limit_test_3 = a11.id

        m1 = Message("First message", "First message message")
        self.known_message_id = m1.id
        db.session.add(m1)

        m2 = Message("Second message", "Second message message")
        self.known_message2_id = m2.id
        db.session.add(m2)

        an1 = ServiceAnnouncement("1st Service announcement", "1st Service announcement", 1,
                                  "welcome", True, True)
        self.known_announcement_id = an1.id
        db.session.add(an1)

        an2 = ServiceAnnouncement("2nd Service announcement", "2nd Service announcement Service announcement", 2,
                                  "login", False, True)
        self.known_announcement2_id = an2.id
        db.session.add(an2)

        an3 = ServiceAnnouncement("3rd Service announcement",
                                  "3rd Service announcement Service announcement Service announcement", 3,
                                  "catalog, my-workspace", True, False)
        self.known_announcement3_id = an3.id
        db.session.add(an3)

        an4 = ServiceAnnouncement("4th Service announcement",
                                  "4th Service announcement Service announcement Service announcement", 4,
                                  "workspace-owner", False, False)

        self.known_announcement4_id = an4.id
        db.session.add(an4)

        i1 = ApplicationSession(
            Application.query.filter_by(id=a2.id).first(),
            User.query.filter_by(ext_id="user@example.org").first())
        i1.name = 'pb-i1'
        i1.state = ApplicationSession.STATE_RUNNING
        db.session.add(i1)
        self.known_application_session_id = i1.id

        i2 = ApplicationSession(
            Application.query.filter_by(id=a3.id).first(),
            User.query.filter_by(ext_id="user@example.org").first())
        i2.name = 'pb-i2'
        i2.state = ApplicationSession.STATE_RUNNING
        db.session.add(i2)
        db.session.add(ApplicationSessionLog(i2.id, 'info', 'provisioning', '1000.0', 'provisioning done'))
        self.known_application_session_id_2 = i2.id

        i3 = ApplicationSession(
            Application.query.filter_by(id=a3.id).first(),
            User.query.filter_by(ext_id="user@example.org").first())
        i3.name = 'pb-i3'
        i3.to_be_deleted = True
        i3.provisioned_at = datetime.datetime.strptime("2022-06-28T13:00:00", "%Y-%m-%dT%H:%M:%S")
        i3.deprovisioned_at = datetime.datetime.strptime("2022-06-28T14:00:00", "%Y-%m-%dT%H:%M:%S")
        i3.provisioning_config = dict(memory_gib=4)
        i3.state = ApplicationSession.STATE_DELETED
        db.session.add(i3)

        i4 = ApplicationSession(
            Application.query.filter_by(id=a3.id).first(),
            User.query.filter_by(ext_id="workspace_owner@example.org").first())
        i4.name = 'pb-i4'
        i4.state = ApplicationSession.STATE_FAILED
        db.session.add(i4)
        self.known_application_session_id_4 = i4.id

        i5 = ApplicationSession(
            Application.query.filter_by(id=a4.id).first(),
            User.query.filter_by(ext_id="admin@example.org").first())
        i5.name = 'pb-i5'
        i5.state = ApplicationSession.STATE_RUNNING
        db.session.add(i5)

        i6 = ApplicationSession(
            Application.query.filter_by(id=a3.id).first(),
            User.query.filter_by(ext_id="user@example.org").first())
        i6.name = 'pb-i6'
        i6.to_be_deleted = True
        i6.provisioned_at = datetime.datetime.strptime("2022-06-28T13:00:00", "%Y-%m-%dT%H:%M:%S")
        i6.deprovisioned_at = datetime.datetime.strptime("2022-06-28T16:00:00", "%Y-%m-%dT%H:%M:%S")
        i6.provisioning_config = dict(memory_gib=8)
        i6.state = ApplicationSession.STATE_DELETED
        db.session.add(i6)

        db.session.commit()


@pytest.fixture
def client():
    return app.test_client()


@pytest.fixture
def rmaker(client, pri_data):
    return RequestMaker(client, pri_data)


class RequestMaker():
    def __init__(self, client, pri_data: PrimaryData):
        self.client = client
        self.pri_data = pri_data
        self.methods = {
            'GET': self.client.get,
            'POST': self.client.post,
            'PUT': self.client.put,
            'PATCH': self.client.patch,
            'DELETE': self.client.delete,
        }

    def make_request(self, method='GET', path='/', headers=None, data=None):
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
            ADMIN_TOKEN = self.get_auth_token(
                {'ext_id': 'admin@example.org', 'password': 'admin', 'agreement_sign': 'signed'})

        self.admin_token = ADMIN_TOKEN

        return self.make_authenticated_request(method, path, headers, data,
                                               auth_token=self.admin_token)

    def make_authenticated_user_request(self, method='GET', path='/', headers=None, data=None):
        global USER_TOKEN
        if not USER_TOKEN:
            USER_TOKEN = self.get_auth_token(creds={
                'ext_id': self.pri_data.known_user_ext_id,
                'password': self.pri_data.known_user_password,
                'agreement_sign': 'signed'}
            )
        self.user_token = USER_TOKEN
        return self.make_authenticated_request(method, path, headers, data,
                                               auth_token=self.user_token)

    def make_authenticated_user_2_request(self, method='GET', path='/', headers=None, data=None):
        global USER_2_TOKEN
        if not USER_2_TOKEN:
            USER_2_TOKEN = self.get_auth_token(creds={
                'ext_id': self.pri_data.known_user_2_ext_id,
                'password': self.pri_data.known_user_2_password,
                'agreement_sign': 'signed'}
            )
        self.user_token = USER_2_TOKEN
        return self.make_authenticated_request(method, path, headers, data,
                                               auth_token=self.user_token)

    def make_authenticated_workspace_owner_request(self, method='GET', path='/', headers=None, data=None):
        global COURSE_OWNER_TOKEN
        if not COURSE_OWNER_TOKEN:
            COURSE_OWNER_TOKEN = self.get_auth_token(
                creds=dict(ext_id='workspace_owner@example.org', password='workspace_owner', agreement_sign='signed'))
        self.workspace_owner_token = COURSE_OWNER_TOKEN
        return self.make_authenticated_request(method, path, headers, data,
                                               auth_token=self.workspace_owner_token)

    def make_authenticated_workspace_owner2_request(self, method='GET', path='/', headers=None, data=None):
        global COURSE_OWNER_TOKEN2
        if not COURSE_OWNER_TOKEN2:
            COURSE_OWNER_TOKEN2 = self.get_auth_token(
                creds=dict(ext_id='workspace_owner2@example.org', password='workspace_owner2', agreement_sign='signed'))
        self.workspace_owner_token2 = COURSE_OWNER_TOKEN2
        return self.make_authenticated_request(method, path, headers, data,
                                               auth_token=self.workspace_owner_token2)
