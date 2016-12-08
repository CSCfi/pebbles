from flask.ext.restful import fields
from flask.ext.httpauth import HTTPBasicAuth
from flask import g, render_template, abort
import logging
from pouta_blueprints.models import db, ActivationToken, User, Group, GroupUserAssociation
from pouta_blueprints.server import app
from pouta_blueprints.tasks import send_mails
from functools import wraps


user_fields = {
    'id': fields.String,
    'email': fields.String,
    'credits_quota': fields.Float,
    'credits_spent': fields.Float,
    'is_active': fields.Boolean,
    'is_admin': fields.Boolean,
    'is_group_owner': fields.Boolean,
    'is_deleted': fields.Boolean,
    'is_blocked': fields.Boolean
}

group_fields = {
    'id': fields.String(attribute='id'),
    'name': fields.String,
    'join_code': fields.String,
    'description': fields.Raw,
    'config': fields.Raw,
    'user_config': fields.Raw,
    'owner_email': fields.String,
    'role': fields.String
}

auth = HTTPBasicAuth()
auth.authenticate_header = lambda: "Authentication Required"


@auth.verify_password
def verify_password(userid_or_token, password):
    g.user = User.verify_auth_token(userid_or_token, app.config['SECRET_KEY'])
    if not g.user:
        g.user = User.query.filter_by(email=userid_or_token).first()
        if not g.user:
            return False
        if not g.user.check_password(password):
            return False
    return True


def create_worker():
    return create_user('worker@pouta_blueprints', app.config['SECRET_KEY'], is_admin=True)


def create_user(email, password, is_admin=False):
    if User.query.filter_by(email=email).first():
        logging.info("user %s already exists" % email)
        return None

    user = User(email, password, is_admin=is_admin)
    if not is_admin:
        add_user_to_default_group(user)
    db.session.add(user)
    db.session.commit()
    return user


def invite_user(email, password=None, is_admin=False):
    user = User.query.filter_by(email=email).first()
    if user:
        logging.warn("user %s already exists" % email)
        return None

    user = User(email, password, is_admin)
    db.session.add(user)
    db.session.commit()

    token = ActivationToken(user)
    db.session.add(token)
    db.session.commit()

    if not app.dynamic_config['SKIP_TASK_QUEUE'] and not app.dynamic_config['MAIL_SUPPRESS_SEND']:
        send_mails.delay([(user.email, token.token)])
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
