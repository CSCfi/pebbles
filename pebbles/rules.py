from sqlalchemy import or_, select, false, func
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
