import json
import logging

import flask_restful as restful
from flask import Blueprint as FlaskBlueprint

from pebbles.views.commons import auth

app_version = FlaskBlueprint('app_version', __name__)


class AppVersionList(restful.Resource):
    """ Get application build version that has been baked into the image"""

    # cache version json to avoid subsequent reads
    app_version_data = None

    @auth.login_required
    def get(self):
        try:
            if AppVersionList.app_version_data is None:
                with open('app-version.json', 'r') as version_file:
                    AppVersionList.app_version = json.loads(version_file.read())
            return AppVersionList.app_version
        except Exception as e:
            logging.warning(e)
            return dict(appVersion='not-set')
