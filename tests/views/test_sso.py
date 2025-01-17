import base64
import json
import os
import time
from datetime import timezone, datetime

import responses
import yaml
from Crypto.PublicKey import RSA
from flask import current_app
from jose import jwt
from pyfakefs.fake_filesystem_unittest import Patcher

from pebbles.models import PEBBLES_TAINT_KEY
from pebbles.models import User, WorkspaceMembership
from pebbles.models import db
from tests.conftest import PrimaryData

# generate key in module load instead of setUp() to speed things up
private_key = RSA.generate(2048)
public_key = private_key.public_key()

AUTH_CONFIG = dict(
    oauth2=dict(
        openidConfigurationUrl='https://example.org/.well-known-configuration',
        authMethods=[
            dict(
                acr='https://example.org/Method_1',
                idClaim='userid',
                prefix='ex1',
            ),
            dict(
                acr='https://example.org/Method_2',
                idClaim='userid username eppn',
                prefix='ex2',
                activateNsAccountLock=True,
            ),
            dict(
                acr='https://example.org/Method_3',
                idClaim='userid username eppn',
                prefix='ex3',
                userAnnotations=[
                    dict(key=PEBBLES_TAINT_KEY, value='low_trust'),
                ],
            ),
        ]
    )
)

TERMS_HTML = 'TERMS {{ title }}'
LOGIN_HTML = 'LOGIN {{ username }} {{ token }} '


def create_id_token(claims=None, key=None, algorithm='RS256'):
    if not claims:
        claims = dict(
            acr='https://example.org/Method_1',
        )
    if not key:
        key = private_key.export_key().decode('UTF-8')

    return jwt.encode(
        claims=claims,
        key=key,
        algorithm=algorithm
    )


def add_default_responses():
    responses.add(
        responses.GET,
        'https://example.org/.well-known-configuration',
        json=dict(jwks_uri='https://example.org/jwks', userinfo_endpoint='https://example.org/userinfo'),
        status=200,
    )
    responses.add(
        responses.GET,
        'https://example.org/jwks',
        json=dict(keys=[public_key.export_key().decode('UTF-8')]),
        status=200,
    )
    responses.add(
        responses.GET,
        'https://example.org/userinfo',
        json=dict(
            userid='user-1',
            email='user-1@example.org',
        ),
        status=200,
    )


def make_request(method='GET', path='/', headers=None, data=None):
    if not headers:
        headers = {}

    if 'Content-Type' not in headers:
        headers['Content-Type'] = 'application/json'

    header_tuples = [(x, y) for x, y in headers.items()]
    if method == 'GET':
        return current_app.test_client().get(path, headers=header_tuples, data=data, content_type='application/json')
    elif method == 'POST':
        return current_app.test_client().post(path, headers=header_tuples, data=data, content_type='application/json')
    else:
        raise NotImplementedError('Method %s not implemented' % method)


def make_mocked_request(**kwargs):
    current_app.config['OAUTH2_LOGIN_ENABLED'] = True
    current_app.config['API_AUTH_CONFIG_FILE'] = 'auth-config.yaml'

    if 'id_token' not in kwargs:
        id_token = create_id_token()
    else:
        id_token = kwargs.pop('id_token')

    access_token = '12341234'
    if 'headers' not in kwargs:
        kwargs['headers'] = {'Authorization': 'Basic %s ' % id_token, 'X-Forwarded-Access-Token': access_token}

    with Patcher() as patcher:
        patcher.fs.create_file('auth-config.yaml', contents=yaml.dump(AUTH_CONFIG))
        template_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../pebbles/templates'))
        # patcher.fs.add_real_directory(template_dir)
        patcher.fs.create_file(os.path.join(template_dir, 'terms.html'), contents=TERMS_HTML)
        patcher.fs.create_file(os.path.join(template_dir, 'login.html'), contents=LOGIN_HTML)
        return make_request(**kwargs)


def test_sso_disabled(pri_data: PrimaryData):
    add_default_responses()
    res = make_request(path='/oauth2')
    assert res.status_code == 401


def test_sso_no_auth_config(pri_data: PrimaryData):
    add_default_responses()
    current_app.config['OAUTH2_LOGIN_ENABLED'] = True
    res = make_request(path='/oauth2')
    assert res.status_code == 500


def test_sso_no_auth_header(pri_data: PrimaryData):
    add_default_responses()
    res = make_mocked_request(path='/oauth2', headers={})
    assert res.status_code == 500


