import logging
import re

import flask_restful as restful
from flask import Blueprint as FlaskBlueprint
from flask import abort, g
from flask_restful import marshal_with, reqparse, inputs
from werkzeug import exceptions

from pebbles.models import db, User, WorkspaceUserAssociation
from pebbles.rules import apply_filter_users
from pebbles.utils import requires_admin
from pebbles.views.commons import user_fields, auth, workspace_user_association_fields

users = FlaskBlueprint('users', __name__)


class UserList(restful.Resource):
    parser = reqparse.RequestParser()
    parser.add_argument('page', type=int, location='args')
    parser.add_argument('page_size', type=int, location='args')
    parser.add_argument('filter_str', type=str)
    parser.add_argument('user_type', type=str)
    parser.add_argument('count', type=int)
    parser.add_argument('expiry_ts', type=int)
    parser.add_argument('addresses')

    @staticmethod
    def address_list(value):
        return set(x for x in re.split(r'[, \n\t]', value) if x)

    @auth.login_required
    @marshal_with(user_fields)
    def get(self):
        user = g.user
        if user.is_admin:
            try:
                args = self.parser.parse_args()
                user_query = apply_filter_users(args)
            except exceptions.BadRequest:
                logging.warning('no arguments found')
                user_query = apply_filter_users()
            return user_query.order_by(User._joining_ts).all()
        return [user]


class UserView(restful.Resource):
    @auth.login_required
    @marshal_with(user_fields)
    def get(self, user_id):
        # only admins can query other users' details
        if not (g.user.is_admin or user_id == g.user.id):
            abort(403)
        result = apply_filter_users().filter_by(id=user_id).first()
        if result:
            return result
        else:
            abort(404)

    @auth.login_required
    @requires_admin
    def delete(self, user_id):
        if not g.user.is_admin:
            abort(403)
        user = User.query.filter_by(id=user_id).first()
        if not user:
            logging.warning('trying to delete non-existing user')
            abort(404)
        user.delete()
        db.session.commit()

    parser = reqparse.RequestParser()
    parser.add_argument('workspace_quota', type=inputs.int_range(0, 999))
    parser.add_argument('is_blocked', type=inputs.boolean)

    @auth.login_required
    @requires_admin
    @marshal_with(user_fields)
    def patch(self, user_id):
        args = self.parser.parse_args()

        user = User.query.filter_by(id=user_id, is_deleted=False).first()
        if not user:
            logging.warning('trying to modify non-existing user')
            abort(404)

        workspace_quota = args.get('workspace_quota')
        if workspace_quota is not None:
            logging.info('setting workspace quota to %d for user %s', workspace_quota, user.ext_id)
            user.workspace_quota = workspace_quota

        is_blocked = args.get('is_blocked')
        if is_blocked is not None:
            logging.info('setting is_blocked to %s for user %s', is_blocked, user.ext_id)
            user.is_blocked = is_blocked

        db.session.commit()
        return user


class UserWorkspaceAssociationList(restful.Resource):
    @auth.login_required
    @marshal_with(workspace_user_association_fields)
    def get(self, user_id):
        if not g.user.is_admin and user_id != g.user.id:
            abort(403)
        return WorkspaceUserAssociation.query.filter_by(user_id=user_id).all()
