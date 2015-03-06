from flask import Flask
from flask.ext.mail import Mail


def get_app():
    app = Flask(__name__)
    app.config.from_object('pouta_blueprints.config.DevConfig')

    mail = Mail()
    mail.init_app(app)

    return app
