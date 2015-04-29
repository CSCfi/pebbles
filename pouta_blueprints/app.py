from flask import Flask
from flask.ext.mail import Mail

from pouta_blueprints.models import db
from pouta_blueprints.config import BaseConfig

app = Flask(__name__)
app.dynamic_config = BaseConfig()
app.config.from_object(app.dynamic_config)
mail = Mail()
mail.init_app(app)

db.init_app(app)
with app.app_context():
    db.create_all()
