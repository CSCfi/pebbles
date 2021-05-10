import datetime
import logging
import uuid
import requests

from jose import jwt
from flask import render_template, request
from flask_restful import reqparse
from flask import abort

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
        logging.warning("Login abort: oauth2 not enabled")
        abort(401)

    token = request.headers['Authorization'].split(' ')[1]

    # get jwk from openid-configuration url
    oidc_key_endpoint = requests.get(app.config['OAUTH2_OPENID_CONFIGURATION_URL']).json()['jwks_uri']
    oidc_jwk = requests.get(oidc_key_endpoint).json()['keys'][0]

    if not oidc_jwk:
        logging.warning("JWK could not be fetched")
        abort(500)

    try:
        options = {'verify_aud': False, 'verify_at_hash': False}
        claims = jwt.decode(token, oidc_jwk, algorithms=['RS256'], options=options)
    except Exception as e:
        logging.warning("JWT error: %s" % e)
        abort(401)

    auth_methods = app.config['OAUTH2_AUTH_METHODS'].split(' ')

    if claims['acr'] not in auth_methods:
        logging.warning("Login abort: Authentication method is not allowed")
        abort(422)
    if 'nsAccountLock' in claims and claims['nsAccountLock'] == 'true':
        logging.warning("Login abort: Account is locked")
        abort(422)

    # Check what virtu sends - 'vppn' instead of 'eppn'

    if 'eppn' in claims:
        eppn = claims['eppn'].lower()
    elif 'vppn' in claims:
        eppn = claims['vppn'].lower()
    else:
        logging.warning("Login abort: Valid eppn nor vppn is received")
        abort(422)

    if 'email' in claims:
        email_id = claims['email']
    else:
        logging.warning("Login abort: Valid email is not received")
        abort(422)
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
            user = create_user(eppn, password=uuid.uuid4().hex, email_id=email_id)
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
            logging.warning("Login abort: User cannot access")
            abort(403)

    if not user.is_active:
        user.is_active = True
        db.session.commit()
    if user.is_blocked:
        logging.warning("Login abort: User is blocked")
        abort(403)
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