def test_sso_no_access_token(pri_data: PrimaryData):
    add_default_responses()
    res = make_mocked_request(path='/oauth2', headers=dict(Authorization='Basic foo'))
    assert res.status_code == 500


@responses.activate
def test_sso_missing_well_known_config(pri_data: PrimaryData):
    add_default_responses()
    responses.replace(
        responses.GET,
        'https://example.org/.well-known-configuration',
        json={'error': 'not found'},
        status=404,
    )
    res = make_mocked_request(
        path='/oauth2',
        headers={'Authorization': 'Basic foo', 'X-Forwarded-Access-Token': 'bar'})
    assert res.status_code == 500


@responses.activate
def test_sso_missing_jwks(pri_data: PrimaryData):
    add_default_responses()
    responses.replace(
        responses.GET,
        'https://example.org/jwks',
        status=404,
    )

    res = make_mocked_request(
        path='/oauth2',
        headers={'Authorization': 'Basic foo', 'X-Forwarded-Access-Token': 'bar'})
    assert res.status_code == 500


@responses.activate
def test_sso_missing_userinfo(pri_data: PrimaryData):
    add_default_responses()
    responses.replace(
        responses.GET,
        'https://example.org/userinfo',
        status=404,
    )

    res = make_mocked_request(
        path='/oauth2',
        headers={'Authorization': 'Basic foo', 'X-Forwarded-Access-Token': 'bar'})
    assert res.status_code == 500


@responses.activate
def test_sso_success(pri_data: PrimaryData):
    add_default_responses()
    # new user, need to agree to terms and conditions
    res = make_mocked_request(
        path='/oauth2',
    )
    assert res.status_code == 200
    assert 'TERMS' in res.text
    assert not User.query.filter_by(ext_id='ex1/user-1').first()

    # agree to ToC and check that user was created
    res = make_mocked_request(
        path='/oauth2?agreement_sign=signed',
    )
    assert res.status_code == 200
    assert 'LOGIN' in res.text
    assert 'ex1/user-1' in res.text
    u = User.query.filter_by(ext_id='ex1/user-1').first()
    assert u
    assert len(WorkspaceMembership.query.filter_by(user_id=u.id).all()) == 1


@responses.activate
def test_missing_id_claim(pri_data: PrimaryData):
    add_default_responses()
    responses.replace(
        responses.GET,
        'https://example.org/userinfo',
        json=dict(
            login='user-1',
            email='user-1@example.org',
        ),
        status=200,
    )
    res = make_mocked_request(
        path='/oauth2',
    )
    assert res.status_code == 422


@responses.activate
def test_account_locking(pri_data: PrimaryData):
    add_default_responses()
    # account has been locked, but locking is not activated by default
    responses.replace(
        responses.GET,
        'https://example.org/userinfo',
        json=dict(
            userid='user-1',
            email='user-1@example.org',
            nsAccountLock='true'
        ),
        status=200,
    )
    res = make_mocked_request(path='/oauth2')
    assert res.status_code == 200

    # token for second login method
    id_token_m2 = create_id_token(claims=dict(acr='https://example.org/Method_2'))

    # account has been locked, and lock processing has been activated on second login method
    res = make_mocked_request(path='/oauth2', id_token=id_token_m2)
    assert res.status_code == 422
    # locking with a boolean
    responses.replace(
        responses.GET,
        'https://example.org/userinfo',
        json=dict(
            userid='user-1',
            email='user-1@example.org',
            nsAccountLock=True
        ),
        status=200,
    )
    res = make_mocked_request(path='/oauth2', id_token=id_token_m2)
    assert res.status_code == 422
    # explicitly telling not to enable locking
    responses.replace(
        responses.GET,
        'https://example.org/userinfo',
        json=dict(
            userid='user-1',
            email='user-1@example.org',
            nsAccountLock='false'
        ),
        status=200,
    )
    res = make_mocked_request(path='/oauth2', id_token=id_token_m2)
    assert res.status_code == 200


@responses.activate
def test_wrong_acr(pri_data: PrimaryData):
    add_default_responses()

    # no such acr in config
    id_token = create_id_token(claims=dict(acr='https://example.org/Method'))
    res = make_mocked_request(path='/oauth2', id_token=id_token)
    assert res.status_code == 422

    # missing acr attribute
    id_token = create_id_token(claims=dict(foo='https://example.org/Method'))
    res = make_mocked_request(path='/oauth2', id_token=id_token)
    assert res.status_code == 422


