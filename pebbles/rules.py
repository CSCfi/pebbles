import itertools

from sqlalchemy import or_, and_, select
from sqlalchemy.orm import load_only
from sqlalchemy.sql.expression import true

from pebbles.models import Application, ApplicationTemplate, ApplicationSession, User, WorkspaceMembership, Workspace, \
    db
from pebbles.views.commons import is_workspace_manager


def apply_rules_application_templates(user, args=None):
    q = ApplicationTemplate.query
    if not user.is_admin:
        query_exp = ApplicationTemplate.is_enabled == true()
        q = q.filter(query_exp)
    if args is not None and 'template_id' in args:
        q = q.filter_by(id=args.get('template_id'))

    return q


def apply_rules_applications(user, args=None):
    q = Application.query
    if not user.is_admin:
        workspace_user_objs = WorkspaceMembership.query.filter_by(
            user_id=user.id, is_manager=False, is_banned=False).all()
        allowed_workspace_ids = [workspace_user_obj.workspace.id for workspace_user_obj in workspace_user_objs]

        # Start building query expressions based on the condition that :
        # a workspace manager can see all of his applications and only enabled ones of other workspaces
        query_exp = Application.is_enabled == true()
        allowed_workspace_ids_exp = None
        if allowed_workspace_ids:
            allowed_workspace_ids_exp = Application.workspace_id.in_(allowed_workspace_ids)
        query_exp = and_(allowed_workspace_ids_exp, query_exp)

        manager_workspace_ids = get_manager_workspace_ids(user)
        manager_workspace_ids_exp = None
        if manager_workspace_ids:
            manager_workspace_ids_exp = Application.workspace_id.in_(manager_workspace_ids)
        query_exp = or_(query_exp, manager_workspace_ids_exp)
        q = q.filter(query_exp).filter_by(status='active')
    else:
        # admins can optionally also see archived and deleted applications
        if args is not None and 'show_all' in args and args.get('show_all'):
            q = q.filter(
                or_(
                    Application.status == Application.STATUS_ACTIVE,
                    Application.status == Application.STATUS_ARCHIVED,
                    Application.status == Application.STATUS_DELETED
                )
            )
        else:
            q = q.filter_by(status=Application.STATUS_ACTIVE)

    if args is not None:
        if 'application_id' in args:
            q = q.filter_by(id=args.get('application_id'))
        elif 'workspace_id' in args and args.get('workspace_id'):
            q = q.filter_by(workspace_id=args.get('workspace_id'))

    return q


def apply_rules_export_applications(user):
    q = Application.query
    if not user.is_admin:
        manager_workspace_ids = get_manager_workspace_ids(user)
        query_exp = None
        if manager_workspace_ids:
            query_exp = Application.workspace_id.in_(manager_workspace_ids)
        q = q.filter(query_exp)
    return q


def apply_rules_application_sessions(user, args=None):
    # basic query filter out the deleted application_sessions
    q = ApplicationSession.query.filter(ApplicationSession.state != ApplicationSession.STATE_DELETED)
    if not user.is_admin:
        # user's own application_sessions
        q1 = q.filter_by(user_id=user.id)
        if is_workspace_manager(user):
            # include also application_sessions of the applications of managed workspaces
            managed_application_ids = get_managed_application_ids(user)
            q2 = q.filter(ApplicationSession.application_id.in_(managed_application_ids))
            q = q1.union(q2)
        else:
            q = q1

    # additional filtering
    if args is not None:
        if 'application_session_id' in args:
            q = q.filter_by(id=args.get('application_session_id'))
    return q


def append_application_session_filter(appsession_select, user, args=None):
    res = appsession_select.where(ApplicationSession.state != ApplicationSession.STATE_DELETED)
    if args:
        if 'application_session_id' in args:
            res = res.where(ApplicationSession.id == args.get('application_session_id'))

    if user.is_admin:
        return res
    if is_workspace_manager(user):
        managed_application_ids = get_managed_application_ids(user)
        res = res.where(
            or_(
                ApplicationSession.application_id.in_(managed_application_ids),
                ApplicationSession.user_id == user.id
            )
        )
    else:
        res = res.where(ApplicationSession.user_id == user.id)

    return res


def apply_rules_workspace_memberships(user, user_id):
    # only admins can query someone else
    if not user.is_admin:
        user_id = user.id

    q = WorkspaceMembership.query \
        .filter_by(user_id=user_id) \
        .join(Workspace) \
        .filter_by(status='active')

    return q


# This should be refactored to return only list the user can access
def apply_filter_users():
    q = User.query
    q = q.filter_by(is_deleted=False)
    return q


###############################################
# all the helper functions for the rules go here
###############################################


def get_manager_workspace_ids(user):
    """Return the workspace ids for the user's managed workspaces"""
    # the result shall contain the owners of the workspaces too as they are managers by default
    workspace_manager_objs = WorkspaceMembership.query.filter_by(user_id=user.id, is_manager=True).all()
    manager_workspace_ids = [workspace_manager_obj.workspace.id for workspace_manager_obj in workspace_manager_objs]
    return manager_workspace_ids


def get_workspace_application_ids_for_application_sessions(user, only_managed=False):
    """Return the valid application ids based on user's workspaces to be used in application_sessions view"""
    workspace_user_query = WorkspaceMembership.query
    if only_managed:  # if we require only managed workspaces
        workspace_user_objs = workspace_user_query.filter_by(user_id=user.id, is_manager=True).all()
    else:  # get the normal user workspaces
        workspace_user_objs = workspace_user_query.filter_by(user_id=user.id).all()
    workspaces = [workspace_user_obj.workspace for workspace_user_obj in workspace_user_objs]
    # loading only id column rest will be deferred
    workspace_applications = [
        workspace.applications.options(load_only(Application.id)).all() for workspace in workspaces]
    # merge the list of lists into one list
    workspace_applications_flat = list(itertools.chain.from_iterable(workspace_applications))
    # Get the ids in a list
    workspace_applications_id = [application_item.id for application_item in workspace_applications_flat]
    return workspace_applications_id


def get_managed_application_ids(user):
    stmt = select(Application.id) \
        .join(WorkspaceMembership, WorkspaceMembership.workspace_id == Application.workspace_id) \
        .where(WorkspaceMembership.user_id == user.id, WorkspaceMembership.is_manager)
    res = db.session.scalars(stmt).all()
    return res
