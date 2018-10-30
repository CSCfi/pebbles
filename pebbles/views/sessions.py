from flask.ext.restful import fields, marshal
from flask import Blueprint as FlaskBlueprint

import logging
import json

from pebbles.models import User
from pebbles.forms import SessionCreateForm
from pebbles.server import app, restful
from pebbles.views.commons import is_group_manager  # changed

sessions = FlaskBlueprint('sessions', __name__)

token_fields = {
    'token': fields.String,
    'user_id': fields.String,
    'is_admin': fields.Boolean,
    'is_group_owner': fields.Boolean,
    'is_group_manager': fields.Boolean,
    'icon_value': fields.String
}

admin_icons = ["Dashboard", "Users", "Groups", "Blueprints", "Configure", "Statistics", "Account"]
group_owner_icons = ["Dashboard", "", "Groups", "Blueprints", "Configure", "", "Account"]
group_manager_icons = ["Dashboard", "", "", "Blueprints", "", "", "Account"]
user_icons = ["Dashboard", "", "", "", "", "", "Account"]


class SessionView(restful.Resource):
    def post(self):
        form = SessionCreateForm()
        if not form.validate_on_submit():
            logging.warn("validation error on user login")
            return form.errors, 422

        user = User.query.filter_by(email=form.email.data).first()
        if user and user.check_password(form.password.data):
            if user.is_admin:
                icons = json.dumps(admin_icons)
            elif user.is_group_owner:
                icons = json.dumps(group_owner_icons)
            elif is_group_manager(user):
                icons = json.dumps(group_manager_icons)
            else:
                icons = json.dumps(user_icons)

            return marshal({
                'token': user.generate_auth_token(app.config['SECRET_KEY']),
                'is_admin': user.is_admin,
                'is_group_owner': user.is_group_owner,
                'is_group_manager': is_group_manager(user),
                'user_id': user.id,
                'icon_value': icons
            }, token_fields)
        logging.warn("invalid login credentials for %s" % form.email.data)
        return {
            'message': 'Unauthorized',
            'status': 401
        }, 401
