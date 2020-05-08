import logging
from collections import defaultdict

import flask_restful as restful
from flask import Blueprint as FlaskBlueprint
from flask_restful import marshal_with, fields

from pebbles.models import Environment, Instance
from pebbles.utils import requires_admin, memoize
from pebbles.views.commons import auth

stats = FlaskBlueprint('stats', __name__)


def query_environment(environment_id):
    return Environment.query.filter_by(id=environment_id).first()


ENVIRONMENT_FIELDS = {
    'name': fields.String,
    'users': fields.Integer,
    'launched_instances': fields.Integer,
    'running_instances': fields.Integer,
}

RESULT_FIELDS = {
    'environments': fields.List(fields.Nested(ENVIRONMENT_FIELDS)),
    'overall_running_instances': fields.Integer
}


class StatsList(restful.Resource):
    @auth.login_required
    @requires_admin
    @marshal_with(RESULT_FIELDS)
    def get(self):
        instances = Instance.query.all()
        overall_running_instances = Instance.query.filter(Instance.state != Instance.STATE_DELETED).count()

        get_environment = memoize(query_environment)
        per_environment_results = defaultdict(lambda: {'users': 0, 'launched_instances': 0, 'running_instances': 0})
        unique_users = defaultdict(set)

        for instance in instances:

            user_id = instance.user_id

            environment = get_environment(instance.environment_id)
            if not environment:
                logging.warning("instance %s has a reference to non-existing environment", instance.id)
                continue

            if 'name' not in per_environment_results[environment.id]:
                per_environment_results[environment.id]['name'] = environment.name

            if user_id not in unique_users[environment.id]:
                unique_users[environment.id].add(user_id)
                per_environment_results[environment.id]['users'] += 1

            if instance.state != Instance.STATE_DELETED:
                per_environment_results[environment.id]['running_instances'] += 1

            per_environment_results[environment.id]['launched_instances'] += 1
            # per_environment_results[environment.id]['overall_running_instances'] = overall_running_instances

        results = []
        for environment_id in per_environment_results:
            results.append(per_environment_results[environment_id])

        results.sort(
            key=lambda results_entry: (results_entry["launched_instances"], results_entry["users"]),
            reverse=True
        )
        final = {"environments": results, "overall_running_instances": overall_running_instances}

        return final
