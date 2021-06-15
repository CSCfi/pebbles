from flask import Blueprint as FlaskBlueprint
import flask_restful as restful
from pebbles.views.commons import auth
import logging
import yaml

helps = FlaskBlueprint('helps', __name__)


class HelpsList(restful.Resource):

    @auth.login_required
    def get(self):
        try:
            faq_config = yaml.load(open('/run/configmaps/pebbles/api-configmap/faq-content.yaml'))
            return faq_config
        except Exception as e:
            logging.warning(e)
            return None
