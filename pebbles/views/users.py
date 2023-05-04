import logging
import time
import re

import flask_restful as restful
from flask import Blueprint as FlaskBlueprint
from flask import abort, g
from flask_restful import marshal_with, reqparse, inputs

from pebbles.models import db, User
from pebbles.rules import apply_filter_users, apply_rules_workspace_memberships
from pebbles.utils import requires_admin, create_password
from pebbles.views.commons import user_fields, auth, workspace_membership_fields, create_user

users = FlaskBlueprint('users', __name__)


class UserList(restful.Resource):

    @staticmethod
    def address_list(value):
        return set(x for x in re.split(r'[, \n\t]', value) if x)

    @auth.login_required
    @requires_admin
    @marshal_with(user_fields)
    def get(self):
        return apply_filter_users().order_by(User._joining_ts).all()

    parser = reqparse.RequestParser()
    parser.add_argument('ext_id', type=str, required=True)
    parser.add_argument('lifetime_in_days', type=int)
    parser.add_argument('email_id', type=str)
    parser.add_argument('is_admin', type=bool)

    @auth.login_required
    @requires_admin
    def post(self):
        """Creates new user"""
        args = self.parser.parse_args()
        lifetime_in_days = args.get('lifetime_in_days')
        if lifetime_in_days is not None and not lifetime_in_days >= 1:
            abort(400, "lifetime_in_days should be >= 1")

        password = create_password(8)

        expiry_ts = time.time() + 3600 * 24 * lifetime_in_days if lifetime_in_days else None

        user = create_user(ext_id=args.get('ext_id'), password=password, is_admin=args.get('is_admin'),
                           email_id=args.get('email_id'), expiry_ts=expiry_ts)
        if user is None:
            abort(409, "user %s already exists" % args.get('ext_id'))

        return {'id': user.id, 'ext_id': user.ext_id, 'password': password, 'expiry_ts': expiry_ts}


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


class UserWorkspaceMembershipList(restful.Resource):
    @auth.login_required
    @marshal_with(workspace_membership_fields)
    def get(self, user_id):
        # only admins are allowed to query someone else
        if user_id != g.user.id and not g.user.is_admin:
            abort(403)

        return apply_rules_workspace_memberships(g.user, user_id).all()
