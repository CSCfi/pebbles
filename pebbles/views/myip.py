from flask import Blueprint as FlaskBlueprint, request
from pebbles.server import restful
from pebbles.views.commons import auth


myip = FlaskBlueprint('myip', __name__)


class WhatIsMyIp(restful.Resource):
    @auth.login_required
    def get(self):
        if len(request.access_route) > 0:
            return {'ip': request.access_route[-1]}
        else:
            return {'ip': request.remote_addr}
