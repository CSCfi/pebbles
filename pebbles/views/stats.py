import logging
from collections import defaultdict

import flask_restful as restful
from flask import Blueprint as FlaskBlueprint
from flask_restful import marshal_with, fields

from pebbles.models import Blueprint, Instance
from pebbles.utils import requires_admin, memoize
from pebbles.views.commons import auth

stats = FlaskBlueprint('stats', __name__)


def query_blueprint(blueprint_id):
    return Blueprint.query.filter_by(id=blueprint_id).first()


BLUEPRINT_FIELDS = {
    'name': fields.String,
    'users': fields.Integer,
    'launched_instances': fields.Integer,
    'running_instances': fields.Integer,
}

RESULT_FIELDS = {
    'blueprints': fields.List(fields.Nested(BLUEPRINT_FIELDS)),
    'overall_running_instances': fields.Integer
}


class StatsList(restful.Resource):
    @auth.login_required
    @requires_admin
    @marshal_with(RESULT_FIELDS)
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
                logging.warning("instance %s has a reference to non-existing blueprint", instance.id)
                continue

            if 'name' not in per_blueprint_results[blueprint.id]:
                per_blueprint_results[blueprint.id]['name'] = blueprint.name

            if user_id not in unique_users[blueprint.id]:
                unique_users[blueprint.id].add(user_id)
                per_blueprint_results[blueprint.id]['users'] += 1

            if instance.state != Instance.STATE_DELETED:
                per_blueprint_results[blueprint.id]['running_instances'] += 1

            per_blueprint_results[blueprint.id]['launched_instances'] += 1
            # per_blueprint_results[blueprint.id]['overall_running_instances'] = overall_running_instances

        results = []
        for blueprint_id in per_blueprint_results:
            results.append(per_blueprint_results[blueprint_id])

        results.sort(
            key=lambda results_entry: (results_entry["launched_instances"], results_entry["users"]),
            reverse=True
        )
        final = {"blueprints": results, "overall_running_instances": overall_running_instances}

        return final
