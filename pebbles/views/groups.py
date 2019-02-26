from flask.ext.restful import marshal_with, reqparse
from flask import abort, g
from flask import Blueprint as FlaskBlueprint
import logging
from pebbles.models import db, Group, User, GroupUserAssociation, Instance
from pebbles.forms import GroupForm
from pebbles.server import restful, app
from pebbles.views.commons import auth, group_fields, user_fields, requires_group_manager_or_admin, is_group_manager
from pebbles.utils import requires_admin, requires_group_owner_or_admin
from pebbles.tasks import run_update
import re
import datetime

groups = FlaskBlueprint('groups', __name__)


class GroupList(restful.Resource):
    @auth.login_required
    @requires_group_manager_or_admin
    @marshal_with(group_fields)
    def get(self):
        user = g.user
        group_user_query = GroupUserAssociation.query
        results = []
        if not user.is_admin:
            group_manager_objs = group_user_query.filter_by(user_id=user.id, manager=True).all()
            manager_groups = [group_manager_obj.group for group_manager_obj in group_manager_objs]
            groups = manager_groups
        else:
            query = Group.query
            groups = query.all()

        for group in groups:
            if group.current_status != 'archived' and group.current_status != 'deleted':
                group_owner_obj = group_user_query.filter_by(group_id=group.id, owner=True).first()
                owner = User.query.filter_by(id=group_owner_obj.user_id).first()
                # config and user_config dicts are required by schemaform and multiselect in the groups modify ui modal
                if user.is_admin or user.id == owner.id:
                    group.config = {"name": group.name, "join_code": group.join_code, "description": group.description}
                    group.user_config = generate_user_config(group)
                    group.owner_eppn = owner.eppn
                    group.admin_group = owner.is_admin
                else:
                    group.config = {}
                    group.user_config = {}
                results.append(group)

        if not user.is_admin:
            results = sorted(results, key=lambda group: group.name)
        else:  # For admins, the admin groups should be first
            results = sorted(results, key=lambda group: (-group.admin_group, group.owner_eppn, group.name))
        return results

    @auth.login_required
    @requires_group_owner_or_admin
    def post(self):
        user = g.user
        user_owned_groups = GroupUserAssociation.query.filter_by(user_id=user.id, owner=True).count()
        if not user.group_quota and user.is_group_owner and not user_owned_groups:
            user.group_quota = 1
        elif not user.group_quota and user.is_group_owner and user_owned_groups:
            user.group_quota = user_owned_groups
        if not user.is_admin and user_owned_groups >= user.group_quota and user.is_group_owner:
            logging.warn("Maximum User_group_quota is reached")
            return {"message": "You reached maximum number of groups that can be created. If you wish create more groups contact administrator"}, 422

        form = GroupForm()
        if not form.validate_on_submit():
            logging.warn("validation error on creating group")
            return form.errors, 422
        group = Group(form.name.data)
        group.description = form.description.data

        group_owner_obj = GroupUserAssociation(user=user, group=group, manager=True, owner=True)
        group.users.append(group_owner_obj)

        db.session.add(group)
        db.session.commit()


