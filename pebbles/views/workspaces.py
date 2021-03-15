import datetime
import logging
import re

import flask_restful as restful
from dateutil.relativedelta import relativedelta
from flask import Blueprint as FlaskBlueprint
from flask import abort, g
from flask_restful import marshal_with, reqparse, fields

from pebbles.forms import WorkspaceForm
from pebbles.models import db, Workspace, User, WorkspaceUserAssociation, Instance
from pebbles.utils import requires_admin, requires_workspace_owner_or_admin
from pebbles.views.commons import auth, user_fields, is_workspace_manager

workspaces = FlaskBlueprint('workspaces', __name__)
join_workspace = FlaskBlueprint('join_workspace', __name__)

workspace_fields = {
    'id': fields.String(attribute='id'),
    'name': fields.String,
    'join_code': fields.String,
    'description': fields.Raw,
    'create_ts': fields.Integer,
    'expiry_ts': fields.Integer,
    'config': fields.Raw,
    'user_config': fields.Raw,
    'owner_eppn': fields.String,
    'role': fields.String,
    'environment_quota': fields.Integer,
}

total_users_fields = {
    'owner': fields.Nested(user_fields),
    'manager_users': fields.List(fields.Nested(user_fields)),
    'normal_users': fields.List(fields.Nested(user_fields)),
    'banned_users': fields.List(fields.Nested(user_fields))
}


class WorkspaceList(restful.Resource):
    @auth.login_required
    @marshal_with(workspace_fields)
    def get(self):
        user = g.user
        workspace_user_query = WorkspaceUserAssociation.query
        results = []
        if not user.is_admin:
            workspace_mappings = workspace_user_query.filter_by(user_id=user.id).all()
            workspaces = [workspace_obj.workspace for workspace_obj in workspace_mappings]

        else:
            query = Workspace.query
            workspaces = query.all()

        for workspace in workspaces:
            if not user.is_admin \
                    and (workspace.current_status in ('archived', 'deleted') or workspace.name.startswith('System.')):
                continue

            workspace_owner_obj = workspace_user_query.filter_by(workspace_id=workspace.id, owner=True).first()
            owner = User.query.filter_by(id=workspace_owner_obj.user_id).first()
            # config and user_config dicts are required by schemaform and multiselect in the workspaces modify ui modal
            if user.is_admin or user.id == owner.id:
                workspace.config = {
                    "name": workspace.name,
                    "join_code": workspace.join_code,
                    "description": workspace.description
                }
                workspace.user_config = generate_user_config(workspace)
                workspace.owner_eppn = owner.eppn
                workspace.admin_workspace = owner.is_admin
            else:
                workspace.config = {}
                workspace.user_config = {}
            results.append(workspace)

        if not user.is_admin:
            results = sorted(results, key=lambda workspace: workspace.name)
        else:  # For admins, the admin workspaces should be first
            results = sorted(
                results,
                key=lambda workspace: (-workspace.admin_workspace, workspace.owner_eppn, workspace.name)
            )
        return results

    @auth.login_required
    @requires_workspace_owner_or_admin
    def post(self):
        user = g.user
        user_workspaces = WorkspaceUserAssociation.query.filter_by(user_id=user.id, owner=True)
        user_owned_workspaces = [uw.workspace.current_status == 'active' for uw in user_workspaces].count(True)
        if not user.is_admin and user_owned_workspaces >= user.workspace_quota:
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

        workspace_owner_obj = WorkspaceUserAssociation(user=user, workspace=workspace, manager=True, owner=True)
        workspace.users.append(workspace_owner_obj)

        workspace.create_ts = datetime.datetime.utcnow().timestamp()
        workspace.expiry_ts = (datetime.datetime.utcnow() + relativedelta(months=+6)).timestamp()

        db.session.add(workspace)
        db.session.commit()

        return restful.marshal(workspace, workspace_fields), 200


