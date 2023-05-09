import datetime
import json
import logging
import re
import time

import flask_restful as restful
import sqlalchemy as sa
import sqlalchemy.orm
from dateutil.relativedelta import relativedelta
from flask import Blueprint as FlaskBlueprint, current_app
from flask import abort, g, request
from flask_restful import marshal, marshal_with, reqparse, fields, inputs

from pebbles import rules
from pebbles.app import app
from pebbles.forms import WorkspaceForm
from pebbles.models import db, Workspace, User, WorkspaceMembership, Application, ApplicationSession
from pebbles.utils import requires_admin, requires_workspace_owner_or_admin, load_cluster_config
from pebbles.views.commons import auth

workspaces = FlaskBlueprint('workspaces', __name__)
join_workspace = FlaskBlueprint('join_workspace', __name__)

workspace_fields_admin = {
    'id': fields.String,
    'pseudonym': fields.String,
    'name': fields.String,
    'join_code': fields.String,
    'description': fields.Raw,
    'create_ts': fields.Integer,
    'expiry_ts': fields.Integer,
    'owner_ext_id': fields.String,
    'application_quota': fields.Integer,
    'memory_limit_gib': fields.Integer,
    'membership_type': fields.String(default='admin'),
    'membership_expiry_policy': fields.Raw,
    'cluster': fields.String,
    'config': fields.Raw,
}

workspace_fields_owner = {
    'id': fields.String,
    'name': fields.String,
    'join_code': fields.String,
    'description': fields.Raw,
    'create_ts': fields.Integer,
    'expiry_ts': fields.Integer,
    'owner_ext_id': fields.String,
    'application_quota': fields.Integer,
    'memory_limit_gib': fields.Integer,
    'membership_type': fields.String(default='owner'),
    'membership_expiry_policy': fields.Raw,
    'cluster': fields.String,
}

workspace_fields_manager = {
    'id': fields.String,
    'name': fields.String,
    'join_code': fields.String,
    'description': fields.Raw,
    'create_ts': fields.Integer,
    'expiry_ts': fields.Integer,
    'application_quota': fields.Integer,
    'memory_limit_gib': fields.Integer,
    'membership_type': fields.String(default='manager'),
    'membership_expiry_policy': fields.Raw,
    'cluster': fields.String,
}

workspace_fields_user = {
    'id': fields.String,
    'name': fields.String,
    'description': fields.Raw,
    'create_ts': fields.Integer,
    'expiry_ts': fields.Integer,
    'memory_limit_gib': fields.Integer,
    'membership_type': fields.String(default='member'),
    'membership_expiry_policy': fields.Raw,
}

member_fields = dict(
    user_id=fields.String,
    ext_id=fields.String,
    email_id=fields.String,
    is_owner=fields.Boolean,
    is_manager=fields.Boolean,
    is_banned=fields.Boolean,
)


def marshal_based_on_role(user, workspace):
    if user.is_admin:
        if workspace.name.startswith('System.'):
            workspace.user_association_type = 'public'
            workspace.membership_type = 'public'
        return restful.marshal(workspace, workspace_fields_admin)
    elif rules.is_user_owner_of_workspace(user, workspace):
        return restful.marshal(workspace, workspace_fields_owner)
    elif rules.is_user_manager_in_workspace(user, workspace):
        return restful.marshal(workspace, workspace_fields_manager)
    else:
        return restful.marshal(workspace, workspace_fields_user)


