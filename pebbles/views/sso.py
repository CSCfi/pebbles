import datetime
import base64
import logging
import uuid

from flask import render_template, request
from flask_restful import reqparse

from pebbles.app import app
from pebbles.models import db, User
from pebbles.views.commons import admin_icons, workspace_owner_icons, workspace_manager_icons, user_icons
from pebbles.views.commons import create_user, is_workspace_manager


@app.route('/oauth2')
def oauth2_login():
    parser = reqparse.RequestParser()
    parser.add_argument('agreement_sign', type=str, default=False)
    args = parser.parse_args()
    if not app.config['OAUTH2_LOGIN_ENABLED']:
        error_description = 'oauth2 not enabled'
        return render_template(
            'error.html',
            error_title='Login error',
            error_description=error_description
        )

    # decode base64 encoded 'user:password' to get the shared secret from password
    basic_auth = base64.b64decode(request.headers['Authorization'].split(' ')[1].encode('utf-8'))
    basic_auth = bytes.decode(basic_auth, 'utf-8')
    proxy_secret = basic_auth.split(':')[1]

    # only allow requests that know the shared secret to proceed
    if proxy_secret != app.config['OAUTH2_PROXY_SECRET']:
        error_description = 'Proxy communication key mismatch'
        return render_template(
            'error.html',
            error_title='Proxy communication key mismatch',
            error_description=error_description
        )

    eppn = request.headers['X-Forwarded-Email']
    user = User.query.filter_by(eppn=eppn).first()

    # New users: Get credentials from aai proxy and then send agreement to user to sign.
    if not user:
        if not args.agreement_sign:
            return render_template(
                'terms.html',
                title=app.config['AGREEMENT_TITLE'],
                terms_link=app.config['AGREEMENT_TERMS_PATH'],
                cookies_link=app.config['AGREEMENT_COOKIES_PATH'],
                privacy_link=app.config['AGREEMENT_PRIVACY_PATH'],
                logo_path=app.config['AGREEMENT_LOGO_PATH']
            )
        elif args.agreement_sign == 'signed':
            user = create_user(eppn, password=uuid.uuid4().hex, email_id=eppn)
            user.tc_acceptance_date = datetime.datetime.utcnow()
            db.session.commit()

    # Existing users: Check if agreement is accepted. If not send the terms to user.
    if user and not user.tc_acceptance_date:
        if not args.agreement_sign:
            return render_template(
                'terms.html',
                title=app.config['AGREEMENT_TITLE'],
                terms_link=app.config['AGREEMENT_TERMS_PATH'],
                logo_path=app.config['AGREEMENT_LOGO_PATH']
            )
        elif args.agreement_sign == 'signed':
            user.tc_acceptance_date = datetime.datetime.utcnow()
            db.session.commit()
        else:
            error_description = 'Contact your administrator'
            return render_template(
                'error.html',
                error_title='User cannot access',
                error_description=error_description
            )

    if not user.is_active:
        user.is_active = True
        db.session.commit()
    if user.is_blocked:
        error_description = 'You have been blocked, contact your administrator'
        return render_template(
            'error.html',
            error_title='User Blocked',
            error_description=error_description
        )
    if user.is_admin:
        icons = admin_icons
    elif user.is_workspace_owner:
        icons = workspace_owner_icons
    elif is_workspace_manager(user):
        icons = workspace_manager_icons
    else:
        icons = user_icons

    logging.info('new oauth2 session for user %s', user.id)

    token = user.generate_auth_token(app.config['SECRET_KEY'])
    # does not support angularJS
    return render_template(
        'login.html',
        token=token,
        username=eppn,
        is_admin=user.is_admin,
        is_workspace_owner=user.is_workspace_owner,
        is_workspace_manager=is_workspace_manager(user),
        userid=user.id,
        icon_value=icons
    )