class WorkspaceView(restful.Resource):
    parser = reqparse.RequestParser()
    parser.add_argument('current_status', type=str)

    @auth.login_required
    @requires_admin
    @marshal_with(workspace_fields)
    def get(self, workspace_id):

        query = Workspace.query.filter_by(id=workspace_id)
        workspace = query.first()

        if not workspace:
            abort(404)
        if workspace.current_status == 'archived':
            abort(422)

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
        if workspace.current_status == 'archived':
            abort(422)
        workspace_owner_obj = WorkspaceUserAssociation.query.filter_by(workspace_id=workspace.id, owner=True).first()
        owner = workspace_owner_obj.user
        if not user.is_admin and user.id != owner.id:
            abort(403)
        if workspace.name != form.name.data:
            workspace.name = form.name.data
            workspace.join_code = form.name.data  # hybrid property
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

    @auth.login_required
    @requires_admin
    def patch(self, workspace_id):
        args = self.parser.parse_args()
        workspace = Workspace.query.filter_by(id=workspace_id).first()
        if not workspace:
            abort(404)

        if args.get('current_status'):
            workspace.current_status = args['current_status']
            environment_instances = workspace.environments.all()
            for environment in environment_instances:
                environment.current_status = 'archived'
            db.session.commit()

    @auth.login_required
    @requires_admin
    def delete(self, workspace_id):
        workspace = Workspace.query.filter_by(id=workspace_id).first()

        if not workspace:
            logging.warning("trying to delete non-existing workspace")
            abort(404)
        if workspace.name == 'System.default':
            logging.warning("cannot delete the default system workspace")
            return {"error": "Cannot delete the default system workspace"}, 422

        workspace_environments = workspace.environments.all()

        if not workspace_environments:
            db.session.delete(workspace)
            db.session.commit()
        else:
            for workspace_environment in workspace_environments:
                environment_instances = Instance.query.filter_by(environment_id=workspace_environment.id).all()
                if environment_instances:
                    for instance in environment_instances:
                        instance.to_be_deleted = True
                        instance.state = Instance.STATE_DELETING
                        instance.deprovisioned_at = datetime.datetime.utcnow()
                        workspace_environment.current_status = workspace_environment.STATE_DELETED
            workspace.current_status = workspace.STATE_DELETED
            db.session.commit()


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
                workspace.users.append(workspace_owner_obj)
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
    if workspace.users:
        for workspace_user_obj in workspace.users:  # Association object
            if workspace_user_obj.user in banned_users_final:
                logging.warning("user %s is banned, cannot add", workspace_user_obj.user.id)
                continue
            if workspace_user_obj.user.id in managers_set:  # if user is a manager
                workspace_user_obj.manager = True
            elif not workspace_user_obj.owner:  # if the user is not an owner then keep all users to non manager status
                workspace_user_obj.manager = False
            users_final.append(workspace_user_obj)
    workspace.users = users_final

    return workspace


def generate_user_config(workspace):
    """Generates the user_config object used in multiselect ui component on workspaces modify modal"""
    user_config = {'banned_users': [], 'managers': [], 'owner': []}
    if workspace.banned_users:
        for banned_user in workspace.banned_users:
            user_config['banned_users'].append({'id': banned_user.id})
    workspace_manager_objs = WorkspaceUserAssociation.query.filter_by(
        workspace_id=workspace.id,
        manager=True,
        owner=False
    ).all()
    if workspace_manager_objs:
        for workspace_manager_obj in workspace_manager_objs:
            manager = workspace_manager_obj.user
            user_config['managers'].append({'id': manager.id})
    workspace_owner_obj = WorkspaceUserAssociation.query.filter_by(workspace_id=workspace.id, owner=True).first()
    if workspace_owner_obj:
        owner = workspace_owner_obj.user
        user_config['owner'].append({'id': owner.id})
    return user_config


class JoinWorkspace(restful.Resource):
    @auth.login_required
    def put(self, join_code):
        user = g.user
        workspace = Workspace.query.filter_by(join_code=join_code).first()
        if not workspace:
            logging.warning("invalid workspace join code %s", join_code)
            return {"error": "The code entered is invalid. Please recheck and try again"}, 422
        if user in workspace.banned_users:
            logging.warning("user banned from the workspace with code %s", join_code)
            return {"error": "You are banned from this workspace, please contact the concerned person"}, 403
        if user in [workspace_user_obj.user for workspace_user_obj in workspace.users]:
            logging.warning("user %s already exists in workspace", user.id)
            return {"error": "User already exists in the workspace"}, 422

        workspace_user_obj = WorkspaceUserAssociation(user=user, workspace=workspace)
        workspace.users.append(workspace_user_obj)
        db.session.add(workspace)
        db.session.commit()

        return restful.marshal(workspace, workspace_fields), 200


