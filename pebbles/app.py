import logging
import os as os

from flask import Flask
from flask_migrate import Migrate

from pebbles.config import TestConfig, RuntimeConfig
from pebbles.models import db, bcrypt
from pebbles.utils import init_logging

app = Flask(__name__, static_url_path='')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# initialize migrations with Alembic
migrate = Migrate(app, db)


if 'REMOTE_DEBUG_SERVER' in os.environ:
    print('trying to connect to remote debug server at %s ' % os.environ['REMOTE_DEBUG_SERVER'])
    import pydevd_pycharm

    pydevd_pycharm.settrace(
        host=os.environ['REMOTE_DEBUG_SERVER'],
        port=os.environ.get('REMOTE_DEBUG_PORT', 12345),
        stdoutToServer=True,
        stderrToServer=True,
        suspend=False
    )
    print('API: connected to remote debug server at %s ' % os.environ['REMOTE_DEBUG_SERVER'])


# Setup route for readiness/liveness probe check
@app.route('/healthz')
def healthz():
    return 'ok'


@app.route('/favicon.ico')
def favicon():
    return app.send_static_file('favicon.ico')


@app.after_request
def add_headers(r):
    r.headers['X-Content-Type-Options'] = 'nosniff'
    r.headers['X-XSS-Protection'] = '1; mode=block'
    r.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    r.headers['Pragma'] = 'no-cache'
    r.headers['Expires'] = '0'
    r.headers['Strict-Transport-Security'] = 'max-age=31536000'
    # does not work without unsafe-inline / unsafe-eval
    csp_list = [
        "img-src 'self' data:",
        "script-src 'self' 'unsafe-inline' 'unsafe-eval'",
        "style-src 'self' 'unsafe-inline'",
        "default-src 'self'",
    ]
    r.headers['Content-Security-Policy'] = '; '.join(csp_list)

    # Sometimes we need to allow additional domains in CORS during UI development.
    # Do not set this in production.
    if 'DISABLE_CORS' in os.environ and os.environ['DISABLE_CORS']:
        r.headers['Access-Control-Allow-Origin'] = '*'
        r.headers['Access-Control-Allow-Headers'] = '*'
        r.headers['Access-Control-Allow-Methods'] = '*'

    return r


# unit tests need a config with tweaked default values and no environment variable resolving - unit tests can be run
# in a container that has environment set up for real
if os.environ.get('UNITTEST') == '1':
    app_config = TestConfig()
else:
    app_config = RuntimeConfig()

# set up logging
init_logging(app_config, 'api')

# configure flask
app.config.from_object(app_config)

# insert database password to SQLALCHEMY_DATABASE_URI from a separate source
if app.config['DATABASE_PASSWORD']:
    app.config['SQLALCHEMY_DATABASE_URI'] = app.config['SQLALCHEMY_DATABASE_URI'].replace('__PASSWORD__', app.config[
        'DATABASE_PASSWORD'])

bcrypt.init_app(app)
db.init_app(app)

# Enable debugging SQLAlchemy queries. Level must be set as an integer, take a look at logging constants for values.
# https://docs.python.org/3.9/library/logging.html#logging-levels
# Hint: logging.INFO (=20) gives you SQL output for each query
if 'SQLALCHEMY_LOGGING_LEVEL' in os.environ:
    logging.getLogger("sqlalchemy.engine").setLevel(int(os.environ.get('SQLALCHEMY_LOGGING_LEVEL')))