class WorkspaceList(restful.Resource):
    get_parser = reqparse.RequestParser()
    get_parser.add_argument('membership_expiry_policy_kind', type=str, location='args')

    @auth.login_required
    def get(self):
        user = g.user
        args = self.get_parser.parse_args()

        workspace_user_query = WorkspaceMembership.query
        results = []
        if not user.is_admin:
            workspace_mappings = workspace_user_query.filter_by(user_id=user.id, is_banned=False).all()
            workspaces = [workspace_obj.workspace for workspace_obj in workspace_mappings]
        else:
            query = Workspace.query
            workspaces = query.all()

        workspaces = sorted(workspaces, key=lambda ws: ws.name)
        for workspace in workspaces:
            if not user.is_admin and workspace.name.startswith('System.'):
                continue

            if not workspace.status == Workspace.STATUS_ACTIVE:
                continue

            # filter based on membership expiry policy
            mep_kind = args.get('membership_expiry_policy_kind', None)
            if mep_kind and workspace.membership_expiry_policy.get('kind') != mep_kind:
                continue

            owner = next((wm.user for wm in workspace.memberships if wm.is_owner), None)
            workspace.owner_ext_id = owner.ext_id if owner else None

            # marshal results based on role
            results.append(marshal_based_on_role(user, workspace))

        return results

    @auth.login_required
    @requires_workspace_owner_or_admin
    def post(self):
        user = g.user
        user_owned_workspaces = WorkspaceMembership.query.filter_by(user_id=user.id, is_owner=True)
        num_user_owned_workspaces = [
            w.workspace.status == Workspace.STATUS_ACTIVE for w in user_owned_workspaces].count(True)
        if not user.is_admin and num_user_owned_workspaces >= user.workspace_quota:
            logging.warning("Maximum workspace quota %s is reached" % user.workspace_quota)
            return dict(
                message="You reached maximum number of workspaces that can be created."
                        " If you wish create more workspaces please contact the support"
            ), 422
        form = WorkspaceForm()
        if not form.validate_on_submit():
            logging.warning("validation error on creating workspace")
            return form.errors, 422
        workspace = Workspace(form.name.data)
        workspace.description = form.description.data

        workspace_owner_obj = WorkspaceMembership(user=user, workspace=workspace, is_manager=True, is_owner=True)
        workspace.memberships.append(workspace_owner_obj)

        workspace.create_ts = datetime.datetime.utcnow().timestamp()
        workspace.expiry_ts = (datetime.datetime.utcnow() + relativedelta(months=+6)).timestamp()

        # If users can later select the clusters, then this should be taken from the form and verified
        workspace.cluster = app.config['DEFAULT_CLUSTER']

        # By default, run sessions on nodes for all users
        workspace.config = dict(scheduler_tolerations=['role=user'])

        db.session.add(workspace)
        db.session.commit()

        # marshal based on role
        return marshal_based_on_role(user, workspace)


