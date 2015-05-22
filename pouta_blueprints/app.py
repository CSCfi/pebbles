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
mail = Mail()
mail.init_app(app)

db.init_app(app)
with app.app_context():
    db.create_all()