@responses.activate
def test_wrong_signature(pri_data: PrimaryData):
    add_default_responses()

    # wrong key
    id_token = create_id_token(
        claims=dict(acr='https://example.org/Method_1'),
        key=RSA.generate(2048).export_key(),
    )
    res = make_mocked_request(path='/oauth2', id_token=id_token)
    assert res.status_code == 401

    # tamper valid token and check that it works
    id_token = create_id_token()
    res = make_mocked_request(path='/oauth2', id_token=id_token)
    assert res.status_code == 200
    # change claims
    claims = dict(acr='https://example.org/Method_2')
    forged_token = '%s.%s.%s' % (
        id_token.split('.')[0],
        base64.urlsafe_b64encode(json.dumps(claims).encode('utf-8')).replace(b'=', b'').decode('utf-8'),
        id_token.split('.')[2],
    )
    res = make_mocked_request(path='/oauth2', id_token=forged_token)
    assert res.status_code == 401


@responses.activate
def test_existing_user(pri_data: PrimaryData):
    add_default_responses()

    u1 = User('ex1/user-1')
    u1.tc_acceptance_date = datetime.now(timezone.utc)
    db.session.add(u1)
    db.session.commit()

    # existing user
    res = make_mocked_request(
        path='/oauth2',
    )
    assert res.status_code == 200
    assert 'LOGIN' in res.text
    assert 'ex1/user-1' in res.text
    assert User.query.filter_by(ext_id='ex1/user-1').first().last_login_ts > time.time() - 1


@responses.activate
def test_existing_user_toc_not_signed(pri_data: PrimaryData):
    add_default_responses()

    u1 = User('ex1/user-1')
    db.session.add(u1)
    db.session.commit()

    # existing user bounced back to ToC dialog
    res = make_mocked_request(
        path='/oauth2',
    )
    assert res.status_code == 200
    assert 'TERMS' in res.text

    # existing user agrees to ToC
    res = make_mocked_request(
        path='/oauth2?agreement_sign=signed',
    )
    assert res.status_code == 200
    assert 'LOGIN' in res.text
    assert 'ex1/user-1' in res.text


@responses.activate
def test_existing_user_with_tertiary_id_attribute(pri_data: PrimaryData):
    add_default_responses()

    # test that tertiary id attribute picks up existing user created with eppn
    u1 = User('ex2/user-1@example.org')
    u1.tc_acceptance_date = datetime.now(timezone.utc)
    db.session.add(u1)
    db.session.commit()

    id_token = create_id_token(
        claims=dict(acr='https://example.org/Method_2'),
    )
    responses.replace(
        responses.GET,
        'https://example.org/userinfo',
        json=dict(
            userid='user-1',
            username='exauser1',
            eppn='user-1@example.org',
            email='user-1@example.org',
        ),
        status=200,
    )
    res = make_mocked_request(
        path='/oauth2',
        id_token=id_token
    )
    assert 'LOGIN' in res.text
    assert 'ex2/user-1@example.org' in res.text


@responses.activate
def test_require_email_in_userinfo(pri_data: PrimaryData):
    add_default_responses()

    responses.replace(
        responses.GET,
        'https://example.org/userinfo',
        json=dict(
            userid='user-1',
            username='exauser1',
            eppn='user-1@example.org',
        ),
        status=200,
    )
    res = make_mocked_request(
        path='/oauth2',
    )
    assert res.status_code == 422


@responses.activate
def test_blocked_user_cannot_log_in(pri_data: PrimaryData):
    add_default_responses()

    # Add the default user in advance to the database and mark it blocked. Login should be denied.
    u1 = User('ex1/user-1')
    u1.tc_acceptance_date = datetime.now(timezone.utc)
    u1.is_blocked = True
    db.session.add(u1)
    db.session.commit()

    res = make_mocked_request(
        path='/oauth2',
    )
    assert res.status_code == 403


@responses.activate
def test_user_annotations(pri_data: PrimaryData):
    add_default_responses()

    id_token = create_id_token(
        claims=dict(acr='https://example.org/Method_3'),
    )
    res = make_mocked_request(
        path='/oauth2?agreement_sign=signed',
        id_token=id_token,
    )
    assert res.status_code == 200
    u = User.query.filter_by(ext_id='ex3/user-1').first()
    assert 'LOGIN' in res.text
    assert u.annotations == AUTH_CONFIG['oauth2']['authMethods'][2]['userAnnotations']

    # Because of taints, user should not be a member of System.default workspace
    assert len(WorkspaceMembership.query.filter_by(user_id=u.id).all()) == 0