class GroupView(restful.Resource):
    parser = reqparse.RequestParser()
    parser.add_argument('current_status', type=str)

    @auth.login_required
    @requires_admin
    @marshal_with(group_fields)
    def get(self, group_id):

        query = Group.query.filter_by(id=group_id)
        group = query.first()

        if not group:
            abort(404)
        if group.current_status == 'archived':
            abort(422)

        return group

    @auth.login_required
    @requires_group_owner_or_admin
    def put(self, group_id):
        form = GroupForm()
        if not form.validate_on_submit():
            logging.warn("validation error on creating group")
            return form.errors, 422
        user = g.user
        group = Group.query.filter_by(id=group_id).first()
        if not group:
            abort(404)
        if group.current_status == 'archived':
            abort(422)
        group_owner_obj = GroupUserAssociation.query.filter_by(group_id=group.id, owner=True).first()
        owner = group_owner_obj.user
        if not user.is_admin and user.id != owner.id:
            abort(403)
        if group.name != form.name.data:
            group.name = form.name.data
            group.join_code = form.name.data  # hybrid property
        group.description = form.description.data

        user_config = form.user_config.data
        try:
            group = group_users_add(group, user_config, owner)
        except KeyError:
            abort(422)
        except RuntimeError as e:
            return {"error": "{}".format(e)}, 422

        db.session.add(group)
        db.session.commit()

    @auth.login_required
    @requires_admin
    def patch(self, group_id):
        args = self.parser.parse_args()
        group = Group.query.filter_by(id=group_id).first()
        if not group:
            abort(404)

        if args.get('current_status'):
            group.current_status = args['current_status']
            blueprint_instances = group.blueprints.all()
            for blueprint in blueprint_instances:
                blueprint.current_status = 'archived'
            db.session.commit()

    @auth.login_required
    @requires_admin
    def delete(self, group_id):
        group = Group.query.filter_by(id=group_id).first()

        if not group:
            logging.warn("trying to delete non-existing group")
            abort(404)
        if group.name == 'System.default':
            logging.warn("cannot delete the default system group")
            return {"error": "Cannot delete the default system group"}, 422

        group_blueprints = group.blueprints.all()

        if not group_blueprints:
            db.session.delete(group)
            db.session.commit()
        else:
            for group_blueprint in group_blueprints:
                blueprint_instances = Instance.query.filter_by(blueprint_id=group_blueprint.id).all()
                if blueprint_instances:
                    for instance in blueprint_instances:
                        instance.to_be_deleted = True
                        instance.state = Instance.STATE_DELETING
                        instance.deprovisioned_at = datetime.datetime.utcnow()
                        if not app.dynamic_config.get('SKIP_TASK_QUEUE'):
                            run_update.delay(instance.id)
                group_blueprint.current_status = group_blueprint.STATE_DELETED
            group.current_status = group.STATE_DELETED
            db.session.commit()


def group_users_add(group, user_config, owner):
    """Validate and add the managers, banned users and normal users in a group"""
    # Generate a 'set' of Group Managers
    managers_list = []
    managers_list.append(owner)  # Owner is always a manager
    managers_list.append(g.user)  # always add the user creating/modifying the group
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
                logging.warn("user %s does not exist", banned_user_id)
                raise RuntimeError("User to be banned, does not exist")
            if banned_user_id in managers_set:
                logging.warn("user %s is a manager, cannot ban" % banned_user_id)
                raise RuntimeError("User is a manager, demote to normal status first")
            banned_users_final.append(banned_user)
    group.banned_users = banned_users_final  # setting a new list adds and also removes relationships
    # add the users
    users_final = []
    if group.users:
        for group_user_obj in group.users:  # Association object
            if group_user_obj.user in banned_users_final:
                logging.warn("user %s is banned, cannot add", group_user_obj.user.id)
                continue
            if group_user_obj.user.id in managers_set:  # if user is a manager
                group_user_obj.manager = True
            elif not group_user_obj.owner:  # if the user is not an owner then keep all users to non manager status
                group_user_obj.manager = False
            users_final.append(group_user_obj)
    group.users = users_final

    return group


def generate_user_config(group):
    """Generates the user_config object used in multiselect ui component on groups modify modal"""
    user_config = {'banned_users': [], 'managers': []}
    if group.banned_users:
        for banned_user in group.banned_users:
            user_config['banned_users'].append({'id': banned_user.id})
    group_manager_objs = GroupUserAssociation.query.filter_by(group_id=group.id, manager=True, owner=False).all()
    if group_manager_objs:
        for group_manager_obj in group_manager_objs:
            manager = group_manager_obj.user
            user_config['managers'].append({'id': manager.id})
    return user_config


class GroupJoin(restful.Resource):
    @auth.login_required
    def put(self, join_code):
        user = g.user
        group = Group.query.filter_by(join_code=join_code).first()
        if not group:
            logging.warn("invalid group join code %s", join_code)
            return {"error": "The code entered is invalid. Please recheck and try again"}, 422
        if user in group.banned_users:
            logging.warn("user banned from the group with code %s", join_code)
            return {"error": "You are banned from this group, please contact the concerned person"}, 403
        if user in [group_user_obj.user for group_user_obj in group.users]:
            logging.warn("user %s already exists in group", user.id)
            return {"error": "User already in the group"}, 422
        group_user_obj = GroupUserAssociation(user=user, group=group)
        group.users.append(group_user_obj)
        db.session.add(group)
        db.session.commit()