class WorkspaceListExit(restful.Resource):
    @auth.login_required
    @marshal_with(workspace_fields)
    def get(self):
        user = g.user
        results = []
        workspace_user_query = (
            WorkspaceUserAssociation.query.filter_by(
                user_id=user.id, owner=False
            ).order_by(
                WorkspaceUserAssociation.manager.desc()
            )
        )
        workspace_user_objs = workspace_user_query.all()
        for workspace_user_obj in workspace_user_objs:
            workspace = workspace_user_obj.workspace
            if re.match('^System.+', workspace.name):  # Do not show system level workspaces
                continue
            workspace.config = {}
            workspace.user_config = {}

            role = 'user'
            if is_workspace_manager(user, workspace):
                role = 'manager'
            workspace.role = role
            results.append(workspace)
        return results


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

        workspace_user_filtered_query = WorkspaceUserAssociation.query.filter_by(
            workspace_id=workspace.id,
            user_id=user.id
        )
        user_is_owner = workspace_user_filtered_query.filter_by(owner=True).first()
        if user_is_owner:
            logging.warning("cannot exit the owned workspace %s", workspace_id)
            return {"error": "Cannot exit the workspace which is owned by you"}, 422
        user_in_workspace = workspace_user_filtered_query.first()
        if not user_in_workspace:
            logging.warning("user %s is not a part of the workspace", user.id)
            abort(403)
        workspace.users.remove(user_in_workspace)
        db.session.add(workspace)
        db.session.commit()


class WorkspaceUsersList(restful.Resource):
    parser = reqparse.RequestParser()

    @auth.login_required
    @requires_workspace_owner_or_admin
    @marshal_with(total_users_fields)
    def get(self, workspace_id):
        user = g.user
        workspace = Workspace.query.filter_by(id=workspace_id).first()
        if not workspace:
            logging.warning('workspace %s does not exist', workspace_id)
            abort(404)

        workspace_user_query = WorkspaceUserAssociation.query
        user_is_owner = workspace_user_query.filter_by(workspace_id=workspace.id, user_id=user.id, owner=True).first()
        if not user.is_admin and not user_is_owner:
            logging.warning('Workspace %s not owned, cannot see users', workspace_id)
            abort(403)

        banned_users = workspace.banned_users.all()
        workspace_user_objs = workspace_user_query.filter_by(
            workspace_id=workspace.id,
            owner=False,
            manager=False
        ).all()
        normal_users = [workspace_user_obj.user for workspace_user_obj in workspace_user_objs]
        workspace_user_objs = workspace_user_query.filter_by(
            workspace_id=workspace.id,
            owner=True
        ).first()
        owner_user = workspace_user_objs.user
        workspace_user_objs = workspace_user_query.filter_by(
            workspace_id=workspace.id,
            manager=True
        ).all()
        manager_users = [workspace_user_obj.user for workspace_user_obj in workspace_user_objs]
        total_users = {
            'owner': owner_user,
            'manager_users': manager_users,
            'normal_users': normal_users,
            'banned_users': banned_users
        }
        return total_users


class WorkspaceClearUsers(restful.Resource):
    parser = reqparse.RequestParser()
    parser.add_argument('workspace_id', type=str)

    @auth.login_required
    @requires_workspace_owner_or_admin
    def post(self, workspace_id):

        user = g.user
        workspace = Workspace.query.filter_by(id=workspace_id).first()
        workspace_user_query = WorkspaceUserAssociation.query
        user_is_owner = workspace_user_query.filter_by(workspace_id=workspace_id, user_id=user.id, owner=True).first()

        if not workspace:
            logging.warning('Workspace %s does not exist', workspace_id)
            return {"error": "The workspace does not exist"}, 404

        if workspace.name == 'System.default':
            logging.warning("cannot clear the default system workspace")
            return {"error": "Cannot clear the default system workspace"}, 422

        if user_is_owner or user.is_admin:
            workspace_user_query.filter_by(workspace_id=workspace_id, owner=False, manager=False).delete()
            db.session.commit()
        else:
            logging.warning('Workspace %s not owned, cannot clear users', workspace_id)
            return {"error": "Only the workspace owner can clear users"}, 403
