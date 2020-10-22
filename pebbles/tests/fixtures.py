# Test fixture methods to be called from app context so we can access the db
import importlib
import inspect

import yaml

import pebbles
from pebbles.models import (
    User, Workspace, WorkspaceUserAssociation, EnvironmentTemplate, Environment,
    Message, Instance)
from pebbles.tests.base import db


def primary_test_setup(namespace):
    """ Setup taken from FlaskApiTestCase to re-use it elsewhere as well.

        db.create_all is left to the caller.

        namespace is a descendant of unittest.testcase and we store things to
        it for easy access during tests.

        ToDo: store test vars inside a namespace on the parent object, e.g.
        namespace.vars to avoid cluttering.
    """
    namespace.known_admin_eppn = "admin@example.org"
    namespace.known_admin_password = "admin"
    namespace.known_user_eppn = "user@example.org"
    namespace.known_user_password = "user"

    u1 = User(namespace.known_admin_eppn, namespace.known_admin_password, is_admin=True)
    u2 = User(namespace.known_user_eppn, namespace.known_user_password, is_admin=False)
    u3 = User("workspace_owner@example.org", "workspace_owner")
    u4 = User("workspace_owner2@example.org", "workspace_owner2")

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

    namespace.known_admin_id = u1.id
    namespace.known_user_id = u2.id
    namespace.known_workspace_owner_id = u3.id
    namespace.known_workspace_owner_id_2 = u4.id

    db.session.add(u1)
    db.session.add(u2)
    db.session.add(u3)
    db.session.add(u4)

    ws0 = Workspace('System.default')
    ws0.id = 'ws0'
    ws0.users.append(WorkspaceUserAssociation(user=u1, owner=True))
    db.session.add(ws0)

    ws1 = Workspace('Workspace1')
    ws1.id = 'ws1'
    ws1.environment_quota = 5
    ws1.users.append(WorkspaceUserAssociation(user=u2))
    ws1.users.append(WorkspaceUserAssociation(user=u3, manager=True, owner=True))
    ws1.users.append(WorkspaceUserAssociation(user=u4, manager=True))
    db.session.add(ws1)

    ws2 = Workspace('Workspace2')
    ws2.id = 'ws2'
    ws2.users.append(WorkspaceUserAssociation(user=u3))
    ws2.users.append(WorkspaceUserAssociation(user=u4, owner=True))
    db.session.add(ws2)

    ws3 = Workspace('Workspace3')
    ws3.id = 'ws3'
    ws3.users.append(WorkspaceUserAssociation(user=u4, owner=True))
    ws3.banned_users.append(u2)
    ws3.banned_users.append(u3)
    db.session.add(ws3)

    ws4 = Workspace('Workspace4')
    ws4.id = 'ws4'
    ws4.users.append(WorkspaceUserAssociation(user=u1, owner=True))
    db.session.add(ws4)

    namespace.known_workspace_id = ws1.id
    namespace.known_workspace_id_2 = ws2.id
    namespace.known_workspace_id_3 = ws3.id
    namespace.known_banned_workspace_join_id = ws3.join_code
    namespace.known_workspace_join_id = ws4.join_code
    namespace.system_default_workspace_id = ws0.id

    t1 = EnvironmentTemplate()
    t1.name = 'TestTemplate'
    t1.cluster = 'dummy_cluster_1'
    db.session.add(t1)
    namespace.known_template_id_disabled = t1.id

    t2 = EnvironmentTemplate()
    t2.name = 'EnabledTestTemplate'
    t2.cluster = 'dummy_cluster_2'
    t2.config = {
        'labels': 'label1, label with space, label2',
        'cost_multiplier': '1.0',
        'maximum_lifetime': '1h',
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

    b1 = Environment()
    b1.name = "TestEnvironment"
    b1.template_id = t2.id
    b1.workspace_id = ws1.id
    db.session.add(b1)
    namespace.known_environment_id_disabled = b1.id

    b2 = Environment()
    b2.name = "EnabledTestEnvironment"
    b2.template_id = t2.id
    b2.workspace_id = ws1.id
    b2.is_enabled = True
    db.session.add(b2)
    namespace.known_environment_id = b2.id

    b3 = Environment()
    b3.name = "EnabledTestEnvironmentClientIp"
    b3.template_id = t2.id
    b3.workspace_id = ws1.id
    b3.is_enabled = True
    b3.config = {'allow_update_client_connectivity': True}
    db.session.add(b3)
    namespace.known_environment_id_2 = b3.id

    b4 = Environment()
    b4.name = "EnabledTestEnvironmentOtherWorkspace"
    b4.template_id = t2.id
    b4.workspace_id = ws2.id
    b4.is_enabled = True
    db.session.add(b4)
    namespace.known_environment_id_g2 = b4.id

    b5 = Environment()
    b5.name = "DisabledTestEnvironmentOtherWorkspace"
    b5.template_id = t2.id
    b5.workspace_id = ws2.id
    db.session.add(b5)
    namespace.known_environment_id_disabled_2 = b5.id

    b6 = Environment()
    b6.name = "TestArchivedEnvironment"
    b6.template_id = t2.id
    b6.workspace_id = ws2.id
    b6.current_status = 'archived'
    db.session.add(b6)

    b7 = Environment()
    b7.name = "TestDeletedEnvironment"
    b7.template_id = t2.id
    b7.workspace_id = ws2.id
    b7.current_status = 'deleted'
    db.session.add(b7)

    n1 = Message()
    n1.subject = "First message"
    n1.message = "First message message"
    namespace.known_message_id = n1.id
    db.session.add(n1)

    n2 = Message()
    n2.subject = "Second message"
    n2.message = "Second message message"
    namespace.known_message2_id = n2.id
    db.session.add(n2)

    i1 = Instance(
        Environment.query.filter_by(id=b2.id).first(),
        User.query.filter_by(eppn="user@example.org").first())
    db.session.add(i1)
    namespace.known_instance_id = i1.id

    i2 = Instance(
        Environment.query.filter_by(id=b3.id).first(),
        User.query.filter_by(eppn="user@example.org").first())
    db.session.add(i2)
    namespace.known_instance_id_2 = i2.id

    i3 = Instance(
        Environment.query.filter_by(id=b3.id).first(),
        User.query.filter_by(eppn="user@example.org").first())
    db.session.add(i3)
    i3.state = Instance.STATE_DELETED

    i4 = Instance(
        Environment.query.filter_by(id=b3.id).first(),
        User.query.filter_by(eppn="workspace_owner@example.org").first())
    db.session.add(i4)

    i5 = Instance(
        Environment.query.filter_by(id=b4.id).first(),
        User.query.filter_by(eppn="admin@example.org").first())
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