class GroupListExit(restful.Resource):
    @auth.login_required
    @marshal_with(group_fields)
    def get(self):
        user = g.user
        results = []
        group_user_query = (
            GroupUserAssociation.query
            .filter_by(user_id=user.id, owner=False)
            .order_by(GroupUserAssociation.manager.desc())
        )
        group_user_objs = group_user_query.all()
        for group_user_obj in group_user_objs:
            group = group_user_obj.group
            if re.match('^System.+', group.name):  # Do not show system level groups
                continue
            group.config = {}
            group.user_config = {}

            role = 'user'
            if is_group_manager(user, group):
                role = 'manager'
            group.role = role
            results.append(group)
        return results


class GroupExit(restful.Resource):
    @auth.login_required
    def put(self, group_id):
        user = g.user
        group = Group.query.filter_by(id=group_id).first()
        if not group:
            logging.warn("no group with id %s", group_id)
            abort(404)
        if re.match('^System.+', group.name):  # Do not allow exiting system level groups
            abort(403)

        group_user_filtered_query = GroupUserAssociation.query.filter_by(group_id=group.id, user_id=user.id)
        user_is_owner = group_user_filtered_query.filter_by(owner=True).first()
        if user_is_owner:
            logging.warn("cannot exit the owned group %s", group_id)
            return {"error": "Cannot exit the group which is owned by you"}, 422
        user_in_group = group_user_filtered_query.first()
        if not user_in_group:
            logging.warn("user %s is not a part of the group", user.id)
            abort(403)
        group.users.remove(user_in_group)
        db.session.add(group)
        db.session.commit()


class GroupUsersList(restful.Resource):
    parser = reqparse.RequestParser()
    parser.add_argument('banned_list', type=bool)

    @auth.login_required
    @requires_group_owner_or_admin
    @marshal_with(user_fields)
    def get(self, group_id):
        args = self.parser.parse_args()
        banned_list = args.banned_list
        user = g.user
        group = Group.query.filter_by(id=group_id).first()
        if not group:
            logging.warn('group %s does not exist', group_id)
            abort(404)

        group_user_query = GroupUserAssociation.query
        user_is_owner = group_user_query.filter_by(group_id=group.id, user_id=user.id, owner=True).first()
        if not user.is_admin and not user_is_owner:
            logging.warn('Group %s not owned, cannot see users', group_id)
            abort(403)

        total_users = None
        if banned_list:
            banned_users = group.banned_users.all()
            group_user_objs = group_user_query.filter_by(
                group_id=group.id,
                manager=False
            ).all()
            users = [group_user_obj.user for group_user_obj in group_user_objs]
            total_users = users + banned_users
        else:
            group_user_objs = group_user_query.filter_by(
                group_id=group.id,
                owner=False
            ).all()
            total_users = [group_user_obj.user for group_user_obj in group_user_objs]

        return total_users


class ClearUsersFromGroup(restful.Resource):
    parser = reqparse.RequestParser()
    parser.add_argument('group_id', type=str)

    @auth.login_required
    @requires_group_owner_or_admin
    def delete(self):

        args = self.parser.parse_args()
        group_id = args.group_id
        user = g.user
        group = Group.query.filter_by(id=group_id).first()
        group_user_query = GroupUserAssociation.query
        user_is_owner = group_user_query.filter_by(group_id=group_id, user_id=user.id, owner=True).first()

        if not group:
            logging.warn('Group %s does not exist', group_id)
            return {"error": "The group does not exist"}, 404

        if group.name == 'System.default':
            logging.warn("cannot clear the default system group")
            return {"error": "Cannot clear the default system group"}, 422

        if user_is_owner or user.is_admin:
            group_user_query.filter_by(group_id=group_id,
                                       owner=False, manager=False).delete()
            db.session.commit()
        else:
            logging.warn('Group %s not owned, cannot clear users', group_id)
            return {"error": "Only the group owner can clear users"}, 403
