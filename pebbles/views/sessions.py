import logging
import time
from datetime import timezone, datetime

import flask_restful as restful
from flask import Blueprint as FlaskBlueprint, current_app
from flask_restful import fields, marshal, reqparse

from pebbles.forms import SessionCreateForm
from pebbles.models import db, User
from pebbles.views.commons import update_email, EXT_ID_PREFIX_DELIMITER

sessions = FlaskBlueprint('sessions', __name__)

token_fields = {
    'token': fields.String(default=None),
    'user_id': fields.String,
    'is_admin': fields.Boolean(default=False),
    'is_workspace_owner': fields.Boolean(default=False),
    'is_workspace_manager': fields.Boolean(default=False),
    'terms_agreed': fields.Boolean,
}


class SessionView(restful.Resource):
    def post(self):
        parser = reqparse.RequestParser()
        parser.add_argument('agreement_sign', type=str, default=False)
        args = parser.parse_args()
        form = SessionCreateForm()
        if not form.validate_on_submit():
            logging.warning('SessionView.post() validation error on user login')
            return form.errors, 422
        ext_id = form.ext_id.data
        if EXT_ID_PREFIX_DELIMITER in ext_id:
            logging.warning('SessionView.post() Prefix is not allowed in loginname')
            return 'Username cannot contain "%s"' % EXT_ID_PREFIX_DELIMITER, 422

        user = User.query.filter_by(ext_id=ext_id).first()
        # Existing users: Check if agreement is accepted. If not send the terms to user.
        if user and user.check_password(form.password.data) and not user.tc_acceptance_date \
                and user.ext_id != 'worker@pebbles':
            if not args.agreement_sign:
                return marshal({
                    'user_id': user.id,
                    'terms_agreed': False,
                }, token_fields)
            elif args.agreement_sign == 'signed':
                user.tc_acceptance_date = datetime.now(timezone.utc)
                db.session.commit()
            else:
                logging.warning('Login aborted: User "%s" did not agree to terms, access denied', user.id)
                return 'You need to accept the terms and conditions', 403
        if user and user.has_expired():
            logging.warning('Login after expiry not permitted, user %s', user.id)
            return 'Account has expired', 403
        if user and not user.email_id and user.check_password(form.password.data):
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
                'terms_agreed': True,
            }, token_fields)
        logging.warning('SessionView.post() invalid login credentials for %s', form.ext_id.data)
        return 'Invalid user or password', 401