class WorkspaceView(restful.Resource):
    @auth.login_required
    @requires_admin
    @marshal_with(workspace_fields_admin)
    def get(self, workspace_id):

        query = Workspace.query.filter_by(id=workspace_id)
        workspace = query.first()

        if not workspace:
            abort(404)
        if workspace.status == Workspace.STATUS_DELETED:
            abort(404)

        return workspace

    @auth.login_required
    @requires_workspace_owner_or_admin
    def put(self, workspace_id):
        form = WorkspaceForm()
        if not form.validate_on_submit():
            logging.warning("validation error on creating workspace")
            return form.errors, 422
        user = g.user
        workspace = Workspace.query.filter_by(id=workspace_id).first()
        if not workspace:
            abort(404)
        if not workspace.status == Workspace.STATUS_ACTIVE:
            abort(422)
        workspace_owner_obj = WorkspaceMembership.query.filter_by(workspace_id=workspace.id, is_owner=True).first()
        owner = workspace_owner_obj.user
        if not (user.is_admin or user.id == owner.id):
            abort(403)
        if workspace.name != form.name.data:
            workspace.name = form.name.data
            # assigning to this hybrid property triggers regeneration of join code
            workspace.join_code = form.name.data
        workspace.description = form.description.data

        user_config = form.user_config.data
        try:
            workspace = workspace_users_add(workspace, user_config, owner, workspace_owner_obj)
        except KeyError:
            abort(422)
        except RuntimeError as e:
            return {"error": "{}".format(e)}, 422

        db.session.add(workspace)
        db.session.commit()

        # marshal based on role
        return marshal_based_on_role(user, workspace)

    @auth.login_required
    def patch(self, workspace_id):
        user = g.user
        parser = reqparse.RequestParser()
        parser.add_argument('status', type=str)
        new_status = parser.parse_args().get('status')

        return self.handle_status_change(user, workspace_id, new_status)

    @auth.login_required
    def delete(self, workspace_id):
        user = g.user
        return self.handle_status_change(user, workspace_id, Workspace.STATUS_DELETED)

    def handle_status_change(self, user, workspace_id, new_status):
        workspace = Workspace.query.filter_by(id=workspace_id).first()

        if not workspace:
            abort(404)
        # allow only predefined set
        if new_status not in Workspace.VALID_STATUSES:
            abort(403)
        # reactivation is not supported
        if new_status == Workspace.STATUS_ACTIVE:
            abort(403)
        # resurrection is not allowed
        if workspace.status == Workspace.STATUS_DELETED:
            abort(403)
        # System. can't be changed
        if workspace.name.startswith('System.'):
            logging.warning('Cannot change the status of System workspace')
            return {'error': 'Cannot change the status of System workspace'}, 422
        # you have to be an admin or the owner
        if not (user.is_admin or rules.is_user_owner_of_workspace(user, workspace)):
            abort(403)

        # archive
        if new_status == Workspace.STATUS_ARCHIVED:
            logging.info('Archiving workspace %s "%s"', workspace.id, workspace.name)
            workspace.status = Workspace.STATUS_ARCHIVED
            applications = workspace.applications.all()
            for application in applications:
                application.status = Application.STATUS_DELETED
            db.session.commit()

        # delete
        if new_status == Workspace.STATUS_DELETED:
            logging.info('Deleting workspace %s "%s"', workspace.id, workspace.name)
            workspace.status = Workspace.STATUS_DELETED
            applications = workspace.applications.all()
            for application in applications:
                application.status = Application.STATUS_DELETED
                for application_session in application.application_sessions:
                    if application_session.state in (
                            ApplicationSession.STATE_DELETING, ApplicationSession.STATE_DELETED):
                        continue
                    logging.info('Setting application_session %s to be deleted', application_session.name)
                    application_session.to_be_deleted = True
                    application_session.state = ApplicationSession.STATE_DELETING
                    application_session.deprovisioned_at = datetime.datetime.utcnow()
            db.session.commit()

        # marshal based on role
        return marshal_based_on_role(user, workspace)


def workspace_users_add(workspace, user_config, owner, workspace_owner_obj):
    """Validate and add the managers, banned users and normal users in a workspace"""
    # Generate a 'set' of Workspace Managers
    managers_list = []
    managers_list.append(owner)  # Owner is always a manager
    managers_list.append(g.user)  # always add the user creating/modifying the workspace
    # add new workspace owner
    if 'owner' in user_config:
        new_owner = user_config['owner']
        for new_owner_item in new_owner:
            new_owner_id = new_owner_item['id']
            new_owner = User.query.filter_by(id=new_owner_id).first()
            if new_owner != owner:
                workspace_owner_obj.user = new_owner
                workspace.memberships.append(workspace_owner_obj)
                managers_list.append(new_owner)

    if 'managers' in user_config:
        managers = user_config['managers']
        for manager_item in managers:
            manager_id = manager_item['id']
            managers_list.append(manager_id)
    managers_set = set(managers_list)  # use this set to check if a user was appointed as a manager
    # Add Banned users
    banned_users_final = []
    if 'banned_users' in user_config:
        banned_users = user_config['banned_users']
        for banned_user_item in banned_users:
            banned_user_id = banned_user_item['id']
            banned_user = User.query.filter_by(id=banned_user_id).first()
            if not banned_user:
                logging.warning("user %s does not exist", banned_user_id)
                raise RuntimeError("User to be banned, does not exist")
            if banned_user_id in managers_set:
                logging.warning("user %s is a manager, cannot ban" % banned_user_id)
                raise RuntimeError("User is a manager, demote to normal status first")
            banned_users_final.append(banned_user)
    workspace.banned_users = banned_users_final  # setting a new list adds and also removes relationships
    # add the users
    users_final = []
    if workspace.memberships:
        for membership in workspace.memberships:
            if membership.user in banned_users_final:
                logging.warning("user %s is banned, cannot add", membership.user.id)
                continue
            if membership.user.id in managers_set:  # if user is a manager
                membership.is_manager = True
            elif not membership.is_owner:  # if the user is not an owner then keep all users to non manager status
                membership.manager = False
            users_final.append(membership)
    workspace.memberships = users_final

    return workspace


