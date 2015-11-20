from flask.ext.restful import marshal_with, fields
from flask import Blueprint as FlaskBlueprint

import logging

from pouta_blueprints.models import Blueprint, Instance
from pouta_blueprints.server import restful
from pouta_blueprints.views.commons import auth
from pouta_blueprints.utils import requires_admin, memoize

from collections import defaultdict


stats = FlaskBlueprint('stats', __name__)


def query_blueprint(blueprint_id):
    return Blueprint.query.filter_by(id=blueprint_id).first()


blueprint_result_fields = {

    'blueprint': {
        'name': fields.String,
        'users': fields.Integer,
        'launched_instances': fields.Integer,
        'running_instances': fields.Integer,
    },
    'overall_running_instances': fields.Integer
}


class StatsList(restful.Resource):
    @auth.login_required
    @requires_admin
    @marshal_with(blueprint_result_fields)
    def get(self):
        instances = Instance.query.all()
        overall_running_instances = Instance.query.filter(Instance.state != Instance.STATE_DELETED).count()

        get_blueprint = memoize(query_blueprint)
        per_blueprint_results = defaultdict(lambda: {'users': 0, 'launched_instances': 0, 'running_instances': 0})
        unique_users = defaultdict(set)

        for instance in instances:

            user_id = instance.user_id

            blueprint = get_blueprint(instance.blueprint_id)
            if not blueprint:
                logging.warn("instance %s has a reference to non-existing blueprint" % instance.id)
                continue

            if 'name' not in per_blueprint_results[blueprint.id]:
                per_blueprint_results[blueprint.id]['name'] = blueprint.name

            if user_id not in unique_users[blueprint.id]:
                unique_users[blueprint.id].add(user_id)
                per_blueprint_results[blueprint.id]['users'] += 1

            if(instance.state != Instance.STATE_DELETED):
                per_blueprint_results[blueprint.id]['running_instances'] += 1

            per_blueprint_results[blueprint.id]['launched_instances'] += 1
            per_blueprint_results[blueprint.id]['overall_running_instances'] = overall_running_instances

        results = []
        for blueprint_id in per_blueprint_results:
            results.append(per_blueprint_results[blueprint_id])

        return results
