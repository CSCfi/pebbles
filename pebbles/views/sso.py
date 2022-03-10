import datetime
import logging
import time
import uuid

import requests
from flask import abort
from flask import render_template, request
from flask_restful import reqparse
from jose import jwt

from pebbles.app import app
from pebbles.models import db, User
from pebbles.utils import load_auth_config
from pebbles.views.commons import create_user, is_workspace_manager, EXT_ID_PREFIX_DELIMITER


@app.route('/oauth2')
def oauth2_login():
    parser = reqparse.RequestParser()
    parser.add_argument('agreement_sign', type=str, default=False)
    args = parser.parse_args()
    if not app.config['OAUTH2_LOGIN_ENABLED']:
        logging.warning('Login abort: oauth2 not enabled')
        abort(401)

    # Load authentication config and extract the part that is relevant to us.
    # In the config, there should be oauth2 key, and under that keys
    #   - openidConfigurationUrl for fetching the public configuration
    #   - authMethods, a list of allowed authentication methods, each with
    #     - acr       matched to acr in the claim
    #     - idClaim   attribute name for obtaining identity. separate multiple attributes with whitespace
    #     - prefix    prepend this + EXT_ID_PREFIX_DELIMITER to identity to generate ext_id
    auth_config = load_auth_config(app.config['API_AUTH_CONFIG_FILE'])
    oauth2_config = auth_config.get('oauth2') if auth_config else None
    auth_methods = oauth2_config['authMethods'] if oauth2_config else None
    if not (auth_config and oauth2_config and auth_methods):
        logging.warning('Login aborted: no auth-config available')
        abort(500)

    token = request.headers['Authorization'].split(' ')[1]

    # get jwk from openid-configuration url
    oidc_jwk = None
    try:
        oidc_key_endpoint = requests.get(oauth2_config['openidConfigurationUrl']).json()['jwks_uri']
        oidc_jwk = requests.get(oidc_key_endpoint).json()['keys'][0]
    except requests.exceptions.RequestException as e:
        logging.warning('Login aborted: cannot download oauth2 configuration: %s', e)
        abort(500)

    if not oidc_jwk:
        logging.warning('Login aborted: JWK could not be fetched')
        abort(500)

    try:
        options = {'verify_aud': False, 'verify_at_hash': False}
        claims = jwt.decode(token, oidc_jwk, algorithms=['RS256'], options=options)
    except Exception as e:
        logging.warning('Login aborted: JWT error: %s', e)
        abort(401)

    # check that we have email
    if 'email' in claims:
        email_id = claims['email']
    else:
        logging.warning('Login aborted: No valid email received')
        abort(422)

    # check that the account has not been locked
    if 'nsAccountLock' in claims and claims['nsAccountLock'] == 'true':
        logging.warning('Login aborted: Account is locked, email: "%s"', email_id)
        abort(422)

    # find the matching auth_method
    selected_method = None
    for method in auth_methods:
        if claims['acr'] == method['acr']:
            selected_method = method
            break

    if not selected_method:
        logging.warning('Login aborted: Authentication method with acr "%s" is not allowed', claims['acr'])
        abort(422)

    # find the claim that is mapped to ext_id
    user_id = None
    for id_attribute in selected_method['idClaim'].split():
        id_attribute = id_attribute.strip()
        user_id = claims.get(id_attribute)
        # take the first that matches
        if user_id:
            break

    if not user_id:
        logging.warning('Login aborted: No attribute(s) "%s" for user_id received, email "%s, method "%s"',
                        selected_method['idClaim'], email_id, selected_method['acr'])
        return "ERROR: We did not receive user identity from the login provider. " \
               "If this happens again, please contact support.", 422

    # construct ext_id from prefix, delimiter and user_id
    prefix = selected_method.get('prefix')
    ext_id = prefix + EXT_ID_PREFIX_DELIMITER + claims.get(selected_method['idClaim']).lower()

    # fetch matching user object from the database
    user = User.query.filter_by(ext_id=ext_id).first()

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
            user = create_user(ext_id=ext_id, password=uuid.uuid4().hex, email_id=email_id)
            user.tc_acceptance_date = datetime.datetime.utcnow()
            db.session.commit()

    # Existing users: Check if agreement is accepted. If not send the terms to user.
    if user and not user.tc_acceptance_date:
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
            user.tc_acceptance_date = datetime.datetime.utcnow()
            db.session.commit()
        else:
            logging.warning('Login aborted: User "%s" did not agree to terms, access denied', user.id)
            abort(403)

    if not user.is_active:
        user.is_active = True
        db.session.commit()
    if user.is_blocked:
        logging.warning('Login aborted: User "%s" is blocked', user.id)
        abort(403)

    # after successful validation update last_login_ts
    user.last_login_ts = time.time()
    db.session.commit()

    logging.info('new oauth2 session for user "%s"', user.id)

    token = user.generate_auth_token(app.config['SECRET_KEY'])

    return render_template(
        'login.html',
        token=token,
        username=ext_id,
        is_admin=user.is_admin,
        is_workspace_owner=user.is_workspace_owner,
        is_workspace_manager=is_workspace_manager(user),
        userid=user.id,
    )
