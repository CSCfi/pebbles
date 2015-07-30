import sys

from flask import Flask
from flask.ext.mail import Mail

from pouta_blueprints.models import db
from pouta_blueprints.config import BaseConfig, TestConfig

app = Flask(__name__)

if set(['test', 'covtest']).intersection(set(sys.argv)):
    app.dynamic_config = TestConfig()
else:
    app.dynamic_config = BaseConfig()

app.config.from_object(app.dynamic_config)

if app.config['ENABLE_SHIBBOLETH_LOGIN']:
    SSO_ATTRIBUTE_MAP = {
        "HTTP_AJP_SHIB_UID": (True, "uid"),
        "HTTP_AJP_SHIB_MAIL": (True, "mail"),
        "HTTP_AJP_SHIB_DISPLAYNAME": (False, "name")
    }
    app.config.setdefault('SSO_ATTRIBUTE_MAP', SSO_ATTRIBUTE_MAP)
    app.config.setdefault('SSO_LOGIN_URL', '/login')
    app.config.setdefault('PREFERRED_URL_SCHEME', 'https')

mail = Mail()
mail.init_app(app)

db.init_app(app)
with app.app_context():
    db.create_all()
