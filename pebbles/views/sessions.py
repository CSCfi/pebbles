import logging
import time

import flask_restful as restful
from flask import Blueprint as FlaskBlueprint, current_app
from flask_restful import fields, marshal

from pebbles.forms import SessionCreateForm
from pebbles.models import db, User
from pebbles.views.commons import update_email, EXT_ID_PREFIX_DELIMITER

sessions = FlaskBlueprint('sessions', __name__)

token_fields = {
    'token': fields.String,
    'user_id': fields.String,
    'is_admin': fields.Boolean,
    'is_workspace_owner': fields.Boolean,
    'is_workspace_manager': fields.Boolean,
}


class SessionView(restful.Resource):
    def post(self):
        form = SessionCreateForm()
        if not form.validate_on_submit():
            logging.warning('SessionView.post() validation error on user login')
            return form.errors, 422
        ext_id = form.ext_id.data
        if EXT_ID_PREFIX_DELIMITER in ext_id:
            logging.warning('SessionView.post() Prefix is not allowed in loginname')
            return 'Username cannot contain "%s"' % EXT_ID_PREFIX_DELIMITER, 422

        user = User.query.filter_by(ext_id=ext_id).first()
        if user and not user.email_id:
            # Email and ext_id are same because we invite users through email
            # update_email is in commons.py, as in future we could allow
            # update existing email of users and reuse the function
            user = update_email(ext_id=user.ext_id, email_id=user.ext_id)
        if user and user.check_password(form.password.data):
            # after successful validation update last_login_ts
            user.last_login_ts = time.time()
            db.session.commit()

            logging.info('SessionView.post() new session for user %s', user.id)

            return marshal({
                'token': user.generate_auth_token(current_app.config['SECRET_KEY']),
                'is_admin': user.is_admin,
                'is_workspace_owner': user.is_workspace_owner,
                'is_workspace_manager': user.is_workspace_manager,
                'user_id': user.id,
            }, token_fields)
        logging.warning('SessionView.post() invalid login credentials for %s', form.ext_id.data)
        return 'Invalid user or password', 401
