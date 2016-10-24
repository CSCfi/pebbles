from flask.ext.restful import fields, marshal
from flask import Blueprint as FlaskBlueprint

import logging

from pouta_blueprints.models import User
from pouta_blueprints.forms import SessionCreateForm
from pouta_blueprints.server import app, restful
from pouta_blueprints.utils import is_group_manager

sessions = FlaskBlueprint('sessions', __name__)

token_fields = {
    'token': fields.String,
    'user_id': fields.String,
    'is_admin': fields.Boolean,
    'is_group_owner': fields.Boolean,
    'is_group_manager': fields.Boolean
}


class SessionView(restful.Resource):
    def post(self):
        form = SessionCreateForm()
        if not form.validate_on_submit():
            logging.warn("validation error on user login")
            return form.errors, 422

        user = User.query.filter_by(email=form.email.data).first()
        if user and user.check_password(form.password.data):
            return marshal({
                'token': user.generate_auth_token(app.config['SECRET_KEY']),
                'is_admin': user.is_admin,
                'is_group_owner': user.is_group_owner,
                'is_group_manager': is_group_manager(user),
                'user_id': user.id
            }, token_fields)
        logging.warn("invalid login credentials for %s" % form.email.data)
        return {
            'message': 'Unauthorized',
            'status': 401
        }, 401
