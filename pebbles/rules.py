import itertools

from sqlalchemy import or_, and_
from sqlalchemy.orm import load_only
from sqlalchemy.sql.expression import true

from pebbles.models import Environment, EnvironmentTemplate, EnvironmentSession, User, WorkspaceUserAssociation
from pebbles.views.commons import is_workspace_manager


def apply_rules_environment_templates(user, args=None):
    q = EnvironmentTemplate.query
    if not user.is_admin:
        query_exp = EnvironmentTemplate.is_enabled == true()
        q = q.filter(query_exp)
    if args is not None and 'template_id' in args:
        q = q.filter_by(id=args.get('template_id'))

    return q


def apply_rules_environments(user, args=None):
    q = Environment.query
    if not user.is_admin:
        workspace_user_objs = WorkspaceUserAssociation.query.filter_by(
            user_id=user.id, is_manager=False, is_banned=False).all()
        allowed_workspace_ids = [workspace_user_obj.workspace.id for workspace_user_obj in workspace_user_objs]

        # Start building query expressions based on the condition that :
        # a workspace manager can see all of his environments and only enabled ones of other workspaces
        query_exp = Environment.is_enabled == true()
        allowed_workspace_ids_exp = None
        if allowed_workspace_ids:
            allowed_workspace_ids_exp = Environment.workspace_id.in_(allowed_workspace_ids)
        query_exp = and_(allowed_workspace_ids_exp, query_exp)

        manager_workspace_ids = get_manager_workspace_ids(user)
        manager_workspace_ids_exp = None
        if manager_workspace_ids:
            manager_workspace_ids_exp = Environment.workspace_id.in_(manager_workspace_ids)
        query_exp = or_(query_exp, manager_workspace_ids_exp)
        q = q.filter(query_exp).filter_by(status='active')
    else:
        # admins can optionally also see archived and deleted environments
        if args is not None and 'show_all' in args and args.get('show_all'):
            q = q.filter(
                or_(
                    Environment.status == Environment.STATUS_ACTIVE,
                    Environment.status == Environment.STATUS_ARCHIVED,
                    Environment.status == Environment.STATUS_DELETED
                )
            )
        else:
            q = q.filter_by(status=Environment.STATUS_ACTIVE)

    if args is not None:
        if 'environment_id' in args:
            q = q.filter_by(id=args.get('environment_id'))
        elif 'workspace_id' in args and args.get('workspace_id'):
            q = q.filter_by(workspace_id=args.get('workspace_id'))

    return q


def apply_rules_export_environments(user):
    q = Environment.query
    if not user.is_admin:
        manager_workspace_ids = get_manager_workspace_ids(user)
        query_exp = None
        if manager_workspace_ids:
            query_exp = Environment.workspace_id.in_(manager_workspace_ids)
        q = q.filter(query_exp)
    return q


def apply_rules_environment_sessions(user, args=None):
    # basic query filter out the deleted environment_sessions
    q = EnvironmentSession.query.filter(EnvironmentSession.state != EnvironmentSession.STATE_DELETED)
    if not user.is_admin:
        # user's own environment_sessions
        q1 = q.filter_by(user_id=user.id)
        if is_workspace_manager(user):
            # include also environment_sessions of the environments of managed workspaces
            workspace_environments_id = get_workspace_environment_ids_for_environment_sessions(user, only_managed=True)
            q2 = q.filter(EnvironmentSession.environment_id.in_(workspace_environments_id))
            q = q1.union(q2)
        else:
            q = q1

    # additional filtering
    if args is not None:
        if 'environment_session_id' in args:
            q = q.filter_by(id=args.get('environment_session_id'))
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
    workspace_manager_objs = WorkspaceUserAssociation.query.filter_by(user_id=user.id, is_manager=True).all()
    manager_workspace_ids = [workspace_manager_obj.workspace.id for workspace_manager_obj in workspace_manager_objs]
    return manager_workspace_ids


def get_workspace_environment_ids_for_environment_sessions(user, only_managed=False):
    """Return the valid environment ids based on user's workspaces to be used in environment_sessions view"""
    workspace_user_query = WorkspaceUserAssociation.query
    if only_managed:  # if we require only managed workspaces
        workspace_user_objs = workspace_user_query.filter_by(user_id=user.id, is_manager=True).all()
    else:  # get the normal user workspaces
        workspace_user_objs = workspace_user_query.filter_by(user_id=user.id).all()
    workspaces = [workspace_user_obj.workspace for workspace_user_obj in workspace_user_objs]
    # loading only id column rest will be deferred
    workspace_environments = [workspace.environments.options(load_only("id")).all() for workspace in workspaces]
    # merge the list of lists into one list
    workspace_environments_flat = list(itertools.chain.from_iterable(workspace_environments))
    # Get the ids in a list
    workspace_environments_id = [environment_item.id for environment_item in workspace_environments_flat]
    return workspace_environments_id


def is_user_owner_of_workspace(user, workspace):
    return user.id in (wua.user_id for wua in workspace.user_associations if wua.is_owner)


def is_user_manager_in_workspace(user, workspace):
    return user.id in (wua.user_id for wua in workspace.user_associations if wua.is_manager)
