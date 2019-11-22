import datetime
import logging
import re

import flask_restful as restful
from dateutil.relativedelta import relativedelta
from flask import Blueprint as FlaskBlueprint
from flask import abort, g, current_app
from flask_restful import marshal_with, reqparse
from werkzeug import exceptions

from pebbles.forms import ChangePasswordForm, UserForm
from pebbles.models import db, User, ActivationToken
from pebbles.rules import apply_rules_users
from pebbles.utils import requires_admin
from pebbles.views.commons import user_fields, auth, invite_user

users = FlaskBlueprint('users', __name__)


class UserList(restful.Resource):
    parser = reqparse.RequestParser()
    parser.add_argument('page', type=int, location='args')
    parser.add_argument('page_size', type=int, location='args')
    parser.add_argument('filter_str', type=str)
    parser.add_argument('user_type', type=str)
    parser.add_argument('count', type=int)
    parser.add_argument('expiry_date', type=int)

    @staticmethod
    def address_list(value):
        return set(x for x in re.split(r"[, \n\t]", value) if x)

    parser.add_argument('addresses')

    @auth.login_required
    @requires_admin
    @marshal_with(user_fields)
    def post(self):
        form = UserForm()
        if not form.validate_on_submit():
            logging.warning("validation error on user add: %s" % form.errors)
            abort(422)
        invite_user(form.eppn.data, form.password.data, form.is_admin.data)
        return User.query.all()

    @auth.login_required
    @marshal_with(user_fields)
    def get(self):
        user = g.user
        if user.is_admin:
            try:
                args = self.parser.parse_args()
                user_query = apply_rules_users(args)
            except exceptions.BadRequest:
                logging.warning("no arguments found")
                user_query = apply_rules_users()
            return user_query.all()
        return [user]

    @auth.login_required
    @requires_admin
    def patch(self):
        try:
            args = self.parser.parse_args()
        except exceptions.BadRequest:
            abort(422)
            return

        if 'expiry_date' in args and args.expiry_date:
            expiry_date = datetime.datetime.utcnow() + relativedelta(months=+args.expiry_date)
        else:
            # default expiry date is 6 months
            expiry_date = datetime.datetime.utcnow() + relativedelta(months=+6)

        if 'addresses' in args and args.addresses:
            addresses = self.address_list(args.addresses)
            incorrect_addresses = []
            for address in addresses:
                try:
                    invite_user(address, password=None, is_admin=False, expiry_date=expiry_date)
                except RuntimeError:
                    logging.exception("cannot add user %s" % address)
                    incorrect_addresses.append(address)
            if incorrect_addresses:
                return incorrect_addresses, 422

        if 'count' in args and args.count:
            user_query = apply_rules_users(args)
            return user_query.count()


class UserView(restful.Resource):
    @auth.login_required
    @marshal_with(user_fields)
    def get(self, user_id):
        if not g.user.is_admin and user_id != g.user.id:
            abort(403)
        return User.query.filter_by(id=user_id).first()

    @auth.login_required
    def put(self, user_id):
        if not g.user.is_admin and user_id != g.user.id:
            abort(403)
        form = ChangePasswordForm()
        if not form.validate_on_submit():
            return form.errors, 422
        user = User.query.filter_by(id=user_id).first()
        if not user:
            abort(404)
        user.set_password(form.password.data)
        db.session.add(user)
        db.session.commit()

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


class UserActivationUrl(restful.Resource):
    @auth.login_required
    @requires_admin
    def get(self, user_id):
        token = ActivationToken.query.filter_by(user_id=user_id).first()
        activation_url = '%s/#/activate/%s' % (current_app.config['BASE_URL'], token.token)
        return {'activation_url': activation_url}


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
            logging.info("blocking user %s", user.eppn)
            user.is_blocked = True
        else:
            logging.info("unblocking user %s", user.eppn)
            user.is_blocked = False
        db.session.add(user)
        db.session.commit()


class UserGroupOwner(restful.Resource):
    parser = reqparse.RequestParser()
    parser.add_argument('make_group_owner', type=bool, required=True)

    @auth.login_required
    @requires_admin
    def put(self, user_id):
        args = self.parser.parse_args()
        make_group_owner = args.make_group_owner

        user = User.query.filter_by(id=user_id).first()
        if not user:
            logging.warning("user does not exist")
            abort(404)
        if make_group_owner:
            logging.info("making user %s a group owner", user.eppn)
            user.is_group_owner = True
            user.group_quota = 1
            user.blueprint_quota = 1
        else:
            logging.info("removing user %s as a group owner", user.eppn)
            user.is_group_owner = False
        db.session.add(user)
        db.session.commit()
