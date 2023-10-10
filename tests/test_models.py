# Test fixture methods to be called from app context so we can access the db
import base64
import json
import logging
import time

import pytest
from flask import Flask
from jose import jwt

from pebbles.models import PEBBLES_TAINT_KEY
from pebbles.models import User, Workspace, ApplicationTemplate, Application, ApplicationSession
from pebbles.models import db


@pytest.fixture()
def model_data(app: Flask):
    with app.app_context():
        md = ModelDataFixture()
        yield md
        db.session.remove()
        db.drop_all()


class ModelDataFixture:
    def __init__(self):
        db.create_all()
        u = User("user@example.org", "user", is_admin=False, email_id="user@example.org")
        self.known_user = u

        db.session.add(u)

        ws = Workspace('Workspace1')
        self.known_group = ws
        db.session.add(ws)

        t1 = ApplicationTemplate()
        t1.name = 'EnabledTestTemplate'
        t1.is_enabled = True
        t1.attribute_limits = [dict(name='maximum_lifetime', min=0, max=14400)]
        db.session.add(t1)
        self.known_template_id = t1.id

        b1 = Application()
        b1.name = "TestApplication"
        b1.template_id = t1.id
        b1.workspace_id = ws.id
        # b1.cost_multiplier = 1.5
        b1.config = {
            'cost_multiplier': '1.5'
        }
        self.known_application = b1
        db.session.add(b1)

        db.session.commit()


def test_ext_id_unification(model_data: ModelDataFixture):
    u1 = User("UsEr1@example.org", "user")
    u2 = User("User2@example.org", "user")
    db.session.add(u1)
    db.session.add(u2)
    x1 = User.query.filter_by(ext_id="USER1@EXAMPLE.ORG").first()
    x2 = User.query.filter_by(ext_id="user2@Example.org").first()
    assert u1 == x1
    assert u1.ext_id == x1.ext_id
    assert u2 == x2
    assert u2.ext_id == x2.ext_id


def test_add_duplicate_user_will_fail(model_data: ModelDataFixture):
    u1 = User("UsEr1@example.org", "user")
    db.session.add(u1)
    u2 = User("User1@example.org", "user")
    db.session.add(u2)
    with pytest.raises(Exception):
        db.session.commit()


def test_application_session_states(model_data: ModelDataFixture):
    i1 = ApplicationSession(model_data.known_application, model_data.known_user)
    for state in ApplicationSession.VALID_STATES:
        i1.state = state

    invalid_states = [x + 'foo' for x in ApplicationSession.VALID_STATES]
    invalid_states.append('')
    invalid_states.extend([x.upper() for x in ApplicationSession.VALID_STATES])

    for state in invalid_states:
        try:
            i1.state = state
            assert False, 'invalid state %s not detected' % state
        except ValueError:
            pass


def test_token_generation(model_data: ModelDataFixture):
    u1 = model_data.known_user
    token = u1.generate_auth_token('test_secret', expires_in=100)
    assert token is not None

    # check that issued at and expiration times are correct
    claims = jwt.get_unverified_claims(token)
    assert int(time.time()) - int(claims['iat']) <= 1
    assert int(claims['exp']) - int(claims['iat']) == 100

    user_res = User.verify_auth_token(token, 'test_secret')
    assert user_res
    assert user_res.id == model_data.known_user.id


def test_token_expiry(model_data: ModelDataFixture):
    u1 = model_data.known_user
    token = u1.generate_auth_token('test_secret', expires_in=0)
    assert token is not None

    logging.info('sleeping for a second to wait for expiry')
    time.sleep(1)

    user_res = User.verify_auth_token(token, 'test_secret')
    assert user_res is None


def test_token_forging_tamper_times(model_data: ModelDataFixture):
    # construct a token with signing algorithm set to 'none'

    claims = dict(
        id=model_data.known_user.id,
        iat=int(time.time()),
        exp=int(time.time() + 10000000),
    )

    # valid headers and signature from another token
    valid_token = model_data.known_user.generate_auth_token('test_secret')
    token = '%s.%s.%s' % (
        valid_token.split('.')[0],
        base64.urlsafe_b64encode(json.dumps(claims).encode('utf-8')).replace(b'=', b'').decode('utf-8'),
        valid_token.split('.')[2],
    )
    user_res = User.verify_auth_token(token, 'test_secret')
    assert user_res is None


