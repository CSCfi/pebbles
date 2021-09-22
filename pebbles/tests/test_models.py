import base64
import json
import logging
import time

from jose import jwt

from pebbles.models import User, Workspace, Environment, EnvironmentTemplate, EnvironmentSession
from pebbles.tests.base import db, BaseTestCase


class ModelsTestCase(BaseTestCase):
    def setUp(self):
        db.create_all()
        u = User("user@example.org", "user", is_admin=False, email_id="user@example.org")
        self.known_user = u

        db.session.add(u)

        ws = Workspace('Workspace1')
        self.known_group = ws
        db.session.add(ws)

        t1 = EnvironmentTemplate()
        t1.name = 'EnabledTestTemplate'
        t1.is_enabled = True
        t1.allowed_attrs = ['cost_multiplier']
        db.session.add(t1)
        self.known_template_id = t1.id

        b1 = Environment()
        b1.name = "TestEnvironment"
        b1.template_id = t1.id
        b1.workspace_id = ws.id
        # b1.cost_multiplier = 1.5
        b1.config = {
            'cost_multiplier': '1.5'
        }
        self.known_environment = b1
        db.session.add(b1)

        db.session.commit()

    def test_ext_id_unification(self):
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

    def test_add_duplicate_user_will_fail(self):
        u1 = User("UsEr1@example.org", "user")
        db.session.add(u1)
        u2 = User("User1@example.org", "user")
        db.session.add(u2)
        with self.assertRaises(Exception):
            db.session.commit()

    def test_environment_session_states(self):
        i1 = EnvironmentSession(self.known_environment, self.known_user)
        for state in EnvironmentSession.VALID_STATES:
            i1.state = state

        invalid_states = [x + 'foo' for x in EnvironmentSession.VALID_STATES]
        invalid_states.append('')
        invalid_states.extend([x.upper() for x in EnvironmentSession.VALID_STATES])

        for state in invalid_states:
            try:
                i1.state = state
                self.fail('invalid state %s not detected' % state)
            except ValueError:
                pass

    def test_token_generation(self):
        u1 = self.known_user
        token = u1.generate_auth_token('test_secret', expires_in=100)
        assert token is not None

        # check that issued at and expiration times are correct
        claims = jwt.get_unverified_claims(token)
        assert int(time.time()) - int(claims['iat']) <= 1
        assert int(claims['exp']) - int(claims['iat']) == 100

        user_res = User.verify_auth_token(token, 'test_secret')
        assert user_res
        assert user_res.id == self.known_user.id

    def test_token_expiry(self):
        u1 = self.known_user
        token = u1.generate_auth_token('test_secret', expires_in=0)
        assert token is not None

        logging.info('sleeping for a second to wait for expiry')
        time.sleep(1)

        user_res = User.verify_auth_token(token, 'test_secret')
        assert user_res is None

    def test_token_forging_tamper_times(self):
        # construct a token with signing algorithm set to 'none'

        claims = dict(
            id=self.known_user.id,
            iat=int(time.time()),
            exp=int(time.time() + 10000000),
        )

        # valid headers and signature from another token
        valid_token = self.known_user.generate_auth_token('test_secret')
        token = '%s.%s.%s' % (
            valid_token.split('.')[0],
            base64.urlsafe_b64encode(json.dumps(claims).encode('utf-8')).replace(b'=', b'').decode('utf-8'),
            valid_token.split('.')[2],
        )
        user_res = User.verify_auth_token(token, 'test_secret')
        assert user_res is None

    def test_token_forging_algorithm(self):
        # construct a token with signing algorithm set to 'none'
        headers = dict(
            alg='none',
            typ='JWT'
        )
        claims = dict(
            id=self.known_user.id,
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
        valid_token = self.known_user.generate_auth_token('test_secret')
        token = '%s.%s.%s' % (
            base64.urlsafe_b64encode(json.dumps(headers).encode('utf-8')).replace(b'=', b'').decode('utf-8'),
            base64.urlsafe_b64encode(json.dumps(claims).encode('utf-8')).replace(b'=', b'').decode('utf-8'),
            valid_token.split('.')[2],
        )
        user_res = User.verify_auth_token(token, 'test_secret')
        assert user_res is None
