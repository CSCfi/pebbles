import itertools

from sqlalchemy import or_, select, false, func
from sqlalchemy.orm import load_only
from sqlalchemy.sql.expression import true

from pebbles.models import Application, ApplicationTemplate, ApplicationSession, User, WorkspaceMembership, Workspace, \
    CustomImage


def apply_rules_application_templates(user, args=None):
    q = ApplicationTemplate.query
    if not user.is_admin:
        query_exp = ApplicationTemplate.is_enabled == true()
        q = q.filter(query_exp)
    if args is not None and 'template_id' in args:
        q = q.filter_by(id=args.get('template_id'))

    return q


def generate_application_query(user, args):
    # handle admins separately
    if user.is_admin:
        s = select(Application).join(Application.workspace)
        # admins can query deleted applications
        if not args.get('show_all'):
            s = s.where(Application.status == Application.STATUS_ACTIVE)
    else:
        s = select(Application, Workspace, WorkspaceMembership) \
            .join(Workspace, Workspace.id == Application.workspace_id) \
            .join(WorkspaceMembership, WorkspaceMembership.workspace_id == Application.workspace_id)
        s = s.where(WorkspaceMembership.user_id == user.id)
        s = s.where(WorkspaceMembership.is_banned == false())
        s = s.where(Application.status == Application.STATUS_ACTIVE)
        # owner/managers can see draft applications (is_enabled==False)
        s = s.where(
            or_(
                Application.is_enabled == true(),
                WorkspaceMembership.is_manager == true()
            )
        )

    if args and args.get('workspace_id'):
        s = s.where(Application.workspace_id == args.get('workspace_id'))
    if args and args.get('application_id'):
        s = s.where(Application.id == args.get('application_id'))

    return s


def generate_application_session_query(user, args=None):
    """Generates a query to list application_sessions, applications and users joined on the same row"""
    s = select(ApplicationSession, Application, User).join(Application).join(User)
    s = s.where(ApplicationSession.state != ApplicationSession.STATE_DELETED)
    if args and args.get('application_session_id'):
        s = s.where(ApplicationSession.id == args.get('application_session_id'))

    if not user.is_admin:
        # For non-admins, list union of application sessions that
        # - belong to applications that are managed by the user
        # - are owned by the user
        # Use a subquery for finding managed applications
        managed_application_ids = select(Application.id) \
            .join(WorkspaceMembership, WorkspaceMembership.workspace_id == Application.workspace_id) \
            .where(WorkspaceMembership.user_id == user.id) \
            .where(WorkspaceMembership.is_manager)
        s = s.where(
            or_(
                ApplicationSession.application_id.in_(managed_application_ids),
                ApplicationSession.user_id == user.id
            )
        )

    if args and args.get('limit'):
        # prioritize to_be_deleted
        s = s.order_by(ApplicationSession.to_be_deleted == false())
        # then sessions that are not in static states (failed, running, deleted)
        s = s.order_by(
            or_(
                ApplicationSession.state == ApplicationSession.STATE_FAILED,
                ApplicationSession.state == ApplicationSession.STATE_RUNNING,
                ApplicationSession.state == ApplicationSession.STATE_DELETED,
            )
        )
        # finally random order as the last criteria
        s = s.order_by(func.random())
        s = s.limit(int(args.get('limit')))

    return s


def generate_custom_image_query(user, args=None):
    if user.is_admin:
        s = select(CustomImage)
        s = s.join(Workspace, Workspace.id == CustomImage.workspace_id)
        s = s.where(Workspace.status != Workspace.STATUS_DELETED)
    else:
        s = select(CustomImage)
        s = s.join(Workspace, Workspace.id == CustomImage.workspace_id)
        s = s.join(WorkspaceMembership, WorkspaceMembership.workspace_id == Workspace.id)
        s = s.where(WorkspaceMembership.user_id == user.id)
        s = s.where(WorkspaceMembership.is_banned == false())
        s = s.where(WorkspaceMembership.is_manager == true())
        s = s.where(Workspace.status != Workspace.STATUS_DELETED)

    s = s.where(CustomImage.state != CustomImage.STATE_DELETED)

    if args and args.get('custom_image_id'):
        s = s.where(CustomImage.id == args.get('custom_image_id'))

    if args and args.get('workspace_id'):
        s = s.where(Workspace.id == args.get('workspace_id'))

    if args and bool(args.get('unfinished') in ('1', 'true', 'True')):
        s = s.where(
            CustomImage.state.in_(
                [CustomImage.STATE_NEW, CustomImage.STATE_BUILDING]) | CustomImage.to_be_deleted == true()
        )

    if args and args.get('limit'):
        # prioritize to_be_deleted
        s = s.order_by(CustomImage.to_be_deleted == false())
        # prioritize non-terminal states for worker
        #  building > new > terminal states
        # last criteria: oldest first for fair queuing
        s = s.order_by(CustomImage.state != CustomImage.STATE_BUILDING)
        s = s.order_by(
            or_(
                CustomImage.state == CustomImage.STATE_COMPLETED,
                CustomImage.state == CustomImage.STATE_FAILED,
                CustomImage.state == CustomImage.STATE_DELETED,
            )
        )
        s = s.limit(int(args.get('limit')))

    s = s.order_by(CustomImage.created_at)
    return s


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
    manager_workspace_ids = [workspace_manager_obj.workspace_id for workspace_manager_obj in workspace_manager_objs]
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
        workspace.applications.options(load_only(Application.id)).all()
        for workspace in workspaces
    ]
    # merge the list of lists into one list
    workspace_applications_flat = list(itertools.chain.from_iterable(workspace_applications))
    # Get the ids in a list
    workspace_applications_id = [application_item.id for application_item in workspace_applications_flat]
    return workspace_applications_id
