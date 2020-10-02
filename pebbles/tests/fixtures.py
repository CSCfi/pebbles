# Test fixture methods to be called from app context so we can access the db

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
    u3.environment_quota = 5
    u4.id = 'u4'
    u4.workspace_quota = 2
    u4.environment_quota = 5

    namespace.known_admin_id = u1.id
    namespace.known_user_id = u2.id
    namespace.known_workspace_owner_id = u3.id
    namespace.known_workspace_owner_id_2 = u4.id

    db.session.add(u1)
    db.session.add(u2)
    db.session.add(u3)
    db.session.add(u4)

    g1 = Workspace('Workspace1')
    g2 = Workspace('Workspace2')
    g3 = Workspace('Workspace3')
    g4 = Workspace('Workspace4')
    g5 = Workspace('System.default')

    g1.id = 'g1'
    g1u2 = WorkspaceUserAssociation(user=u2)
    g1u3 = WorkspaceUserAssociation(user=u3, manager=True, owner=True)
    g1u4 = WorkspaceUserAssociation(user=u4, manager=True)
    g1.users.append(g1u2)
    g1.users.append(g1u3)
    g1.users.append(g1u4)
    g2.id = 'g2'
    g2u3 = WorkspaceUserAssociation(user=u3)
    g2u4 = WorkspaceUserAssociation(user=u4, owner=True)
    g2.users.append(g2u3)
    g2.users.append(g2u4)
    g3.id = 'g3'
    g3u4 = WorkspaceUserAssociation(user=u4, owner=True)
    g3.users.append(g3u4)
    g3.banned_users.append(u2)
    g3.banned_users.append(u3)
    g4.id = 'g4'
    g4u1 = WorkspaceUserAssociation(user=u1, owner=True)
    g4.users.append(g4u1)
    g5.id = 'g5'
    g5u1 = WorkspaceUserAssociation(user=u1, owner=True)
    g5.users.append(g5u1)

    namespace.known_workspace_id = g1.id
    namespace.known_workspace_id_2 = g2.id
    namespace.known_workspace_id_3 = g3.id
    namespace.known_banned_workspace_join_id = g3.join_code
    namespace.known_workspace_join_id = g4.join_code
    namespace.system_default_workspace_id = g5.id
    db.session.add(g1)
    db.session.add(g2)
    db.session.add(g3)
    db.session.add(g4)
    db.session.add(g5)
    db.session.commit()

    t1 = EnvironmentTemplate()
    t1.name = 'TestTemplate'
    t1.cluster = 'OpenShiftLocalDriver'
    db.session.add(t1)
    namespace.known_template_id_disabled = t1.id

    t2 = EnvironmentTemplate()
    t2.name = 'EnabledTestTemplate'
    t2.cluster = 'OpenShiftRemoteDriver'
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
    b1.workspace_id = g1.id
    db.session.add(b1)
    namespace.known_environment_id_disabled = b1.id

    b2 = Environment()
    b2.name = "EnabledTestEnvironment"
    b2.template_id = t2.id
    b2.workspace_id = g1.id
    b2.is_enabled = True
    db.session.add(b2)
    namespace.known_environment_id = b2.id

    b3 = Environment()
    b3.name = "EnabledTestEnvironmentClientIp"
    b3.template_id = t2.id
    b3.workspace_id = g1.id
    b3.is_enabled = True
    b3.config = {'allow_update_client_connectivity': True}
    db.session.add(b3)
    namespace.known_environment_id_2 = b3.id

    b4 = Environment()
    b4.name = "EnabledTestEnvironmentOtherWorkspace"
    b4.template_id = t2.id
    b4.workspace_id = g2.id
    b4.is_enabled = True
    db.session.add(b4)
    namespace.known_environment_id_g2 = b4.id

    b5 = Environment()
    b5.name = "DisabledTestEnvironmentOtherWorkspace"
    b5.template_id = t2.id
    b5.workspace_id = g2.id
    db.session.add(b5)
    namespace.known_environment_id_disabled_2 = b5.id

    b6 = Environment()
    b6.name = "TestArchivedEnvironment"
    b6.template_id = t2.id
    b6.workspace_id = g2.id
    b6.current_status = 'archived'
    db.session.add(b6)

    b7 = Environment()
    b7.name = "TestDeletedEnvironment"
    b7.template_id = t2.id
    b7.workspace_id = g2.id
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
    db.session.commit()

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
