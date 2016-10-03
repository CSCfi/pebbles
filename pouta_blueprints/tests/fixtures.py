# Test fixture methods to be called from app context so we can access the db

from pouta_blueprints.models import (
    User, Blueprint, Plugin,
    Notification, Instance)
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

    # Fix user IDs to be the same for all tests, in order to reuse the same token
    # for multiple tests
    u1.id = 'u1'
    u2.id = 'u2'
    namespace.known_admin_id = u1.id
    namespace.known_admin_id = u1.id
    namespace.known_user_id = u2.id
    db.session.add(u1)
    db.session.add(u2)

    p1 = Plugin()
    p1.name = "TestPlugin"
    namespace.known_plugin_id = p1.id
    db.session.add(p1)

    b1 = Blueprint()
    b1.name = "TestBlueprint"
    b1.plugin = p1.id
    db.session.add(b1)
    namespace.known_blueprint_id_disabled = b1.id

    b2 = Blueprint()
    b2.name = "EnabledTestBlueprint"
    b2.plugin = p1.id
    b2.is_enabled = True
    db.session.add(b2)
    namespace.known_blueprint_id = b2.id

    b3 = Blueprint()
    b3.name = "EnabledTestBlueprintClientIp"
    b3.plugin = p1.id
    b3.is_enabled = True
    b3.config = {'allow_update_client_connectivity': True}
    db.session.add(b3)
    namespace.known_blueprint_id_2 = b3.id

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
        User.query.filter_by(email="admin@example.org").first())
    db.session.add(i4)

    db.session.commit()
