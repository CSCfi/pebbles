import sys

from flask import Flask

from pouta_blueprints.models import db, Variable
from pouta_blueprints.config import BaseConfig, TestConfig

app = Flask(__name__, static_url_path='')


# Setup static files to be served by Flask for automated testing
@app.route('/')
def root():
    return app.send_static_file('index.html')


@app.route('/favicon.ico')
def favicon():
    return app.send_static_file('favicon.ico')


test_run = set(['test', 'covtest']).intersection(set(sys.argv))

if test_run:
    app.dynamic_config = TestConfig()
else:
    app.dynamic_config = BaseConfig()

app.config.from_object(app.dynamic_config)

if app.config['ENABLE_SHIBBOLETH_LOGIN']:
    SSO_ATTRIBUTE_MAP = {
        "HTTP_AJP_SHIB_MAIL": (False, "mail"),
        "HTTP_AJP_SHIB_EPPN": (True, "eppn"),
    }
    app.config.setdefault('SSO_ATTRIBUTE_MAP', SSO_ATTRIBUTE_MAP)
    app.config.setdefault('SSO_LOGIN_URL', '/login')
    app.config.setdefault('PREFERRED_URL_SCHEME', 'https')

db.init_app(app)
with app.app_context():
    db.create_all()

    # Do not populate variables into DB when running tests, as these are
    # populated during the test case setup phase.
    if not test_run:
        Variable.sync_local_config_to_db(BaseConfig, app.dynamic_config)
