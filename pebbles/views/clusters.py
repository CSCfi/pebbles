from flask import Blueprint as FlaskBlueprint
from flask_restful import fields, marshal_with

import flask_restful as restful
from pebbles.utils import requires_admin
from pebbles.views.commons import auth, get_clusters

clusters = FlaskBlueprint('clusters', __name__)

cluster_fields = {
    'name': fields.String,
    'schema': fields.Raw,
    'form': fields.Raw,
    'model': fields.Raw,
}


class ClusterList(restful.Resource):
    @auth.login_required
    @requires_admin
    @marshal_with(cluster_fields)
    def get(self):
        clusters = get_clusters()
        return clusters
