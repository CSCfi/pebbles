from flask.ext.restful import marshal_with
from flask import abort, g
from flask import Blueprint as FlaskBlueprint
import logging
import json
from pouta_blueprints.models import db, Group, User
from pouta_blueprints.forms import GroupForm
from pouta_blueprints.server import restful
from pouta_blueprints.views.commons import auth, group_fields
from pouta_blueprints.utils import requires_admin, requires_group_owner_or_admin

groups = FlaskBlueprint('groups', __name__)


class GroupList(restful.Resource):
    @auth.login_required
    @requires_group_owner_or_admin
    @marshal_with(group_fields)
    def get(self):

        user = g.user
        if not user.is_admin:
            results = user.groups()
        else:  # group owner
            query = Group.query
            results = []
            for group in query.all():
                group.config = {"name": group.name, "join_code": group.join_code, "description": group.description}
                group.user_ids = [{"id": user_item.id} for user_item in group.users]
                group.banned_user_ids = [{"id": banned_user_item.id} for banned_user_item in group.banned_users]
                group.owner_ids = [{"id": owner_item.id} for owner_item in group.owners]
                results.add(group)
        return results

    @auth.login_required
    @requires_group_owner_or_admin
    def post(self):
        form = GroupForm()
        if not form.validate_on_submit():
            logging.warn("validation error on creating group")
            return form.errors, 422
        # Check if the join code is valid
        join_code = form.join_code.data
        join_code_error = {"join code error": "joining code already taken, please use a different code"}
        join_code_grp = Group.query.filter_by(join_code=join_code)
        if join_code_grp:
            logging.warn("group with code %s already exists", join_code)
            return join_code_error, 422

        user = g.user
        group = Group(form.name.data, join_code, user)
        group.description = form.description.data
        user_ids_str = form.users.data  # Initial number of added users
        banned_user_ids_str = form.banned_users.data
        owners_ids_str = form.owners.data
        group = group_users_add(group, banned_user_ids_str, user_ids_str, owners_ids_str)
        db.session.add(group)
        db.session.commit()


class GroupView(restful.Resource):
    @auth.login_required
    @requires_admin
    @marshal_with(group_fields)
    def get(self, group_id):

        query = Group.query.filter_by(id=group_id)
        group = query.first()
        if not group:
            abort(404)
        return group

    @auth.login_required
    @requires_group_owner_or_admin
    def put(self, group_id):
        form = GroupForm()
        if not form.validate_on_submit():
            logging.warn("validation error on creating group")
            return form.errors, 422
        # check if the join code is valid
        join_code = form.join_code.data
        join_code_error = {"join code error": "joining code already taken, please use a different code"}
        join_code_grp = Group.query.filter_by(join_code=join_code)
        if join_code_grp:
            logging.warn("group with code %s already exists", join_code)
            return join_code_error, 422

        user = g.user
        group = Group.query.filter_by(id=group_id).first()
        if not user.is_admin and group not in user.owner_groups:
            abort(403)
        group.name = form.name.data
        group.join_code = form.join_code.data
        group.description = form.description.data
        users_id_str = form.users.data  # Initial number of added users
        banned_users_id_str = form.banned_users.data
        owners_ids_str = form.owners.data
        group = group_users_add(group, banned_users_id_str, users_id_str, owners_ids_str)

        db.session.add(group)
        db.session.commit()

    @auth.login_required
    @requires_admin
    def delete(self, group_id):
        group = Group.query.filter_by(id=group_id).first()
        if not group:
            logging.warn("trying to delete non-existing group")
            abort(404)
        db.session.delete(group)
        db.session.commit()


def group_users_add(group, banned_user_ids_str, user_ids_str, owner_ids_str):
    # Add Banned users
    banned_user_ids = []
    if banned_user_ids_str:
        banned_user_ids = json.loads(banned_user_ids_str)  # from UI
        for banned_user_id in banned_user_ids:
            banned_user = User.query.filter_by(id=banned_user_id).first()
            if not banned_user:
                logging.warn("user %s does not exist", banned_user_id)
                continue
            if banned_user in group.banned_users:
                logging.warn("user %s already banned", banned_user_id)
                continue
            group.banned_users.append(banned_user)
    # Now add users
    if user_ids_str:
        user_ids = json.loads(user_ids_str)
        for user_id in user_ids:
            if user_id in banned_user_ids:  # Check if the user is not banned
                logging.warn("user %s is blocked, cannot add", user_id)
                continue
            user = User.query.filter_by(id=user_id).first()
            if not user:
                logging.warn("trying to add non-existent user %s", user_id)
                continue
            if user in group.users:
                logging.warn("user already added to the group")
                continue
            group.users.append(user)
    # Group owners
    if owner_ids_str:
        owner_ids = json.loads(owner_ids_str)
        for owner_id in owner_ids:
            if owner_id in banned_user_ids:  # Check if the user is not banned
                logging.warn("user %s is blocked, cannot add as owner", owner_id)
                continue
            owner = User.query.filter_by(id=owner_id).first()
            if not owner:
                logging.warn("trying to add non-existent owner %s", owner_id)
                continue
            if owner in group.owners:
                logging.warn("user already added as owner to the group")
                continue
            group.owners.append(owner)
    return group


class GroupJoin(restful.Resource):

    @auth.login_required
    def put(self, join_code):
        if not join_code:
            return {"join_code missing": "no join code given"}, 422

        user = g.user
        group = Group.query.filter_by(join_code=join_code)
        if user in group.banned_users:
            logging.warn("user banned from the group with code %s", join_code)
            return {"group ban": "You are banned from this group, please contact the concerned person"}, 422
        if user in group.users:
            logging.warn("user %s already exists in group", user.id)
            return {"user already added": "User already in the group"}, 422
        group.users.append(user)
        db.session.add(group)
        db.session.commit()
