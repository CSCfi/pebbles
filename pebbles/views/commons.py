import logging
from functools import wraps

from flask import g, abort, current_app
from flask_httpauth import HTTPBasicAuth

from pebbles.models import db, User, Workspace, WorkspaceMembership

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


def create_user(ext_id, password, is_admin=False, email_id=None, expiry_ts=None, annotations=None):
    if User.query.filter_by(ext_id=ext_id).first():
        logging.info("user %s already exists" % ext_id)
        return None

    user = User(ext_id, password, is_admin=is_admin, email_id=email_id)
    if annotations:
        user.annotations = annotations
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
    workspace_admin_obj = WorkspaceMembership(
        workspace=system_default_workspace, user=admin, is_owner=True, is_manager=True)
    system_default_workspace.memberships.append(workspace_admin_obj)
    db.session.add(system_default_workspace)
    db.session.commit()


def can_user_join_workspace(user, ws):
    if not user.taints:
        return True
    tolerations = ws.membership_join_policy.get('tolerations', [])
    return set(user.taints) <= set(tolerations)


def add_user_to_default_workspace(user):
    system_default_workspace = Workspace.query.filter_by(name='System.default').first()
    if not can_user_join_workspace(user, system_default_workspace):
        logging.info('User %s could not be added to System.default workspace', user.ext_id)
        return
    workspace_user_obj = WorkspaceMembership(workspace=system_default_workspace, user=user)
    system_default_workspace.memberships.append(workspace_user_obj)
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
        if workspace.status != Workspace.STATUS_ACTIVE:
            return False
        manager_cache = g.setdefault('manager_cache', dict())
        key = '%s:%s' % (user.id, workspace.id)
        if key not in manager_cache.keys():
            logging.debug('manager cache: adding key %s' % key)
            manager_cache[key] = user.id in (wm.user_id for wm in workspace.memberships if wm.is_manager)
        return manager_cache.get(key)
    else:
        # generic property can be obtained from User
        return user.is_workspace_manager


def is_workspace_owner(user, workspace=None):
    if workspace:
        if workspace.status != Workspace.STATUS_ACTIVE:
            return False

        owner_cache = g.setdefault('owner_cache', dict())
        key = '%s:%s' % (user.id, workspace.id)
        if key not in owner_cache.keys():
            logging.debug('owner cache: adding key %s' % key)
            owner_cache[key] = user.id in (wm.user_id for wm in workspace.memberships if wm.is_owner)
        return owner_cache.get(key)
    else:
        # generic property can be obtained from User
        return user.is_workspace_owner
