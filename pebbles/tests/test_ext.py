from unittest import TestCase
from flask import Flask
from collections import OrderedDict
from contextlib import contextmanager
from flask import request_started, request
from flask_sso import SSO


class TestSSO(TestCase):
    """
    Tests SSO logins
    """
    def setUp(self):
        app = Flask(__name__)
        app.config['DEBUG'] = True
        app.config['TESTING'] = True
        app.logger.disabled = True
        self.app = app

    def test_login_handler(self):
        sso = SSO(app=self.app)

        @sso.login_handler
        def _callback(attr):
            od = OrderedDict()
            for k, v in sorted(attr.items()):
                od[k] = v
            return '{0}'.format(od).encode('latin-1')

        @contextmanager
        def request_environ_set(app, data):

            def handler(sender, **kwargs):
                for (k, v) in data.items():
                    request.environ[k] = v

            with request_started.connected_to(handler, app):
                yield

        def run(conf, data, expected_data):
            self.app.config['SSO_ATTRIBUTE_MAP'] = conf
            with request_environ_set(self.app, data):
                with self.app.test_client() as c:
                    resp = c.get(self.app.config['SSO_LOGIN_URL'])
                    od = OrderedDict()
                    for k, v in sorted(expected_data.items()):
                        od[k] = v
                    self.assertEqual(resp.data, '{0}'.format(od).encode('latin-1'))

        conf = {'HTTP_AJP_SHIB_EPPN': (True, 'eppn'), 'HTTP_AJP_SHIB_MAIL': (False, 'mail')}
        data = {'HTTP_AJP_SHIB_EPPN': 'user@example.org'}
        expected_data = {'eppn': 'user@example.org', 'mail': None}

        run(conf, data, expected_data)

        conf = {'HTTP_AJP_SHIB_EPPN': (True, 'eppn'), 'HTTP_AJP_SHIB_MAIL': (False, 'mail')}
        data = {'HTTP_AJP_SHIB_EPPN': None}
        expected_data = {'eppn': None, 'mail': None}

        @sso.login_handler
        def _callback_redef(attr):
            assert False

        @sso.login_error_handler
        def _callback_error(attr):
            od = OrderedDict()
            for k, v in sorted(attr.items()):
                od[k] = v
            return '{0}'.format(od)

        run(conf, data, expected_data)
