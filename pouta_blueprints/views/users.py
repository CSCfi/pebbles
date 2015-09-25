from flask.ext.restful import marshal_with, fields, reqparse
from flask import abort, g
from flask import Blueprint as FlaskBlueprint
from sqlalchemy import desc

import logging
import re
import werkzeug

from pouta_blueprints.models import db, Keypair, User
from pouta_blueprints.forms import ChangePasswordForm, UserForm
from pouta_blueprints.server import restful
from pouta_blueprints.utils import generate_ssh_keypair, requires_admin
from pouta_blueprints.views.commons import user_fields, auth, invite_user

users = FlaskBlueprint('users', __name__)


@users.route('/')
class UserList(restful.Resource):
    @staticmethod
    def address_list(value):
        return set(x for x in re.split(r",| |\n|\t", value) if x and '@' in x)

    parser = reqparse.RequestParser()
    parser.add_argument('addresses')

    @auth.login_required
    @requires_admin
    @marshal_with(user_fields)
    def post(self):
        form = UserForm()
        if not form.validate_on_submit():
            logging.warn("validation error on user add: %s" % form.errors)
            abort(422)
        invite_user(form.email.data, form.password.data, form.is_admin.data)
        return User.query.all()

    @auth.login_required
    @marshal_with(user_fields)
    def get(self):
        if g.user.is_admin:
            return User.query.all()
        return [g.user]

    @auth.login_required
    @requires_admin
    @marshal_with(user_fields)
    def patch(self):
        try:
            args = self.parser.parse_args()
        except:
            abort(422)
            return
        addresses = self.address_list(args.addresses)
        for address in addresses:
            try:
                invite_user(address)
            except:
                logging.exception("cannot add user %s" % address)
        return User.query.all()


@users.route('/<string:user_id>')
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
            logging.warn("trying to delete non-existing user")
            abort(404)
        user.delete()
        db.session.commit()


public_key_fields = {
    'id': fields.String,
    'public_key': fields.String
}


@users.route('/<string:user_id>/keypairs')
class KeypairList(restful.Resource):
    @auth.login_required
    @marshal_with(public_key_fields)
    def get(self, user_id):
        if not g.user.is_admin and user_id != g.user.id:
            abort(403)

        user = g.user
        if user_id != g.user.id:
            user = User.query.filter_by(id=user_id).first()

        if not user:
            abort(404)

        return Keypair.query.filter_by(user_id=user.id).order_by(desc("id")).all()


private_key_fields = {
    'private_key': fields.String
}


@users.route('/<string:user_id>/keypairs/create')
class CreateKeyPair(restful.Resource):
    @auth.login_required
    @marshal_with(private_key_fields)
    def post(self, user_id):
        if user_id != g.user.id:
            abort(403)
        priv, pub = generate_ssh_keypair()

        for keypair in Keypair.query.filter_by(user_id=g.user.id).all():
            db.session.delete(keypair)
        db.session.commit()

        key = Keypair()
        key.user_id = g.user.id
        key.public_key = pub
        db.session.add(key)
        db.session.commit()

        return {'private_key': priv}


@users.route('/<string:user_id>/upload')
class UploadKeyPair(restful.Resource):
    @auth.login_required
    def post(self, user_id):
        parser = reqparse.RequestParser()
        parser.add_argument('file', type=werkzeug.datastructures.FileStorage, location='files')

        if user_id != g.user.id:
            abort(403)
        args = parser.parse_args()
        if 'file' not in args:
            abort(422)

        existing_key = None
        for keypair in Keypair.query.filter_by(user_id=g.user.id).all():
            existing_key = keypair.public_key
            db.session.delete(keypair)
        db.session.commit()

        key = Keypair()
        key.user_id = g.user.id
        try:
            uploaded_key = args['file'].read()
            key.public_key = uploaded_key
            db.session.add(key)
            db.session.commit()
        except:
            key.public_key = existing_key
            db.session.add(key)
            db.session.commit()
            abort(422)
