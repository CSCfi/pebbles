import logging
import re

import flask_restful as restful
from flask import Blueprint as FlaskBlueprint
from flask import abort, g
from flask_restful import marshal_with, reqparse
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
        return set(x for x in re.split(r"[, \n\t]", value) if x)

    @auth.login_required
    @marshal_with(user_fields)
    def get(self):
        user = g.user
        if user.is_admin:
            try:
                args = self.parser.parse_args()
                user_query = apply_filter_users(args)
            except exceptions.BadRequest:
                logging.warning("no arguments found")
                user_query = apply_filter_users()
            return user_query.all()
        return [user]


class UserView(restful.Resource):
    @auth.login_required
    @marshal_with(user_fields)
    def get(self, user_id):
        # only admins can query other users' details
        if not g.user.is_admin and user_id != g.user.id:
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
            logging.warning("trying to delete non-existing user")
            abort(404)
        user.delete()
        db.session.commit()


class UserBlacklist(restful.Resource):
    parser = reqparse.RequestParser()
    parser.add_argument('block', type=bool, required=True)

    @auth.login_required
    @requires_admin
    def put(self, user_id):
        args = self.parser.parse_args()
        block = args.block

        user = User.query.filter_by(id=user_id).first()
        if not user:
            logging.warning("trying to block/unblock non-existing user")
            abort(404)
        if block:
            logging.info("blocking user %s", user.ext_id)
            user.is_blocked = True
        else:
            logging.info("unblocking user %s", user.ext_id)
            user.is_blocked = False
        db.session.add(user)
        db.session.commit()


class UserWorkspaceAssociationList(restful.Resource):
    @auth.login_required
    @marshal_with(workspace_user_association_fields)
    def get(self, user_id):
        if not g.user.is_admin and user_id != g.user.id:
            abort(403)
        return WorkspaceUserAssociation.query.filter_by(user_id=user_id).all()


class UserWorkspaceOwner(restful.Resource):
    parser = reqparse.RequestParser()
    parser.add_argument('make_workspace_owner', type=bool, required=True)

    @auth.login_required
    @requires_admin
    def put(self, user_id):
        args = self.parser.parse_args()
        make_workspace_owner = args.make_workspace_owner

        user = User.query.filter_by(id=user_id).first()
        if not user:
            logging.warning("user does not exist")
            abort(404)
        # promote
        if make_workspace_owner:
            if user.workspace_quota == 0:
                logging.info("making user %s a workspace owner by granting workspace quota", user.ext_id)
                user.workspace_quota = 2
        # demote
        else:
            user.workspace_quota = 0
            for ws in user.get_owned_workspace_associations():
                logging.info('removing user %s ownership from workspace %s' % (ws.user_id, ws.workspace_id))
                ws.is_owner = False
        db.session.add(user)
        db.session.commit()