class JoinWorkspace(restful.Resource):
    @auth.login_required
    def put(self, join_code):
        user = g.user
        workspace = Workspace.query.filter_by(join_code=join_code).first()
        if not workspace:
            logging.warning('invalid workspace join code %s', join_code)
            return 'The code entered is invalid. Please recheck and try again', 422

        # filter workspaces that have expiry_ts in the past
        if workspace.has_expired():
            logging.warning('workspace for join code %s has expired', join_code)
            return 'The workspace for this join code has expired.', 422

        existing_relation = next(filter(lambda wm: wm.user_id == user.id, workspace.memberships), None)
        if existing_relation and existing_relation.is_banned:
            logging.warning('banned user %s tried to join workspace %s with code %s',
                            user.ext_id, workspace.name, join_code)
            return 'You are banned from this workspace, please contact the concerned person', 403

        if existing_relation:
            logging.warning('user %s already exists in workspace', user.id)
            return 'User already exists in the workspace', 422

        workspace_user_obj = WorkspaceMembership(user=user, workspace=workspace)
        workspace.memberships.append(workspace_user_obj)
        db.session.add(workspace)
        db.session.commit()

        # marshal based on role
        return marshal_based_on_role(user, workspace)


class WorkspaceExit(restful.Resource):
    @auth.login_required
    def put(self, workspace_id):
        user = g.user
        workspace = Workspace.query.filter_by(id=workspace_id).first()
        if not workspace:
            logging.warning("no workspace with id %s", workspace_id)
            abort(404)
        if re.match('^System.+', workspace.name):  # Do not allow exiting system level workspaces
            abort(403)

        workspace_user_filtered_query = WorkspaceMembership.query.filter_by(
            workspace_id=workspace.id,
            user_id=user.id
        )
        if rules.is_user_owner_of_workspace(user, workspace):
            logging.warning("cannot exit the owned workspace %s", workspace_id)
            return {"error": "Cannot exit the workspace which is owned by you"}, 422
        user_in_workspace = workspace_user_filtered_query.first()
        if not user_in_workspace:
            logging.warning("user %s is not a part of the workspace", user.id)
            abort(403)
        workspace.memberships.remove(user_in_workspace)
        db.session.add(workspace)
        db.session.commit()


