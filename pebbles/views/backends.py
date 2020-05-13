from flask import Blueprint as FlaskBlueprint
from flask_restful import fields, marshal_with

import flask_restful as restful
from pebbles.utils import requires_admin
from pebbles.views.commons import auth, get_backends

backends = FlaskBlueprint('backends', __name__)

backend_fields = {
    'name': fields.String,
    'schema': fields.Raw,
    'form': fields.Raw,
    'model': fields.Raw,
}


class BackendList(restful.Resource):
    @auth.login_required
    @requires_admin
    @marshal_with(backend_fields)
    def get(self):
        backends = get_backends()
        return backends
