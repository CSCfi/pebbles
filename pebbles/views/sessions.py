from flask_restful import fields, marshal
from flask import Blueprint as FlaskBlueprint, current_app

import logging
import json

from pebbles.models import User
from pebbles.forms import SessionCreateForm
import flask_restful as restful
from pebbles.views.commons import is_group_manager, update_email  # changed
from pebbles.views.commons import admin_icons, group_owner_icons, group_manager_icons, user_icons

sessions = FlaskBlueprint('sessions', __name__)

token_fields = {
    'token': fields.String,
    'user_id': fields.String,
    'is_admin': fields.Boolean,
    'is_group_owner': fields.Boolean,
    'is_group_manager': fields.Boolean,
    'icon_value': fields.String
}


class SessionView(restful.Resource):
    def post(self):
        form = SessionCreateForm()
        if not form.validate_on_submit():
            logging.warning("validation error on user login")
            return form.errors, 422

        user = User.query.filter_by(eppn=form.eppn.data).first()
        if user and not user.email_id:
            # Email and eppn are same because we invite users through emailid
            user = update_email(eppn=user.eppn, email_id=user.eppn)
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
                'token': user.generate_auth_token(current_app.config['SECRET_KEY']),
                'is_admin': user.is_admin,
                'is_group_owner': user.is_group_owner,
                'is_group_manager': is_group_manager(user),
                'user_id': user.id,
                'icon_value': icons
            }, token_fields)
        logging.warning("invalid login credentials for %s" % form.eppn.data)
        return dict(message='Unauthorized', status=401), 401
