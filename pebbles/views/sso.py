import logging
import time
import uuid
from datetime import timezone, datetime

import requests
from flask import abort, current_app
from flask import render_template, request
from flask_restful import reqparse
from jose import jwt

from pebbles.models import db, User
from pebbles.utils import load_auth_config
from pebbles.views.commons import create_user, is_workspace_manager, EXT_ID_PREFIX_DELIMITER


def render_terms_and_conditions():
    return render_template(
        'terms.html',
        title=current_app.config['AGREEMENT_TITLE'],
        terms_link=current_app.config['AGREEMENT_TERMS_PATH'],
        cookies_link=current_app.config['AGREEMENT_COOKIES_PATH'],
        privacy_link=current_app.config['AGREEMENT_PRIVACY_PATH'],
        logo_path=current_app.config['AGREEMENT_LOGO_PATH']
    )


def oauth2_login():
    parser = reqparse.RequestParser()
    parser.add_argument('agreement_sign', type=str, default=False, location='args')
    args = parser.parse_args()
    if not current_app.config['OAUTH2_LOGIN_ENABLED']:
        logging.warning('Login abort: oauth2 not enabled')
        abort(401)

    # Load authentication config and extract the part that is relevant to us.
    # In the config, there should be oauth2 key, and under that keys
    #   - openidConfigurationUrl for fetching the public configuration
    #   - authMethods, a list of allowed authentication methods, each with
    #     - acr       matched to acr in the claim
    #     - idClaim   attribute name for obtaining identity. separate multiple attributes with whitespace
    #     - prefix    prepend this + EXT_ID_PREFIX_DELIMITER to identity to generate ext_id
    auth_config = load_auth_config(current_app.config['API_AUTH_CONFIG_FILE'])
    oauth2_config = auth_config.get('oauth2') if auth_config else None
    auth_methods = oauth2_config['authMethods'] if oauth2_config else None
    if not (auth_config and oauth2_config and auth_methods):
        logging.warning('Login aborted: no auth-config available')
        abort(500)

    # idtoken (implicit flow)
    if not request.headers.get('Authorization'):
        logging.warning('Did not receive Authorization header. Headers: %s', request.headers.to_wsgi_list())
        abort(500)
    id_token = request.headers['Authorization'].split(' ')[1]

    # access_token (hybrid and authorized flow)
    access_token = request.headers.get('X-Forwarded-Access-Token')
    if not access_token:
        logging.warning('Did not receive header X-Forwarded-Access-Token. Headers: %s', request.headers.to_wsgi_list())
        abort(500)

    # get provider's well known config to get JWKS URI and download JWK to verify claims
    well_known_config = None
    oidc_jwk = None
    try:
        resp = requests.get(oauth2_config['openidConfigurationUrl'])
        if resp.status_code != 200:
            logging.warning('Login aborted: error downloading oauth2 configuration: %s', resp.status_code)
            abort(500)
        well_known_config = resp.json()

        if not (well_known_config and 'jwks_uri' in well_known_config):
            logging.warning('Login aborted: provider well-known config could not be fetched')
            abort(500)

        resp = requests.get(well_known_config['jwks_uri'])
        if resp.status_code != 200:
            logging.warning('Login aborted: error downloading JWKS: %s', resp.status_code)
            abort(500)
        oidc_jwk = resp.json()['keys'][0]
        if not oidc_jwk:
            logging.warning('Login aborted: JWK could not be fetched')
            abort(500)
    except requests.exceptions.RequestException as e:
        logging.warning('Login aborted: cannot download oauth2 configuration: %s', e)
        abort(500)

    userinfo = None
    try:
        oidc_userinfo_endpoint = well_known_config['userinfo_endpoint']
        userinfo = requests.get(
            oidc_userinfo_endpoint,
            headers={'Authorization': 'Bearer %s' % access_token}
        ).json()
        logging.debug('got userinfo %s', userinfo)
    except requests.exceptions.RequestException as e:
        logging.warning('Login aborted: cannot download userinfo: %s', e)
        abort(500)

    # verify idToken with the identity server's public key
    try:
        options = {'verify_aud': False, 'verify_at_hash': False}
        claims = jwt.decode(id_token, oidc_jwk, algorithms=['RS256'], options=options)
        logging.debug('got claims: %s', claims)
    except Exception as e:
        logging.error('Login aborted: JWT error: %s', e)
        abort(401)

    # check that claims include acr
    if 'acr' not in claims:
        logging.warning('Login aborted: No acr in claims')
        abort(422)

    # check that we have email from userinfo
    if 'email' in userinfo:
        email_id = userinfo['email']
    else:
        logging.warning('Login aborted: No valid email received')
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

    # check that the account has not been locked
    if selected_method.get('activateNsAccountLock', False):
        nal = userinfo.get('nsAccountLock')
        if isinstance(nal, str):
            nal = nal.lower() == 'true'
        if nal:
            logging.warning('Login aborted: Account is locked, email: "%s"', email_id)
            abort(422)

    # find the id attributes that can be used
    id_attribute_values = []
    for id_attribute in selected_method['idClaim'].split():
        id_attribute = id_attribute.strip()
        id_value = userinfo.get(id_attribute)
        if id_value:
            id_attribute_values.append((id_attribute, id_value))

    if not id_attribute_values:
        logging.warning('Login aborted: No attribute(s) "%s" for user id received, email "%s", method "%s"',
                        selected_method['idClaim'], email_id, selected_method['acr'])
        return "ERROR: We did not receive user identity from the login provider. " \
               "If this happens again, please contact support.", 422

    # Find existing user using id values, in priority order. In practice, we should not end up with multiple accounts
    # per external identity, but this could happen if the attributes come and go.
    user = None
    prefix = selected_method.get('prefix')
    for id_attribute_value in id_attribute_values:
        # construct ext_id from prefix, delimiter and user_id
        ext_id = prefix + EXT_ID_PREFIX_DELIMITER + id_attribute_value[1].lower()
        # fetch matching user object from the database
        user = User.query.filter_by(ext_id=ext_id).first()
        if user:
            logging.debug('Found existing user with id attribute %s, value %s' % id_attribute_value)
            break

    # New users: Send agreement to user to sign, create User object after signing
    if not user:
        if not args.agreement_sign:
            return render_terms_and_conditions()
        elif args.agreement_sign == 'signed':
            # create user using the highest priority id attribute value that was present in userinfo
            ext_id = prefix + EXT_ID_PREFIX_DELIMITER + id_attribute_values[0][1].lower()
            user = create_user(
                ext_id=ext_id,
                password=uuid.uuid4().hex,
                email_id=email_id,
                annotations=selected_method.get('userAnnotations')
            )
            user.tc_acceptance_date = datetime.now(timezone.utc)
            user.workspace_quota = selected_method.get('defaultWorkspaceQuota', 0)
            logging.info('Created new user with ext_id %s' % ext_id)
            db.session.commit()

    # Existing users: Check if agreement is accepted. If not send the terms to user.
    if user and not user.tc_acceptance_date:
        if not args.agreement_sign:
            return render_terms_and_conditions()
        elif args.agreement_sign == 'signed':
            user.tc_acceptance_date = datetime.now(timezone.utc)
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

    # create a session token
    session_token = user.generate_auth_token(current_app.config['SECRET_KEY'])

    return render_template(
        'login.html',
        token=session_token,
        username=ext_id,
        is_admin=user.is_admin,
        is_workspace_owner=user.is_workspace_owner,
        is_workspace_manager=is_workspace_manager(user),
        userid=user.id,
    )
