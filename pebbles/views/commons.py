import logging
from functools import wraps

from flask import g, abort, current_app
from flask_httpauth import HTTPBasicAuth
from flask_restful import fields

from pebbles.models import db, User, Workspace, WorkspaceUserAssociation

user_fields = {
    'id': fields.String,
    'ext_id': fields.String,
    'email_id': fields.String,
    'pseudonym': fields.String,
    'workspace_quota': fields.Integer,
    'is_active': fields.Boolean,
    'is_admin': fields.Boolean,
    'is_deleted': fields.Boolean,
    'is_blocked': fields.Boolean,
    'joining_ts': fields.Integer,
    'expiry_ts': fields.Integer,
    'last_login_ts': fields.Integer,
}

workspace_user_association_fields = {
    'workspace_id': fields.String,
    'user_id': fields.String,
    'is_owner': fields.Boolean,
    'is_manager': fields.Boolean,
    'is_banned': fields.Boolean,
}

auth = HTTPBasicAuth()
auth.authenticate_header = lambda: "Authentication Required"

# Delimiter between optional identity domain/prefix and username(eppn/vppn/email)
EXT_ID_PREFIX_DELIMITER = '/'


@auth.verify_password
def verify_password(userid_or_token, password):
    g.user = User.verify_auth_token(userid_or_token, current_app.config['SECRET_KEY'])
    if not g.user:
        g.user = User.query.filter_by(ext_id=userid_or_token).first()
        if not g.user:
            return False
        if not g.user.check_password(password):
            return False
    return True


def create_worker():
    return create_user('worker@pebbles', current_app.config['SECRET_KEY'], is_admin=True, email_id=None)


def create_user(ext_id, password, is_admin=False, email_id=None, expiry_ts=None):
    if User.query.filter_by(ext_id=ext_id).first():
        logging.info("user %s already exists" % ext_id)
        return None

    user = User(ext_id, password, is_admin=is_admin, email_id=email_id)
    if not is_admin:
        add_user_to_default_workspace(user)
    if expiry_ts:
        user.expiry_ts = expiry_ts
    db.session.add(user)
    db.session.commit()
    return user


def update_email(ext_id, email_id=None):
    user = User.query.filter_by(ext_id=ext_id).first()
    if email_id:
        user.email_id = email_id
    db.session.add(user)
    db.session.commit()
    return user


def create_system_workspaces(admin):
    system_default_workspace = Workspace('System.default')
    workspace_admin_obj = WorkspaceUserAssociation(
        workspace=system_default_workspace, user=admin, is_owner=True, is_manager=True)
    system_default_workspace.user_associations.append(workspace_admin_obj)
    db.session.add(system_default_workspace)
    db.session.commit()


def add_user_to_default_workspace(user):
    system_default_workspace = Workspace.query.filter_by(name='System.default').first()
    workspace_user_obj = WorkspaceUserAssociation(workspace=system_default_workspace, user=user)
    system_default_workspace.user_associations.append(workspace_user_obj)
    db.session.add(system_default_workspace)
    db.session.commit()


def requires_workspace_manager_or_admin(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not g.user.is_admin and not g.user.is_workspace_owner and not g.user.is_workspace_manager:
            abort(403)
        return f(*args, **kwargs)

    return decorated


def is_workspace_manager(user, workspace=None):
    if workspace:
        # query specific active workspace
        match = WorkspaceUserAssociation.query \
            .filter_by(user_id=user.id, workspace_id=workspace.id, is_manager=True) \
            .join(Workspace) \
            .filter_by(status='active') \
            .first()
    else:
        # generic property can be obtained from User
        match = user.is_workspace_manager
    if match:
        return True
    return False