class WorkspaceMemberList(restful.Resource):
    get_parser = reqparse.RequestParser()
    get_parser.add_argument('member_count', type=inputs.boolean, default=False, location='args')

    @auth.login_required
    def get(self, workspace_id):
        args = self.get_parser.parse_args()
        user = g.user
        workspace = Workspace.query.filter_by(id=workspace_id).first()
        if not workspace:
            logging.warning('workspace %s does not exist', workspace_id)
            abort(404)

        if not (user.is_admin or rules.is_user_manager_in_workspace(user, workspace)):
            logging.warning('workspace %s not managed by %s, cannot see users', workspace_id, user.ext_id)
            abort(403)

        memberships = WorkspaceMembership.query \
            .filter_by(workspace_id=workspace_id) \
            .options(sa.orm.subqueryload(WorkspaceMembership.user)) \
            .all()

        members = []
        for wm in memberships:
            if wm.user.is_deleted:
                continue
            members.append(dict(
                user_id=wm.user_id,
                ext_id=wm.user.ext_id,
                email_id=wm.user.email_id,
                is_owner=wm.is_owner,
                is_manager=wm.is_manager,
                is_banned=wm.is_banned
            ))
        if args is not None and 'member_count' in args and args.get('member_count'):
            return len(members)
        return marshal(members, member_fields)

    patch_parser = reqparse.RequestParser()
    patch_parser.add_argument('user_id', type=str, required=True, location='json')
    patch_parser.add_argument('operation', type=str, required=True, location='json')

    @auth.login_required
    def patch(self, workspace_id):
        user = g.user
        args = self.patch_parser.parse_args()
        workspace = Workspace.query.filter_by(id=workspace_id).first()
        if not workspace:
            logging.warning('workspace %s does not exist', workspace_id)
            abort(404)

        if not (user.is_admin or rules.is_user_manager_in_workspace(user, workspace)):
            logging.warning('workspace %s not managed by %s, cannot see users', workspace_id, user.ext_id)
            abort(403)

        wm = WorkspaceMembership.query \
            .filter_by(workspace_id=workspace_id) \
            .filter_by(user_id=args.user_id) \
            .options(sa.orm.subqueryload(WorkspaceMembership.user)) \
            .first()
        if not wm:
            logging.warning('member %s not found', args.user_id)
            abort(404)

        # block operations on owners
        if wm.is_owner:
            logging.warning('cannot operate on owners, workspace %s', workspace_id)
            abort(403)

        if args.operation == 'promote':
            wm.is_manager = True
        elif args.operation == 'demote':
            wm.is_manager = False
        elif args.operation == 'ban':
            wm.is_banned = True
        elif args.operation == 'unban':
            wm.is_banned = False
        else:
            logging.info('unknown operation %s', args.operation)
            abort(422)

        logging.info('%s member %s in workspace %s', args.operation, wm.user_id, wm.workspace_id)
        db.session.commit()


class WorkspaceTransferOwnership(restful.Resource):

    @auth.login_required
    @requires_workspace_owner_or_admin
    def patch(self, workspace_id):
        parser = reqparse.RequestParser()
        parser.add_argument('new_owner_id', type=str)

        args = parser.parse_args()

        user = g.user

        workspace = Workspace.query.filter_by(id=workspace_id).first()

        wm_old_owner = WorkspaceMembership.query.filter_by(
            workspace_id=workspace_id,
            user_id=user.id,
            is_owner=True
        ).first()
        wm_new_owner = WorkspaceMembership.query \
            .filter_by(workspace_id=workspace_id) \
            .filter_by(user_id=args.new_owner_id) \
            .options(sa.orm.subqueryload(WorkspaceMembership.user)) \
            .first()

        if not wm_old_owner:
            logging.warning('workspace %s not owned, cannot transfer member', workspace_id)
            return {'error': 'Only the workspace owner can transfer ownership'}, 403

        if not workspace:
            logging.warning('workspace %s does not exist', workspace_id)
            return {'error': 'The workspace does not exist'}, 404

        if workspace.name.startswith('System.'):
            logging.warning('cannot transfer a System workspace')
            return {'error': 'Cannot transfer a System workspace'}, 422

        # check if new-owner-to-be is a part of the workspace
        if not wm_new_owner:
            logging.warning('user %s is not a member of the workspace', args.new_owner_id)
            return {'error': 'User is not a member of workspace'}, 403

        # block operations if new-owner-to-be is already owner in that workspace
        if wm_new_owner.is_owner:
            logging.warning('user is already owner of workspace %s', workspace_id)
            return {'error': 'User is already owner of the workspace'}, 403

        if not wm_new_owner.user.is_workspace_owner:
            logging.warning('user %s needs owner privileges in workspace %s', args.new_owner_id, workspace_id)
            return {'error': 'User %s needs owner privileges, please contact administrator' % args.new_owner_id}, 403

        try:
            wm_new_owner.is_manager = True
            wm_new_owner.is_owner = True
            wm_old_owner.is_manager = True
            wm_old_owner.is_owner = False
            db.session.commit()
        except Exception as e:
            logging.warning(e)


