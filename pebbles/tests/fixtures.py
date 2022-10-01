# Test fixture methods to be called from app context so we can access the db
import importlib
import inspect

import yaml

import pebbles
from pebbles.models import (
    User, Workspace, WorkspaceUserAssociation, ApplicationTemplate, Application,
    Message, ApplicationSession, ApplicationSessionLog)
from pebbles.tests.base import db

from datetime import datetime


def fill_application_from_template(application, template):
    application.base_config = template.base_config.copy()
    application.attribute_limits = template.attribute_limits.copy()
    application.application_type = template.application_type


def primary_test_setup(namespace):
    """ Setup taken from FlaskApiTestCase to re-use it elsewhere as well.

        db.create_all is left to the caller.

        namespace is a descendant of unittest.testcase and we store things to
        it for easy access during tests.

        ToDo: store test vars inside a namespace on the parent object, e.g.
        namespace.vars to avoid cluttering.
    """
    namespace.known_admin_ext_id = "admin@example.org"
    namespace.known_admin_password = "admin"
    namespace.known_user_ext_id = "user@example.org"
    namespace.known_user_password = "user"
    namespace.known_user_2_ext_id = "user-2@example.org"
    namespace.known_user_2_password = "user-2"

    u1 = User(namespace.known_admin_ext_id, namespace.known_admin_password, is_admin=True)
    u2 = User(namespace.known_user_ext_id, namespace.known_user_password, is_admin=False)
    u3 = User("workspace_owner@example.org", "workspace_owner")
    u4 = User("workspace_owner2@example.org", "workspace_owner2")
    u5 = User("deleted_user1@example.org", "deleted_user1")
    u5.is_deleted = True
    u6 = User(namespace.known_user_2_ext_id, namespace.known_user_2_password, is_admin=False)
    u7 = User("expired_user@example.org", "expired_user")
    u7.expiry_ts = 10000000

    # Fix user IDs to be the same for all tests, in order to reuse the same token
    # for multiple tests
    u1.id = 'u1'
    u2.id = 'u2'
    namespace.known_admin_id = u1.id
    namespace.known_admin_id = u1.id
    namespace.known_user_id = u2.id
    u3.id = 'u3'
    u3.workspace_quota = 2
    u4.id = 'u4'
    u4.workspace_quota = 2
    u5.id = 'u5'
    u6.id = 'u6'
    u7.id = 'u7'

    namespace.known_admin_id = u1.id
    namespace.known_user_id = u2.id
    namespace.known_deleted_user_id = u5.id
    namespace.known_workspace_owner_id = u3.id
    namespace.known_workspace_owner_id_2 = u4.id
    namespace.known_expired_user_id = u7.id

    db.session.add(u1)
    db.session.add(u2)
    db.session.add(u3)
    db.session.add(u4)
    db.session.add(u5)
    db.session.add(u6)
    db.session.add(u7)

    ws0 = Workspace('System.default')
    ws0.id = 'ws0'
    ws0.user_associations.append(WorkspaceUserAssociation(user=u1, is_owner=True))
    ws0.user_associations.append(WorkspaceUserAssociation(user=u2))
    ws0.user_associations.append(WorkspaceUserAssociation(user=u3))
    ws0.user_associations.append(WorkspaceUserAssociation(user=u4))
    ws0.user_associations.append(WorkspaceUserAssociation(user=u5))
    ws0.user_associations.append(WorkspaceUserAssociation(user=u6))
    ws0.user_associations.append(WorkspaceUserAssociation(user=u7))
    db.session.add(ws0)

    ws1 = Workspace('Workspace1')
    ws1.id = 'ws1'
    ws1.cluster = 'dummy_cluster_1'
    ws1.application_quota = 6
    ws1.user_associations.append(WorkspaceUserAssociation(user=u2))
    ws1.user_associations.append(WorkspaceUserAssociation(user=u3, is_manager=True, is_owner=True))
    ws1.user_associations.append(WorkspaceUserAssociation(user=u4, is_manager=True))
    ws1.user_associations.append(WorkspaceUserAssociation(user=u6))
    db.session.add(ws1)

    ws2 = Workspace('Workspace2')
    ws2.id = 'ws2'
    ws2.cluster = 'dummy_cluster_1'
    ws2.user_associations.append(WorkspaceUserAssociation(user=u3))
    ws2.user_associations.append(WorkspaceUserAssociation(user=u4, is_manager=True, is_owner=True))
    db.session.add(ws2)

    ws3 = Workspace('Workspace3')
    ws3.id = 'ws3'
    ws3.cluster = 'dummy_cluster_2'
    ws3.user_associations.append(WorkspaceUserAssociation(user=u4, is_manager=True, is_owner=True))
    ws3.user_associations.append(WorkspaceUserAssociation(user=u2, is_banned=True))
    ws3.user_associations.append(WorkspaceUserAssociation(user=u3, is_banned=True))
    db.session.add(ws3)

    ws4 = Workspace('Workspace4')
    ws4.id = 'ws4'
    ws4.cluster = 'dummy_cluster_2'
    ws4.user_associations.append(WorkspaceUserAssociation(user=u1, is_manager=True, is_owner=True))
    db.session.add(ws4)

    # deleted workspace
    ws5 = Workspace('Workspace5')
    ws5.id = 'ws5'
    ws5.cluster = 'dummy_cluster_1'
    ws5.status = 'deleted'
    ws5.user_associations.append(WorkspaceUserAssociation(user=u2, is_manager=True, is_owner=True))
    db.session.add(ws5)

    ws6 = Workspace('Workspace1')
    ws6.id = 'ws6'
    ws6.description = 'workspace for memory limit testing'
    ws6.cluster = 'dummy_cluster_1'
    ws6.application_quota = 6
    ws6.memory_limit_gib = 10
    ws6.user_associations.append(WorkspaceUserAssociation(user=u6))
    db.session.add(ws6)

    namespace.known_workspace_id = ws1.id
    namespace.known_workspace_id_2 = ws2.id
    namespace.known_workspace_id_3 = ws3.id
    namespace.known_banned_workspace_join_id = ws3.join_code
    namespace.known_workspace_join_id = ws4.join_code
    namespace.system_default_workspace_id = ws0.id

    t1 = ApplicationTemplate()
    t1.name = 'TestTemplate'
    t1.application_type = 'generic'
    t1.base_config = {}
    db.session.add(t1)
    namespace.known_template_id_disabled = t1.id

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
    namespace.known_template_id = t2.id

    a0 = Application()
    a0.name = "Public application"
    a0.labels = ['label1', 'label with space', 'label2']
    a0.template_id = t2.id
    a0.workspace_id = ws0.id
    a0.is_enabled = True
    fill_application_from_template(a0, t2)
    db.session.add(a0)
    namespace.known_application_public = a0.id

    a1 = Application()
    a1.name = "TestApplication"
    a1.labels = ['label1', 'label with space', 'label2']
    a1.template_id = t2.id
    a1.workspace_id = ws1.id
    fill_application_from_template(a1, t2)
    db.session.add(a1)
    namespace.known_application_id_disabled = a1.id

    a2 = Application()
    a2.name = "EnabledTestApplication"
    a2.labels = ['label1', 'label with space', 'label2']
    a2.template_id = t2.id
    a2.workspace_id = ws1.id
    a2.is_enabled = True
    fill_application_from_template(a2, t2)
    db.session.add(a2)
    namespace.known_application_id = a2.id

    a3 = Application()
    a3.name = "EnabledTestApplicationClientIp"
    a3.labels = ['label1', 'label with space', 'label2']
    a3.template_id = t2.id
    a3.workspace_id = ws1.id
    a3.is_enabled = True
    a3.config = {'allow_update_client_connectivity': True}
    fill_application_from_template(a3, t2)
    db.session.add(a3)
    namespace.known_application_id_2 = a3.id

    a4 = Application()
    a4.name = "EnabledTestApplicationOtherWorkspace"
    a2.labels = ['label1', 'label with space', 'label2']
    a4.template_id = t2.id
    a4.workspace_id = ws2.id
    a4.is_enabled = True
    fill_application_from_template(a4, t2)
    db.session.add(a4)
    namespace.known_application_id_g2 = a4.id

    a5 = Application()
    a5.name = "DisabledTestApplicationOtherWorkspace"
    a5.labels = ['label1', 'label with space', 'label2']
    a5.template_id = t2.id
    a5.workspace_id = ws2.id
    fill_application_from_template(a5, t2)
    db.session.add(a5)
    namespace.known_application_id_disabled_2 = a5.id

    a6 = Application()
    a6.name = "TestArchivedApplication"
    a6.labels = ['label1', 'label with space', 'label2']
    a6.template_id = t2.id
    a6.workspace_id = ws2.id
    a6.status = Application.STATUS_ARCHIVED
    fill_application_from_template(a6, t2)
    db.session.add(a6)
    namespace.known_application_id_archived = a6.id

    a7 = Application()
    a7.name = "TestDeletedApplication"
    a7.labels = ['label1', 'label with space', 'label2']
    a7.template_id = t2.id
    a7.workspace_id = ws2.id
    a7.status = Application.STATUS_DELETED
    fill_application_from_template(a7, t2)
    db.session.add(a7)
    namespace.known_application_id_deleted = a7.id

    a8 = Application()
    a8.name = "EnabledTestApplication"
    a8.labels = ['label1', 'label with space', 'label2']
    a8.template_id = t2.id
    a8.workspace_id = ws1.id
    a8.is_enabled = True
    fill_application_from_template(a8, t2)
    db.session.add(a8)
    namespace.known_application_id_empty = a8.id

    a9 = Application()
    a9.name = "MemLimitTest 1"
    a9.labels = ['label1', 'label with space', 'label2']
    a9.template_id = t2.id
    a9.workspace_id = ws6.id
    a9.is_enabled = True
    fill_application_from_template(a9, t2)
    db.session.add(a9)
    namespace.known_application_id_mem_limit_test_1 = a9.id

    a10 = Application()
    a10.name = "MemLimitTest 2"
    a10.labels = ['label1', 'label with space', 'label2']
    a10.template_id = t2.id
    a10.workspace_id = ws6.id
    a10.is_enabled = True
    fill_application_from_template(a10, t2)
    db.session.add(a10)
    namespace.known_application_id_mem_limit_test_2 = a10.id

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
    namespace.known_application_id_mem_limit_test_3 = a11.id

    m1 = Message("First message", "First message message")
    namespace.known_message_id = m1.id
    db.session.add(m1)

    m2 = Message("Second message", "Second message message")
    namespace.known_message2_id = m2.id
    db.session.add(m2)

    i1 = ApplicationSession(
        Application.query.filter_by(id=a2.id).first(),
        User.query.filter_by(ext_id="user@example.org").first())
    i1.name = 'pb-i1'
    i1.state = ApplicationSession.STATE_RUNNING
    db.session.add(i1)
    namespace.known_application_session_id = i1.id

    i2 = ApplicationSession(
        Application.query.filter_by(id=a3.id).first(),
        User.query.filter_by(ext_id="user@example.org").first())
    i2.name = 'pb-i2'
    i2.state = ApplicationSession.STATE_RUNNING
    db.session.add(i2)
    db.session.add(ApplicationSessionLog(i2.id, 'info', 'provisioning', '1000.0', 'provisioning done'))
    namespace.known_application_session_id_2 = i2.id

    i3 = ApplicationSession(
        Application.query.filter_by(id=a3.id).first(),
        User.query.filter_by(ext_id="user@example.org").first())
    i3.name = 'pb-i3'
    i3.to_be_deleted = True
    i3.provisioned_at = datetime.strptime("2022-06-28T13:00:00", "%Y-%m-%dT%H:%M:%S")
    i3.deprovisioned_at = datetime.strptime("2022-06-28T14:00:00", "%Y-%m-%dT%H:%M:%S")
    i3.provisioning_config = dict(memory_gib=4)
    i3.state = ApplicationSession.STATE_DELETED
    db.session.add(i3)

    i4 = ApplicationSession(
        Application.query.filter_by(id=a3.id).first(),
        User.query.filter_by(ext_id="workspace_owner@example.org").first())
    i4.name = 'pb-i4'
    i4.state = ApplicationSession.STATE_FAILED
    db.session.add(i4)
    namespace.known_application_session_id_4 = i4.id

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
    i6.provisioned_at = datetime.strptime("2022-06-28T13:00:00", "%Y-%m-%dT%H:%M:%S")
    i6.deprovisioned_at = datetime.strptime("2022-06-28T16:00:00", "%Y-%m-%dT%H:%M:%S")
    i6.provisioning_config = dict(memory_gib=8)
    i6.state = ApplicationSession.STATE_DELETED
    db.session.add(i6)

    db.session.commit()


def load_yaml(yaml_data):
    """
    A function to load annotated yaml data into the database.
    Example can be found in devel_dataset.yaml
    """

    # callback function for constructing custom objects from yaml
    def model_object_constructor(loader, node):
        values = loader.construct_mapping(node, deep=True)
        # figure out class and use its constructor
        cls = getattr(
            importlib.import_module('pebbles.models'),
            node.tag[1:],
            None
        )
        # we could not find a matching class, return value dict
        if not cls:
            return values

        if 'id' in values:
            id = values.pop('id')
            obj = cls(**values)
            obj.id = id
        else:
            obj = cls(**values)

        return obj

    # wire custom construction for all pebbles.models classes
    for class_info in inspect.getmembers(pebbles.models, inspect.isclass):
        yaml.add_constructor('!' + class_info[0], model_object_constructor)

    data = yaml.unsafe_load(yaml_data)

    return data
