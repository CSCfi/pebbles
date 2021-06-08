# Test fixture methods to be called from app context so we can access the db
import importlib
import inspect

import yaml

import pebbles
from pebbles.models import (
    User, Workspace, WorkspaceUserAssociation, EnvironmentTemplate, Environment,
    Message, Instance, InstanceLog)
from pebbles.tests.base import db


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

    u1 = User(namespace.known_admin_ext_id, namespace.known_admin_password, is_admin=True)
    u2 = User(namespace.known_user_ext_id, namespace.known_user_password, is_admin=False)
    u3 = User("workspace_owner@example.org", "workspace_owner")
    u4 = User("workspace_owner2@example.org", "workspace_owner2")
    u5 = User("deleted_user1@example.org", "deleted_user1")
    u5.is_deleted = True

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

    namespace.known_admin_id = u1.id
    namespace.known_user_id = u2.id
    namespace.known_deleted_user_id = u5.id
    namespace.known_workspace_owner_id = u3.id
    namespace.known_workspace_owner_id_2 = u4.id

    db.session.add(u1)
    db.session.add(u2)
    db.session.add(u3)
    db.session.add(u4)
    db.session.add(u5)

    ws0 = Workspace('System.default')
    ws0.id = 'ws0'
    ws0.user_associations.append(WorkspaceUserAssociation(user=u1, is_owner=True))
    ws0.user_associations.append(WorkspaceUserAssociation(user=u2))
    ws0.user_associations.append(WorkspaceUserAssociation(user=u3))
    ws0.user_associations.append(WorkspaceUserAssociation(user=u4))
    ws0.user_associations.append(WorkspaceUserAssociation(user=u5))
    db.session.add(ws0)

    ws1 = Workspace('Workspace1')
    ws1.id = 'ws1'
    ws1.cluster = 'dummy_cluster_1'
    ws1.environment_quota = 6
    ws1.user_associations.append(WorkspaceUserAssociation(user=u2))
    ws1.user_associations.append(WorkspaceUserAssociation(user=u3, is_manager=True, is_owner=True))
    ws1.user_associations.append(WorkspaceUserAssociation(user=u4, is_manager=True))
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

    namespace.known_workspace_id = ws1.id
    namespace.known_workspace_id_2 = ws2.id
    namespace.known_workspace_id_3 = ws3.id
    namespace.known_banned_workspace_join_id = ws3.join_code
    namespace.known_workspace_join_id = ws4.join_code
    namespace.system_default_workspace_id = ws0.id

    t1 = EnvironmentTemplate()
    t1.name = 'TestTemplate'
    t1.environment_type = 'generic'
    t1.base_config = {}
    db.session.add(t1)
    namespace.known_template_id_disabled = t1.id

    t2 = EnvironmentTemplate()
    t2.name = 'EnabledTestTemplate'
    t2.environment_type = 'generic'
    t2.base_config = {
        'labels': '["label1", "label with space", "label2"]',
        'cost_multiplier': '1.0',
        'maximum_lifetime': 3600,
        'memory_limit': '512m',
        'allow_update_client_connectivity': False
    }
    t2.allowed_attrs = [
        'maximum_lifetime',
        'cost_multiplier',
        'allow_update_client_connectivity'
    ]
    t2.is_enabled = True
    db.session.add(t2)
    namespace.known_template_id = t2.id

    e1 = Environment()
    e1.name = "TestEnvironment"
    e1.labels = ['label1', 'label with space', 'label2']
    e1.template_id = t2.id
    e1.workspace_id = ws1.id
    db.session.add(e1)
    namespace.known_environment_id_disabled = e1.id

    e2 = Environment()
    e2.name = "EnabledTestEnvironment"
    e2.labels = ['label1', 'label with space', 'label2']
    e2.template_id = t2.id
    e2.workspace_id = ws1.id
    e2.is_enabled = True
    db.session.add(e2)
    namespace.known_environment_id = e2.id

    e3 = Environment()
    e3.name = "EnabledTestEnvironmentClientIp"
    e3.labels = ['label1', 'label with space', 'label2']
    e3.template_id = t2.id
    e3.workspace_id = ws1.id
    e3.is_enabled = True
    e3.config = {'allow_update_client_connectivity': True}
    db.session.add(e3)
    namespace.known_environment_id_2 = e3.id

    e4 = Environment()
    e4.name = "EnabledTestEnvironmentOtherWorkspace"
    e2.labels = ['label1', 'label with space', 'label2']
    e4.template_id = t2.id
    e4.workspace_id = ws2.id
    e4.is_enabled = True
    db.session.add(e4)
    namespace.known_environment_id_g2 = e4.id

    e5 = Environment()
    e5.name = "DisabledTestEnvironmentOtherWorkspace"
    e5.labels = ['label1', 'label with space', 'label2']
    e5.template_id = t2.id
    e5.workspace_id = ws2.id
    db.session.add(e5)
    namespace.known_environment_id_disabled_2 = e5.id

    e6 = Environment()
    e6.name = "TestArchivedEnvironment"
    e6.labels = ['label1', 'label with space', 'label2']
    e6.template_id = t2.id
    e6.workspace_id = ws2.id
    e6.status = Environment.STATUS_ARCHIVED
    db.session.add(e6)
    namespace.known_environment_id_archived = e6.id

    e7 = Environment()
    e7.name = "TestDeletedEnvironment"
    e7.labels = ['label1', 'label with space', 'label2']
    e7.template_id = t2.id
    e7.workspace_id = ws2.id
    e7.status = Environment.STATUS_DELETED
    db.session.add(e7)
    namespace.known_environment_id_deleted = e7.id

    e8 = Environment()
    e8.name = "EnabledTestEnvironment"
    e8.labels = ['label1', 'label with space', 'label2']
    e8.template_id = t2.id
    e8.workspace_id = ws1.id
    e8.is_enabled = True
    db.session.add(e8)
    namespace.known_environment_id_empty = e8.id

    m1 = Message("First message", "First message message")
    namespace.known_message_id = m1.id
    db.session.add(m1)

    m2 = Message("Second message", "Second message message")
    namespace.known_message2_id = m2.id
    db.session.add(m2)

    i1 = Instance(
        Environment.query.filter_by(id=e2.id).first(),
        User.query.filter_by(ext_id="user@example.org").first())
    i1.name = 'pb-i1'
    i1.state = Instance.STATE_RUNNING
    db.session.add(i1)
    namespace.known_instance_id = i1.id

    i2 = Instance(
        Environment.query.filter_by(id=e3.id).first(),
        User.query.filter_by(ext_id="user@example.org").first())
    i2.name = 'pb-i2'
    i2.state = Instance.STATE_RUNNING
    db.session.add(i2)
    db.session.add(InstanceLog(i2.id, 'info', 'provisioning', '1000.0', 'provisioning done'))
    namespace.known_instance_id_2 = i2.id

    i3 = Instance(
        Environment.query.filter_by(id=e3.id).first(),
        User.query.filter_by(ext_id="user@example.org").first())
    i3.name = 'pb-i3'
    i3.to_be_deleted = True
    i3.state = Instance.STATE_DELETED
    db.session.add(i3)

    i4 = Instance(
        Environment.query.filter_by(id=e3.id).first(),
        User.query.filter_by(ext_id="workspace_owner@example.org").first())
    i4.name = 'pb-i4'
    i4.state = Instance.STATE_FAILED
    db.session.add(i4)
    namespace.known_instance_id_4 = i4.id

    i5 = Instance(
        Environment.query.filter_by(id=e4.id).first(),
        User.query.filter_by(ext_id="admin@example.org").first())
    i5.name = 'pb-i5'
    i5.state = Instance.STATE_RUNNING
    db.session.add(i5)

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
