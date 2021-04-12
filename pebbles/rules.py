import itertools

from sqlalchemy import or_, and_
from sqlalchemy.orm import load_only
from sqlalchemy.sql.expression import true

from pebbles.models import Environment, EnvironmentTemplate, Instance, User, WorkspaceUserAssociation
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
        q = q.filter(query_exp).filter_by(current_status='active')
    else:
        if args is not None and 'show_all' in args and args.get('show_all'):
            q = q.filter(
                or_(
                    Environment.current_status == 'active',
                    Environment.current_status == 'archived',
                    Environment.current_status == 'deleted'
                )
            )
        else:
            q = q.filter_by(current_status='active')

    if args is not None and 'environment_id' in args:
        q = q.filter_by(id=args.get('environment_id'))

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


def apply_rules_instances(user, args=None):
    q = Instance.query
    if not user.is_admin:
        q1 = q.filter_by(user_id=user.id)
        if is_workspace_manager(user):  # show only the instances of the environments which the workspace manager holds
            workspace_environments_id = get_workspace_environment_ids_for_instances(user, only_managed=True)
            q2 = q.filter(Instance.environment_id.in_(workspace_environments_id))
            q = q1.union(q2)
        else:
            q = q1
    if args is None or not args.get('show_deleted'):
        q = q.filter(Instance.state != Instance.STATE_DELETED)
    if args is not None:
        if 'instance_id' in args:
            q = q.filter_by(id=args.get('instance_id'))
        if args.get('show_only_mine'):
            q = q.filter_by(user_id=user.id)
        if 'offset' in args:
            q = q.offset(args.get('offset'))
        if 'limit' in args:
            q = q.limit(args.get('limit'))
    return q


def apply_rules_users(args=None):
    if args is None:
        args = {}

    q = User.query

    if 'filter_str' in args and args.filter_str:
        filter_str = str.lower(args.filter_str)
        q = q.filter(User._eppn.contains(filter_str))

    if 'user_type' in args and args.user_type:
        user_type = args.get('user_type')
        if user_type == 'Admins':
            q = q.filter_by(is_admin=True)
        elif user_type == 'Workspace Owners':
            q = q.filter_by(is_workspace_owner=True)
        elif user_type == 'Active':
            q = q.filter_by(is_active=True)
        elif user_type == 'Inactive':
            q = q.filter_by(is_active=False)
        elif user_type == 'Blocked':
            q = q.filter_by(is_blocked=True)

    page = args.get('page', None)
    page_size = args.get('page_size', None)
    if page and page_size:
        q = q.offset(page * page_size)
        q = q.limit(page_size)

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


def get_workspace_environment_ids_for_instances(user, only_managed=False):
    """Return the valid environment ids based on user's workspaces to be used in instances view"""
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


def is_user_manager_in_workspace(user, workspace):
    return user.id in (wua.user_id for wua in workspace.user_associations if wua.is_manager)
