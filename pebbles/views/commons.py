import logging
import re
from functools import wraps

from flask import g, render_template, abort
from flask_httpauth import HTTPBasicAuth
from flask_restful import fields

from pebbles.drivers.provisioning import dummy_driver_config, kubernetes_driver_config
from pebbles.models import db, ActivationToken, User, Group, GroupUserAssociation, Plugin
from pebbles.server import app

user_fields = {
    'id': fields.String,
    'eppn': fields.String,
    'email_id': fields.String,
    'credits_quota': fields.Float,
    'group_quota': fields.Float,
    'blueprint_quota': fields.Float,
    'credits_spent': fields.Float,
    'is_active': fields.Boolean,
    'is_admin': fields.Boolean,
    'is_group_owner': fields.Boolean,
    'is_deleted': fields.Boolean,
    'is_blocked': fields.Boolean,
    'expiry_date': fields.DateTime,
}

group_fields = {
    'id': fields.String(attribute='id'),
    'name': fields.String,
    'join_code': fields.String,
    'description': fields.Raw,
    'config': fields.Raw,
    'user_config': fields.Raw,
    'owner_eppn': fields.String,
    'role': fields.String
}

auth = HTTPBasicAuth()
auth.authenticate_header = lambda: "Authentication Required"


@auth.verify_password
def verify_password(userid_or_token, password):
    g.user = User.verify_auth_token(userid_or_token, app.config['SECRET_KEY'])
    if not g.user:
        g.user = User.query.filter_by(eppn=userid_or_token).first()
        if not g.user:
            return False
        if not g.user.check_password(password):
            return False
    return True


def create_worker():
    return create_user('worker@pebbles', app.config['SECRET_KEY'], is_admin=True, email_id=None)


def create_user(eppn, password, is_admin=False, email_id=None):
    if User.query.filter_by(eppn=eppn).first():
        logging.info("user %s already exists" % eppn)
        return None

    user = User(eppn, password, is_admin=is_admin, email_id=email_id)
    if not is_admin:
        add_user_to_default_group(user)
    db.session.add(user)
    db.session.commit()
    return user


def register_plugins():
    plugin_data = [
        dict(
            id='1',
            name='DummyDriver',
            conf=dummy_driver_config.CONFIG
        ),
        dict(
            id='2',
            name='KubernetesLocalDriver',
            conf=kubernetes_driver_config.CONFIG
        ),
        dict(
            id='3',
            name='OpenShiftLocalDriver',
            conf=kubernetes_driver_config.CONFIG
        ),
        dict(
            id='4',
            name='OpenShiftRemoteDriver',
            conf=kubernetes_driver_config.CONFIG
        )
    ]

    for pd in plugin_data:
        app.logger.debug('processing plugin %s' % pd['name'])
        plugin = Plugin.query.filter_by(id=pd['id']).first()
        if not plugin:
            plugin = Plugin()
            plugin.id = pd['id']

        plugin.name = pd['name']
        plugin.schema = pd['conf']['schema']
        plugin.form = pd['conf']['form']
        plugin.model = pd['conf']['model']
        db.session.add(plugin)

    db.session.commit()


def update_email(eppn, email_id=None):
    user = User.query.filter_by(eppn=eppn).first()
    if email_id:
        user.email_id = email_id
    db.session.add(user)
    db.session.commit()
    return user


# both eppn and email are the same
def invite_user(eppn=None, password=None, is_admin=False, expiry_date=None):
    email_regex = r"(^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$)"
    if not re.match(email_regex, eppn):
        raise RuntimeError("Incorrect email")
    user = User.query.filter_by(eppn=eppn).first()
    if user:
        logging.warn("user %s already exists" % user.eppn)
        return None

    user = User(eppn=eppn, password=password, is_admin=is_admin, email_id=eppn, expiry_date=expiry_date)
    db.session.add(user)
    db.session.commit()

    token = ActivationToken(user)
    db.session.add(token)
    db.session.commit()

    if not app.dynamic_config['SKIP_TASK_QUEUE'] and not app.dynamic_config['MAIL_SUPPRESS_SEND']:
        logging.warning('email sending not implemented')
    else:
        logging.warn(
            "email sending suppressed in config: SKIP_TASK_QUEUE:%s MAIL_SUPPRESS_SEND:%s" %
            (app.dynamic_config['SKIP_TASK_QUEUE'], app.dynamic_config['MAIL_SUPPRESS_SEND'])
        )
        activation_url = '%s/#/activate/%s' % (app.config['BASE_URL'], token.token)
        content = render_template('invitation.txt', activation_link=activation_url)
        logging.warn(content)

    return user


def create_system_groups(admin):
    system_default_group = Group('System.default')
    group_admin_obj = GroupUserAssociation(group=system_default_group, user=admin, owner=True)
    system_default_group.users.append(group_admin_obj)
    db.session.add(system_default_group)
    db.session.commit()


def add_user_to_default_group(user):
    system_default_group = Group.query.filter_by(name='System.default').first()
    group_user_obj = GroupUserAssociation(group=system_default_group, user=user)
    system_default_group.users.append(group_user_obj)
    db.session.add(system_default_group)
    db.session.commit()


def requires_group_manager_or_admin(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not g.user.is_admin and not g.user.is_group_owner and not is_group_manager(g.user):
            abort(403)
        return f(*args, **kwargs)

    return decorated


def is_group_manager(user, group=None):
    if group:
        match = GroupUserAssociation.query.filter_by(user_id=user.id, group_id=group.id, manager=True).first()
    else:
        match = GroupUserAssociation.query.filter_by(user_id=user.id, manager=True).first()
    if match:
        return True
    return False