class WorkspaceClearMembers(restful.Resource):
    parser = reqparse.RequestParser()
    parser.add_argument('workspace_id', type=str)

    @auth.login_required
    @requires_workspace_owner_or_admin
    def post(self, workspace_id):

        user = g.user
        workspace = Workspace.query.filter_by(id=workspace_id).first()
        workspace_member_query = WorkspaceMembership.query

        if not workspace:
            logging.warning('workspace %s does not exist', workspace_id)
            return {"error": "The workspace does not exist"}, 404

        if workspace.name.startswith('System.'):
            logging.warning("cannot clear a System workspace")
            return {"error": "Cannot clear a System workspace"}, 422

        if user.is_admin or rules.is_user_owner_of_workspace(user, workspace):
            workspace_member_query.filter_by(workspace_id=workspace_id, is_owner=False, is_manager=False).delete()
            db.session.commit()
        else:
            logging.warning('workspace %s not owned, cannot clear members', workspace_id)
            return {"error": "Only the workspace owner can clear members"}, 403


class WorkspaceClearExpiredMembers(restful.Resource):
    parser = reqparse.RequestParser()
    parser.add_argument('workspace_id', type=str)

    @auth.login_required
    @requires_admin
    def post(self, workspace_id):
        workspace = Workspace.query.filter_by(id=workspace_id).first()

        if not workspace:
            logging.warning('workspace "%s" does not exist', workspace_id)
            return {"error": "The workspace does not exist"}, 404

        if workspace.membership_expiry_policy.get('kind') != Workspace.MEP_ACTIVITY_TIMEOUT:
            msg = 'membership expiry policy for workspace "%s" is not "%s"' % (
                workspace_id, Workspace.MEP_ACTIVITY_TIMEOUT
            )
            logging.warning(msg)
            return {"error": msg}, 422

        # list members that have either
        # - last login older than the policy limit
        # - have never logged in but have been created earlier than the policy limit (guest users)
        timeout_days = workspace.membership_expiry_policy.get('timeout_days')
        expiry_limit = datetime.datetime.fromtimestamp(time.time() - timeout_days * 24 * 3600)
        membership_query = WorkspaceMembership.query \
            .filter_by(workspace_id=workspace_id, is_owner=False, is_manager=False) \
            .join(WorkspaceMembership.user) \
            .filter(sa.or_(User._last_login_ts < expiry_limit,
                           sa.and_(User._last_login_ts == sa.null(),
                                   User._joining_ts < expiry_limit
                                   )
                           )
                    )

        num_deleted = 0
        for membership in membership_query.all():
            logging.info('removing expired membership in workspace %s for user %s', workspace_id, membership.user.id)
            db.session.delete(membership)
            num_deleted += 1

        if num_deleted:
            db.session.commit()

        return dict(num_deleted=num_deleted)


class WorkspaceAccounting(restful.Resource):

    @auth.login_required
    @requires_admin
    def get(self, workspace_id):
        applications = Application.query.filter_by(workspace_id=workspace_id).all()

        session_accounting = {}
        total_gib_hours = 0
        for application in applications:
            for session in application.application_sessions:
                if not (session.deprovisioned_at and session.provisioned_at):
                    continue

                duration = session.deprovisioned_at - session.provisioned_at

                if not session.provisioning_config.get('memory_gib'):
                    continue

                gib_hours = session.provisioning_config['memory_gib'] * duration.total_seconds() / 3600

                total_gib_hours = total_gib_hours + gib_hours

        session_accounting['workspace_id'] = workspace_id
        session_accounting['gib_hours'] = total_gib_hours

        return session_accounting


