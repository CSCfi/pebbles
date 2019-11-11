import logging

from flask import abort, Blueprint
from flask_restful import marshal_with

from pebbles.forms import ActivationForm, PasswordResetRequestForm
from pebbles.models import db, ActivationToken, User
from pebbles.server import restful
from pebbles.views.commons import user_fields, add_user_to_default_group

activations = Blueprint('activations', __name__)

MAX_ACTIVATION_TOKENS_PER_USER = 3


class ActivationView(restful.Resource):
    @marshal_with(user_fields)
    def post(self, token_id):
        form = ActivationForm()
        if not form.validate_on_submit():
            return form.errors, 422

        token = ActivationToken.query.filter_by(token=token_id).first()
        if not token:
            return abort(410)

        user = User.query.filter_by(id=token.user_id).first()
        if not user:
            return abort(410)

        user.set_password(form.password.data)

        if not user.is_active:
            user.is_active = True
            add_user_to_default_group(user)
            db.session.add(user)
            logging.info("Activating user: %s" % user.eppn)
        db.session.delete(token)
        db.session.commit()

        logging.info("User %s is active and password has been updated" % user.eppn)

        return user


class ActivationList(restful.Resource):
    def post(self):
        form = PasswordResetRequestForm()
        if not form.validate_on_submit():
            return form.errors, 422

        # here users have same email and eppn data.
        # Because password link is sent only to the email_id
        user = User.query.filter_by(eppn=form.email_id.data).first()
        if not user:
            abort(404)

        if user.is_blocked:
            abort(409)

        if ActivationToken.query.filter_by(user_id=user.id).count() >= MAX_ACTIVATION_TOKENS_PER_USER:
            logging.warning(
                'There are already %d activation tokens for user %s'
                ', not sending another'
                % (MAX_ACTIVATION_TOKENS_PER_USER, user.email_id)
            )
            # 403 Forbidden
            abort(403)

        token = ActivationToken(user)

        db.session.add(token)
        db.session.commit()
