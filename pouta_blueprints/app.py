from flask import Flask
from flask.ext.mail import Mail

from pouta_blueprints.config import BaseConfig


def get_app():
    app = Flask(__name__)

    app.dynamic_config = BaseConfig()

    app.config.from_object(app.dynamic_config)

    mail = Mail()
    mail.init_app(app)

    return app
