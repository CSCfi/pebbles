import logging

import flask_restful as restful
import yaml
from flask import Blueprint as FlaskBlueprint

from pebbles.app import app
from pebbles.views.commons import auth

helps = FlaskBlueprint('helps', __name__)


class HelpsList(restful.Resource):

    @auth.login_required
    def get(self):
        try:
            faq_config = yaml.safe_load(open(app.config['API_FAQ_FILE']))
            return faq_config
        except Exception as e:
            logging.warning(e)
            return None
