# Test fixture methods to be called from app context so we can access the db
import base64
import json
import logging
import time

import pytest
from flask import Flask
from jose import jwt

from pebbles import models
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
        self.known_workspace = ws
        db.session.add(ws)

        t1 = ApplicationTemplate()
        t1.name = 'EnabledTestTemplate'
        t1.is_enabled = True
        t1.attribute_limits = [dict(name='maximum_lifetime', min=0, max=14400)]
        db.session.add(t1)
        self.known_template_id = t1.id

        a1 = Application()
        a1.name = "TestApplication"
        a1.template_id = t1.id
        a1.workspace_id = ws.id
        # a1.cost_multiplier = 1.5
        a1.config = {
            'cost_multiplier': '1.5'
        }
        self.known_application = a1
        db.session.add(a1)

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
    s1 = ApplicationSession(model_data.known_application, model_data.known_user)
    for state in ApplicationSession.VALID_STATES:
        s1.state = state

    invalid_states = [x + 'foo' for x in ApplicationSession.VALID_STATES]
    invalid_states.append('')
    invalid_states.extend([x.upper() for x in ApplicationSession.VALID_STATES])

    for state in invalid_states:
        try:
            s1.state = state
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


def test_application_session_name_generation():
    """
    Test that application session name generation does not return the same
    name too often by generating 1000 names and making sure that the result
    is at least 990 unique names.
    """
    names = {ApplicationSession.generate_name("pb") for _ in range(1000)}
    assert len(names) > 990


def test_list_active_applications(model_data: ModelDataFixture):
    a2 = Application()
    a2.name = 'TestApplication 2'
    a2.template_id = model_data.known_template_id
    a2.workspace_id = model_data.known_workspace.id
    a2.base_config = dict(image='example.org/foo/bar:latest', memory_gib=1)
    a2.config = dict(image_url='example.org/foo/bar:latest', memory_gib=2)
    db.session.add(a2)

    db.session.commit()

    # two active applications in the database now
    assert (set([x.id for x in models.list_active_applications()]) == set([a2.id, model_data.known_application.id]))

    # set one deleted
    a2.status = Application.STATUS_DELETED
    db.session.commit()

    assert (set([x.id for x in models.list_active_applications()]) == set([model_data.known_application.id]))

    # add another active workspace to play with
    w2 = Workspace('TestWorkspace 2')
    db.session.add(w2)
    # add application to the new workspace
    a3 = Application()
    a3.name = 'TestApplication 3'
    a3.template_id = model_data.known_template_id
    a3.workspace_id = w2.id
    a3.base_config = dict(image='example.org/foo/bar:latest', memory_gib=1)
    a3.config = dict(image_url='example.org/foo/bar:latest', memory_gib=2)
    db.session.add(a3)

    db.session.commit()

    # two active applications
    assert (set([x.id for x in models.list_active_applications()]) == set([model_data.known_application.id, a3.id]))

    # archive workspace
    w2.status = Workspace.STATUS_ARCHIVED
    assert (set([x.id for x in models.list_active_applications()]) == set([model_data.known_application.id]))

    # set active again
    w2.status = Workspace.STATUS_ACTIVE
    assert (set([x.id for x in models.list_active_applications()]) == set([model_data.known_application.id, a3.id]))

    # make the workspace expired
    w2.expiry_ts = w2.create_ts
    assert (set([x.id for x in models.list_active_applications()]) == set([model_data.known_application.id]))


def test_replace_application_image(model_data: ModelDataFixture):
    a2 = Application()
    a2.name = "TestApplication 2"
    a2.template_id = model_data.known_template_id
    a2.workspace_id = model_data.known_workspace.id
    a2.base_config = dict(image='example.org/foo/bar:latest', memory_gib=1)
    a2.config = dict(image_url='example.org/foo/bar:latest', memory_gib=2)
    db.session.add(a2)

    # replace both image references, other keys should not be affected
    a2.replace_application_image('example.org/foo/bar:latest', 'example.org/foo/bar:next')
    assert a2.base_config == dict(image='example.org/foo/bar:next', memory_gib=1)
    assert a2.config == dict(image_url='example.org/foo/bar:next', memory_gib=2)

    # only base_config has image defined
    a2.config = dict(hello='world')
    a2.base_config = dict(image='example.org/foo/bar:latest')
    a2.replace_application_image('example.org/foo/bar:latest', 'example.org/foo/bar:next')
    assert a2.config == dict(hello='world')
    assert a2.base_config == dict(image='example.org/foo/bar:next')

    # only config matches
    a2.config = dict(image_url='example.org/foo/bar:latest')
    a2.base_config = dict(image='example.org/other/image:latest')
    a2.replace_application_image('example.org/foo/bar:latest', 'example.org/foo/bar:next')
    assert a2.config == dict(image_url='example.org/foo/bar:next')
    assert a2.base_config == dict(image='example.org/other/image:latest')

    # no match
    a2.config = dict(image_url='example.org/foo/bar:stable')
    a2.base_config = dict(image='example.org/foo/bar:stable')
    a2.replace_application_image('example.org/foo/bar:latest', 'example.org/foo/bar:next')
    assert a2.config == dict(image_url='example.org/foo/bar:stable')
    assert a2.base_config == dict(image='example.org/foo/bar:stable')

    # prefix should not match
    a2.config = dict(image_url='example.org/foo/bar:stable')
    a2.base_config = dict(image='example.org/foo/bar:stable')
    a2.replace_application_image('example.org/foo/bar', 'example.org/foo/bar:next')
    assert a2.config == dict(image_url='example.org/foo/bar:stable')
    assert a2.base_config == dict(image='example.org/foo/bar:stable')
