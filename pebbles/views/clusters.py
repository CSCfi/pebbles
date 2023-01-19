import flask_restful as restful
from flask import Blueprint as FlaskBlueprint, current_app
from flask_restful import fields, marshal_with

from pebbles.utils import requires_admin, load_cluster_config
from pebbles.views.commons import auth

clusters = FlaskBlueprint('clusters', __name__)

cluster_fields = {
    'name': fields.String,
    'driver': fields.String,
    'url': fields.String,
    'app_domain': fields.String,
    'namespace_prefix': fields.String,
}


class ClusterList(restful.Resource):
    @auth.login_required
    @requires_admin
    @marshal_with(cluster_fields)
    def get(self):
        if 'TEST_MODE' not in current_app.config:
            cluster_config = load_cluster_config(load_passwords=False)
        else:
            # rig unit tests to use dummy data
            cluster_config = dict(clusters=[
                dict(name='dummy_cluster_1', driver='KubernetesLocalDriver'),
                dict(name='dummy_cluster_2', driver='KubernetesLocalDriver'),
            ])

        # convert camel case to snake case. camel cased keys will be ignored in marshalling
        for cluster in cluster_config.get('clusters', []):
            if 'appDomain' in cluster.keys():
                cluster['app_domain'] = cluster['appDomain']
            if 'namespacePrefix' in cluster.keys():
                cluster['namespace_prefix'] = cluster['namespacePrefix']

        return cluster_config.get('clusters', [])
