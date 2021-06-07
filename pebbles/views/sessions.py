from flask_restful import fields, marshal
from flask import Blueprint as FlaskBlueprint, current_app

import datetime
import logging
import json

from pebbles.models import db, User
from pebbles.forms import SessionCreateForm
import flask_restful as restful
from pebbles.views.commons import is_workspace_manager, update_email  # changed
from pebbles.views.commons import admin_icons, workspace_owner_icons, workspace_manager_icons, user_icons

sessions = FlaskBlueprint('sessions', __name__)

token_fields = {
    'token': fields.String,
    'user_id': fields.String,
    'is_admin': fields.Boolean,
    'is_workspace_owner': fields.Boolean,
    'is_workspace_manager': fields.Boolean,
    # TODO: remove when AngularJS based old UI has been phased out
    'icon_value': fields.String
}


class SessionView(restful.Resource):
    def post(self):
        form = SessionCreateForm()
        if not form.validate_on_submit():
            logging.warning("validation error on user login")
            return form.errors, 422

        user = User.query.filter_by(ext_id=form.ext_id.data).first()
        if user and not user.email_id:
            # Email and ext_id are same because we invite users through email
            # update_email is in commons.py, as in future we could allow
            # update existing email of users and reuse the function
            user = update_email(ext_id=user.ext_id, email_id=user.ext_id)
        if user and user.check_password(form.password.data):
            # after successful validations clock last_login_date
            user.last_login_date = datetime.datetime.utcnow()
            db.session.commit()
            # TODO: remove when AngularJS based old UI has been phased out
            if user.is_admin:
                icons = json.dumps(admin_icons)
            elif user.is_workspace_owner:
                icons = json.dumps(workspace_owner_icons)
            elif is_workspace_manager(user):
                icons = json.dumps(workspace_manager_icons)
            else:
                icons = json.dumps(user_icons)

            logging.info("new session for user %s", user.id)

            return marshal({
                'token': user.generate_auth_token(current_app.config['SECRET_KEY']),
                'is_admin': user.is_admin,
                'is_workspace_owner': user.is_workspace_owner,
                'is_workspace_manager': is_workspace_manager(user),
                'user_id': user.id,
                'icon_value': icons
            }, token_fields)
        logging.warning("invalid login credentials for %s" % form.ext_id.data)
        return dict(message='Unauthorized', status=401), 401
