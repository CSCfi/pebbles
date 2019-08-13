import os as os
import sys

from flask import Flask
from flask_migrate import Migrate
from flask_migrate import upgrade as flask_upgrade_db_to_head

from pebbles.config import BaseConfig, TestConfig
from pebbles.models import db, bcrypt, Plugin

from pebbles.drivers.provisioning import dummy_driver_config


app = Flask(__name__, static_url_path='')
migrate = Migrate(app, db)

if 'REMOTE_DEBUG_SERVER' in os.environ:
    print('trying to connect to remote debug server at %s ' % os.environ['REMOTE_DEBUG_SERVER'])
    import pydevd_pycharm
    pydevd_pycharm.settrace(os.environ['REMOTE_DEBUG_SERVER'], port=12345, stdoutToServer=True, stderrToServer=True,
                            suspend=False)
    print('connected to remote debug server at %s ' % os.environ['REMOTE_DEBUG_SERVER'])


# Setup static files to be served by Flask for automated testing
@app.route('/')
def root():
    return app.send_static_file('index.html')


@app.route('/favicon.ico')
def favicon():
    return app.send_static_file('favicon.ico')


@app.after_request
def add_header(r):
    r.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    r.headers["Pragma"] = "no-cache"
    r.headers["Expires"] = "0"
    r.headers['Strict-Transport-Security'] = 'max-age=31536000'
    # does not work without unsafe-inline / unsafe-eval
    r.headers[
        'Content-Security-Policy'] = "img-src 'self' data:; script-src 'self' 'unsafe-inline' 'unsafe-eval'; connect-src 'self' wss://{{ domain_name }} ; style-src 'self' 'unsafe-inline'; default-src 'self'"

    return r


test_run = set(['test', 'covtest']).intersection(set(sys.argv)) or 'UNIT_TEST' in os.environ.keys()

if test_run:
    app.dynamic_config = TestConfig()
else:
    app.dynamic_config = BaseConfig()

app.config.from_object(app.dynamic_config)

# insert database password from separate source to SQLALCHEMY URL
if app.config['DATABASE_PASSWORD']:
    app.config['SQLALCHEMY_DATABASE_URI'] = app.config['SQLALCHEMY_DATABASE_URI'].replace('__PASSWORD__', app.config[
        'DATABASE_PASSWORD'])

if app.config['ENABLE_SHIBBOLETH_LOGIN']:
    SSO_ATTRIBUTE_MAP = {
        "HTTP_AJP_SHIB_MAIL": (True, "email_id"),
        "HTTP_AJP_SHIB_EPPN": (True, "eppn"),
    }
    app.config.setdefault('SSO_ATTRIBUTE_MAP', SSO_ATTRIBUTE_MAP)
    app.config.setdefault('SSO_LOGIN_URL', '/login')
    app.config.setdefault('PREFERRED_URL_SCHEME', 'https')

bcrypt.init_app(app)
db.init_app(app)

def run_things_in_context(is_test_run):
    # This is only split into a function so we can easily test some of it's
    # behavior.
    with app.app_context():
        # upgrade to the head of the migration path (the default)
        # we might want to pass a particular revision id instead
        # in the future
        if os.environ.get("DB_AUTOMIGRATION", None) and \
                os.environ.get("DB_AUTOMIGRATION", None) not in ["0", 0] and \
                not is_test_run:
            flask_upgrade_db_to_head()

        # initialize plugins
        if not is_test_run:
            plugins = Plugin.query.all()
            if len(plugins) == 0:
                plugin = Plugin()
                plugin.name = 'DummyDriver'
                plugin.id = 1
                plugin.schema = dummy_driver_config.CONFIG['schema']
                plugin.form = dummy_driver_config.CONFIG['form']
                plugin.model = dummy_driver_config.CONFIG['model']
                db.session.add(plugin)
                db.session.commit()



run_things_in_context(test_run)