def test_token_forging_algorithm(model_data: ModelDataFixture):
    # construct a token with signing algorithm set to 'none'
    headers = dict(
        alg='none',
        typ='JWT'
    )
    claims = dict(
        id=model_data.known_user.id,
        iat=int(time.time()),
        exp=int(time.time() + 100),
    )
    # first try without the last segment
    token = '%s.%s' % (
        base64.urlsafe_b64encode(json.dumps(headers).encode('utf-8')).replace(b'=', b'').decode('utf-8'),
        base64.urlsafe_b64encode(json.dumps(claims).encode('utf-8')).replace(b'=', b'').decode('utf-8'),
    )

    user_res = User.verify_auth_token(token, '')
    assert user_res is None

    # empty last segment
    token = '%s.%s.' % (
        base64.urlsafe_b64encode(json.dumps(headers).encode('utf-8')).replace(b'=', b'').decode('utf-8'),
        base64.urlsafe_b64encode(json.dumps(claims).encode('utf-8')).replace(b'=', b'').decode('utf-8'),
    )
    user_res = User.verify_auth_token(token, '')
    assert user_res is None

    # valid signature from another context
    valid_token = model_data.known_user.generate_auth_token('test_secret')
    token = '%s.%s.%s' % (
        base64.urlsafe_b64encode(json.dumps(headers).encode('utf-8')).replace(b'=', b'').decode('utf-8'),
        base64.urlsafe_b64encode(json.dumps(claims).encode('utf-8')).replace(b'=', b'').decode('utf-8'),
        valid_token.split('.')[2],
    )
    user_res = User.verify_auth_token(token, 'test_secret')
    assert user_res is None


def test_membership_expiry_policy_validation(model_data: ModelDataFixture):
    invalid_meps = [
        None,
        '',
        dict(),
        [],
        'kind: persistent',
        dict(foo='persistent'),
        dict(kind='persistent_foo'),
        dict(kind=Workspace.MEP_ACTIVITY_TIMEOUT),
        dict(kind=Workspace.MEP_ACTIVITY_TIMEOUT, timeout_days=-1),
        dict(kind=Workspace.MEP_ACTIVITY_TIMEOUT, timeout_days="60"),
    ]

    for mep in invalid_meps:
        res = Workspace.check_membership_expiry_policy(mep)
        if res:
            print(res)
        else:
            assert False, 'MEP should be detected as invalid: %s' % json.dumps(mep)

    valid_meps = [
        dict(kind=Workspace.MEP_PERSISTENT),
        dict(kind=Workspace.MEP_ACTIVITY_TIMEOUT, timeout_days=60),
    ]

    for mep in valid_meps:
        res = Workspace.check_membership_expiry_policy(mep)
        if res:
            assert False, 'MEP should be valid: %s, got error %s' % (json.dumps(mep), res)


def test_user_annotations(model_data: ModelDataFixture):
    u1 = User('user-1@example.org', 'user')
    u1.annotations = [
        dict(key='a1', value='v1'),
        dict(key=PEBBLES_TAINT_KEY, value='t1'),
        dict(key=PEBBLES_TAINT_KEY, value='t2'),
    ]
    db.session.add(u1)
    db.session.commit()
    u = User.query.filter_by(ext_id=u1.ext_id).first()
    assert u1.annotations == u.annotations
    assert u.taints == ['t1', 't2']

    # empty annotations
    u1.annotations = None
    db.session.commit()
    u = User.query.filter_by(ext_id=u1.ext_id).first()
    assert u.annotations == []
    assert u._annotations is None

    try:
        u1.annotations = dict(key='a1', value='v1')
        assert False, 'annotations should fail for a non-list'
    except RuntimeWarning:
        pass