class WorkspaceMemoryLimitGiB(restful.Resource):
    parser = reqparse.RequestParser()
    parser.add_argument('new_limit', type=int)

    @auth.login_required
    @requires_admin
    def put(self, workspace_id):
        args = self.parser.parse_args()

        workspace = Workspace.query.filter_by(id=workspace_id).first()

        if not workspace:
            logging.warning('workspace %s does not exist', workspace_id)
            return dict(error='The workspace does not exist'), 404

        new_limit = args.new_limit
        if new_limit < 0:
            logging.warning('rejecting illegal memory_limit_gib "%s" for workspace %s', new_limit, workspace_id)
            return dict(error='illegal memory limit %s' % new_limit), 422

        workspace.memory_limit_gib = new_limit

        db.session.commit()

        return new_limit


class WorkspaceModifyUserFolderSize(restful.Resource):
    # Admin can modify user my_work folder size
    parser = reqparse.RequestParser()
    parser.add_argument('new_size', type=int)

    @auth.login_required
    @requires_admin
    def put(self, workspace_id):
        args = self.parser.parse_args()

        workspace = Workspace.query.filter_by(id=workspace_id).first()

        if not workspace:
            logging.warning('workspace %s does not exist', workspace_id)
            return dict(error='The workspace does not exist'), 404

        new_size = args.new_size

        if new_size < 0:
            logging.warning('rejecting illegal user_work_folder_size "%s" for workspace %s', new_size, workspace_id)
            return dict(error='illegal work folder size %s' % new_size), 422

        workspace_config = workspace.config
        # Get the config first out, assign value locally and assign it back.
        # This is because workspace.config is a hybrid field with a setter and getter

        workspace_config['user_work_folder_size_gib'] = new_size

        workspace.config = workspace_config

        db.session.commit()

        return new_size


class WorkspaceModifyCluster(restful.Resource):
    # Admin can modify workspace cluster
    parser = reqparse.RequestParser()
    parser.add_argument('new_cluster', type=str, required=True)

    @auth.login_required
    @requires_admin
    def put(self, workspace_id):
        args = self.parser.parse_args()

        workspace = Workspace.query.filter_by(id=workspace_id).first()

        if not workspace:
            logging.warning('workspace %s does not exist', workspace_id)
            return dict(error='The workspace does not exist'), 404

        new_cluster = args.new_cluster
        if 'TEST_MODE' not in current_app.config:
            cluster_config = load_cluster_config(load_passwords=False)
        else:
            # rig unit tests to use dummy data
            cluster_config = dict(clusters=[
                dict(name='dummy_cluster_1', driver='KubernetesLocalDriver'),
                dict(name='dummy_cluster_2', driver='KubernetesLocalDriver'),
            ])

        if new_cluster not in [c['name'] for c in cluster_config.get('clusters', [])]:
            logging.warning('rejecting unknown cluster "%s" for workspace %s', new_cluster, workspace_id)
            return dict(error='unknown cluster %s' % new_cluster), 422

        workspace.cluster = new_cluster

        db.session.commit()

        return new_cluster


class WorkspaceModifyMembershipExpiryPolicy(restful.Resource):

    @auth.login_required
    @requires_admin
    def put(self, workspace_id):
        workspace = Workspace.query.filter_by(id=workspace_id).first()

        if not workspace:
            logging.warning('workspace %s does not exist', workspace_id)
            return dict(error='The workspace does not exist'), 404

        new_mep = request.json
        error = Workspace.check_membership_expiry_policy(new_mep)
        if error:
            msg = 'membership expiry policy %s failed validation: %s' % (json.dumps(new_mep), error)
            logging.warning(msg)
            return dict(error=msg), 422

        workspace.membership_expiry_policy = new_mep
        db.session.commit()

        return workspace.membership_expiry_policy
