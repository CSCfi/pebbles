# Test fixture methods to be called from app context so we can access the db

from pouta_blueprints.models import (
    User, Group, BlueprintTemplate, Blueprint,
    Plugin, Notification, Instance)
from pouta_blueprints.tests.base import db


def primary_test_setup(namespace):
    """ Setup taken from FlaskApiTestCase to re-use it elsewhere as well.

        db.create_all is left to the caller.

        namespace is a descendant of unittest.testcase and we store things to
        it for easy access during tests.

        ToDo: store test vars inside a namespace on the parent object, e.g.
        namespace.vars to avoid cluttering.
    """
    namespace.known_admin_email = "admin@example.org"
    namespace.known_admin_password = "admin"
    namespace.known_user_email = "user@example.org"
    namespace.known_user_password = "user"

    u1 = User(namespace.known_admin_email, namespace.known_admin_password, is_admin=True)
    u2 = User(namespace.known_user_email, namespace.known_user_password, is_admin=False)
    u3 = User("group_owner@example.org", "group_owner")
    u4 = User("group_owner2@example.org", "group_owner2")

    # Fix user IDs to be the same for all tests, in order to reuse the same token
    # for multiple tests
    u1.id = 'u1'
    u2.id = 'u2'
    namespace.known_admin_id = u1.id
    namespace.known_admin_id = u1.id
    namespace.known_user_id = u2.id
    u3.id = 'u3'
    u3.is_group_owner = True
    u4.id = 'u4'
    u4.is_group_owner = True

    namespace.known_admin_id = u1.id
    namespace.known_user_id = u2.id
    namespace.known_group_owner_id = u3.id
    namespace.known_group_owner_id_2 = u4.id

    db.session.add(u1)
    db.session.add(u2)
    db.session.add(u3)
    db.session.add(u4)

    g1 = Group('Group1')
    g2 = Group('Group2')
    g3 = Group('Group3')
    g4 = Group('Group4')
    g5 = Group('System.default')

    g1.id = 'g1'
    g1.owner_id = u3.id
    g1.users.append(u2)
    g1.managers.append(u3)  # The owner is always a manager
    g1.managers.append(u4)  # Add extra manager
    g2.id = 'g2'
    g2.owner_id = u4.id
    g2.users.append(u3)
    g3.id = 'g3'
    g3.owner_id = u4.id
    g3.banned_users.append(u2)
    g3.banned_users.append(u3)

    namespace.known_group_id = g1.id
    namespace.known_group_id_2 = g2.id
    namespace.known_group_id_3 = g3.id
    namespace.known_banned_group_join_id = g3.join_code
    namespace.known_group_join_id = g4.join_code
    namespace.system_default_group_id = g5.id
    db.session.add(g1)
    db.session.add(g2)
    db.session.add(g3)
    db.session.add(g4)
    db.session.add(g5)
    db.session.commit()

    p1 = Plugin()
    p1.name = "TestPlugin"
    p1.schema = {
        "type": "object",
        "title": "Comment",
        "description": "Description",
        "properties": {
            "name": {
                "type": "string"
            },
            "description": {
                "type": "string"
            },
            "maximum_lifetime": {
                "type": "string"
            }
        }
    }
    namespace.known_plugin_id = p1.id
    db.session.add(p1)

    t1 = BlueprintTemplate()
    t1.name = 'TestTemplate'
    t1.plugin = p1.id
    db.session.add(t1)
    namespace.known_template_id_disabled = t1.id

    t2 = BlueprintTemplate()
    t2.name = 'EnabledTestTemplate'
    t2.plugin = p1.id
    t2.config = {
        'cost_multiplier': '1.0',
        'maximum_lifetime': '1h',
        'memory_limit': '512m',
        'allow_update_client_connectivity': False
    }
    t2.allowed_attrs = [
        'maximum_lifetime',
        'cost_multiplier',
        'preallocated_credits',
        'allow_update_client_connectivity'
    ]
    t2.is_enabled = True
    db.session.add(t2)
    namespace.known_template_id = t2.id

    b1 = Blueprint()
    b1.name = "TestBlueprint"
    b1.template_id = t2.id
    b1.group_id = g1.id
    db.session.add(b1)
    namespace.known_blueprint_id_disabled = b1.id

    b2 = Blueprint()
    b2.name = "EnabledTestBlueprint"
    b2.template_id = t2.id
    b2.group_id = g1.id
    b2.is_enabled = True
    db.session.add(b2)
    namespace.known_blueprint_id = b2.id

    b3 = Blueprint()
    b3.name = "EnabledTestBlueprintClientIp"
    b3.template_id = t2.id
    b3.group_id = g1.id
    b3.is_enabled = True
    b3.config = {'allow_update_client_connectivity': True}
    db.session.add(b3)
    namespace.known_blueprint_id_2 = b3.id

    b4 = Blueprint()
    b4.name = "EnabledTestBlueprintOtherGroup"
    b4.template_id = t2.id
    b4.group_id = g2.id
    b4.is_enabled = True
    db.session.add(b4)
    namespace.known_blueprint_id_g2 = b4.id

    b5 = Blueprint()
    b5.name = "DisabledTestBlueprintOtherGroup"
    b5.template_id = t2.id
    b5.group_id = g2.id
    db.session.add(b5)
    namespace.known_blueprint_id_disabled_2 = b5.id

    n1 = Notification()
    n1.subject = "First notification"
    n1.message = "First notification message"
    namespace.known_notification_id = n1.id
    db.session.add(n1)

    n2 = Notification()
    n2.subject = "Second notification"
    n2.message = "Second notification message"
    namespace.known_notification2_id = n2.id
    db.session.add(n2)
    db.session.commit()

    i1 = Instance(
        Blueprint.query.filter_by(id=b2.id).first(),
        User.query.filter_by(email="user@example.org").first())
    db.session.add(i1)
    namespace.known_instance_id = i1.id

    i2 = Instance(
        Blueprint.query.filter_by(id=b3.id).first(),
        User.query.filter_by(email="user@example.org").first())
    db.session.add(i2)
    namespace.known_instance_id_2 = i2.id

    i3 = Instance(
        Blueprint.query.filter_by(id=b3.id).first(),
        User.query.filter_by(email="user@example.org").first())
    db.session.add(i3)
    i3.state = Instance.STATE_DELETED

    i4 = Instance(
        Blueprint.query.filter_by(id=b3.id).first(),
        User.query.filter_by(email="group_owner@example.org").first())
    db.session.add(i4)

    i5 = Instance(
        Blueprint.query.filter_by(id=b4.id).first(),
        User.query.filter_by(email="admin@example.org").first())
    db.session.add(i5)
    db.session.commit()
