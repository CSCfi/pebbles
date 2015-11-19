from flask.ext.restful import marshal, marshal_with, fields
from flask import abort, g
from flask import Blueprint as FlaskBlueprint

import logging

from pouta_blueprints.models import db, Blueprint, Plugin, Instance, User
from pouta_blueprints.forms import BlueprintForm
from pouta_blueprints.server import restful
from pouta_blueprints.views.commons import auth, blueprint_fields
from pouta_blueprints.views.instances import InstanceLogs
from pouta_blueprints.utils import requires_admin, memoize
from pouta_blueprints.views.instances import instance_fields

import re
import datetime
from collections import defaultdict


stats = FlaskBlueprint('stats', __name__)

MAX_ACTIVATION_TOKENS_PER_USER = 3


def query_blueprint(blueprint_id):
    return Blueprint.query.filter_by(id=blueprint_id).first()


def query_user(user_id):
    return User.query.filter_by(id=user_id).first()


@stats.route('/')
class StatsList(restful.Resource):
    @auth.login_required
    @requires_admin
    def get(self):
        user = g.user
        if user.is_admin:
            instances = Instance.query.all()
            total_running_instances = Instance.query.filter(Instance.state != Instance.STATE_DELETED).count()

        get_blueprint = memoize(query_blueprint)
        get_user = memoize(query_user)
        per_blueprint_results = defaultdict(lambda: {'users': 0, 'total_instances': 0, 'running_instances': 0})
        unique_users = defaultdict(set)

        for instance in instances:

            user = get_user(instance.user_id)
            if user:
                instance.username = user.email

            blueprint = get_blueprint(instance.blueprint_id)
            if not blueprint:
                logging.warn("instance %s has a reference to non-existing blueprint" % instance.id)
                continue

            if 'name' not in per_blueprint_results[blueprint.id]:
                per_blueprint_results[blueprint.id]['name'] = blueprint.name

            if user.id not in unique_users[blueprint.id]:
                unique_users[blueprint.id].add(user.id)
                per_blueprint_results[blueprint.id]['users'] += 1

            if(instance.state != Instance.STATE_DELETED):
                per_blueprint_results[blueprint.id]['running_instances'] += 1

            per_blueprint_results[blueprint.id]['total_instances'] += 1

        results = {"blueprints": per_blueprint_results, "total_running_instances": total_running_instances}
        list_results = []  # Restangular Friendly
        list_results.append(results)

        return list_results


@stats.route('/instances')
class StatsInstanceList(restful.Resource):
    @auth.login_required
    @requires_admin
    def get(self):
        user = g.user
        if user.is_admin:
            instances = Instance.query.all()
            running_instances = Instance.query.filter(Instance.state != Instance.STATE_DELETED).count()

        get_blueprint = memoize(query_blueprint)
        get_user = memoize(query_user)
        per_blueprint_results = defaultdict(lambda: {'users': [], 'instances': []})
        for instance in instances:
            instance.logs = InstanceLogs.get_logfile_urls(instance.id)

            user = get_user(instance.user_id)
            if user:
                instance.username = user.email

            blueprint = get_blueprint(instance.blueprint_id)
            if not blueprint:
                logging.warn("instance %s has a reference to non-existing blueprint" % instance.id)
                continue

            age = 0
            if instance.provisioned_at:
                age = (datetime.datetime.utcnow() - instance.provisioned_at).total_seconds()
            instance.lifetime_left = max(blueprint.maximum_lifetime - age, 0)
            instance.maximum_lifetime = blueprint.maximum_lifetime
            instance.cost_multiplier = blueprint.cost_multiplier
            per_blueprint_results[blueprint.id]['instances'].append(marshal(instance, instance_fields))
            per_blueprint_results[blueprint.id]['users'].append(instance.user.email)

        for res in per_blueprint_results:
            per_blueprint_results[res]['users'] = list(set(per_blueprint_results[res]['users']))

        results = {"blueprints": per_blueprint_results, "running_instances": running_instances}
        list_results = []
        list_results.append(results)

        return list_results


@stats.route('/blueprint/<string:blueprint_id>')
class StatsBlueprintView(restful.Resource):
    @auth.login_required
    @requires_admin
    def get(self, blueprint_id):
        user = g.user
        if user.is_admin:
            instances = Instance.query.filter(Instance.blueprint_id == blueprint_id).all()
            # running_instances = Instance.query.filter(Instance.state != Instance.STATE_DELETED).count()

        get_blueprint = memoize(query_blueprint)
        get_user = memoize(query_user)
        blueprint_results = {'name': '', 'users': [], 'instances': []}

        for instance in instances:
            instance.logs = InstanceLogs.get_logfile_urls(instance.id)

            user = get_user(instance.user_id)
            if user:
                instance.username = user.email

            blueprint = get_blueprint(instance.blueprint_id)
            if not blueprint:
                logging.warn("instance %s has a reference to non-existing blueprint" % instance.id)
                continue

            age = 0
            if instance.provisioned_at:
                age = (datetime.datetime.utcnow() - instance.provisioned_at).total_seconds()
            instance.lifetime_left = max(blueprint.maximum_lifetime - age, 0)
            instance.maximum_lifetime = blueprint.maximum_lifetime
            instance.cost_multiplier = blueprint.cost_multiplier

            blueprint_results['name'] = blueprint.name
            blueprint_results['instances'].append(marshal(instance, instance_fields))
            blueprint_results['users'].append(instance.user.email)

        blueprint_results['users'] = list(set(blueprint_results['users']))
        list_results = []
        list_results.append(blueprint_results)

        return list_results
