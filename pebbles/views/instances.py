from flask.ext.restful import marshal, marshal_with, fields, reqparse
from flask import abort, g
from flask import Blueprint as FlaskBlueprint

import datetime
import logging
import json

from pebbles.models import db, Blueprint, Instance, InstanceLog, User
from pebbles.forms import InstanceForm, UserIPForm
from pebbles.server import app, restful
from pebbles.utils import requires_admin, memoize
from pebbles.tasks import run_update, update_user_connectivity, fetch_running_instance_logs
from pebbles.views.commons import auth, is_group_manager
from pebbles.rules import apply_rules_instances, get_group_blueprint_ids_for_instances

instances = FlaskBlueprint('instances', __name__)

USER_INSTANCE_LIMIT = 5

instance_fields = {
    'id': fields.String,
    'name': fields.String,
    'provisioned_at': fields.DateTime,
    'lifetime_left': fields.Integer,
    'maximum_lifetime': fields.Integer,
    'runtime': fields.Float,
    'state': fields.String,
    'to_be_deleted': fields.Boolean,
    'error_msg': fields.String,
    'username': fields.String,
    'user_id': fields.String,
    'blueprint': fields.String,
    'blueprint_id': fields.String,
    'cost_multiplier': fields.Float(default=1.0),
    'can_update_connectivity': fields.Boolean(default=False),
    'instance_data': fields.Raw,
    'public_ip': fields.String,
    'client_ip': fields.String(default='not set'),
    'logs': fields.Raw,
}

instance_log_fields = {
    'id': fields.String,
    'instance_id': fields.String,
    'log_type': fields.String,
    'log_level': fields.String,
    'timestamp': fields.Float,
    'message': fields.String
}


def query_blueprint(blueprint_id):
    return Blueprint.query.filter_by(id=blueprint_id).first()


def query_user(user_id):
    return User.query.filter_by(id=user_id).first()


def positive_integer(input_value):
    """Return input_value if valid, raise an exception in other case."""
    try:
        input_int = int(input_value)
    except:
        raise ValueError('{} is not a valid integer'.format(input_value))
    if input_int >= 0:
        return input_int
    else:
        raise ValueError('{} is not a positive integer'.format(input_value))


class InstanceList(restful.Resource):
    parser = reqparse.RequestParser()
    parser.add_argument('show_deleted', type=bool, default=False, location='args')
    parser.add_argument('show_only_mine', type=bool, default=False, location='args')
    parser.add_argument('offset', type=positive_integer, location='args')
    parser.add_argument('limit', type=positive_integer, location='args')

    @auth.login_required
    @marshal_with(instance_fields)
    def get(self):
        user = g.user
        args = self.parser.parse_args()
        q = apply_rules_instances(user, args)
        q = q.order_by(Instance.provisioned_at)
        instances = q.all()

        get_blueprint = memoize(query_blueprint)
        get_user = memoize(query_user)
        for instance in instances:
            instance_logs = get_logs_from_db(instance.id)
            instance.logs = marshal(instance_logs, instance_log_fields)

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

            if instance.to_be_deleted:
                instance.state = Instance.STATE_DELETING

        return instances

    @auth.login_required
    def post(self):
        user = g.user

        form = InstanceForm()
        if not form.validate_on_submit():
            logging.warn("validation error on user login")
            return form.errors, 422

        blueprint_id = form.blueprint.data
        allowed_blueprint_ids = get_group_blueprint_ids_for_instances(user)
        if not user.is_admin and blueprint_id not in allowed_blueprint_ids:
            abort(403)
        blueprint = Blueprint.query.filter_by(id=blueprint_id, is_enabled=True).first()
        if not blueprint:
            abort(404)
        if user.quota_exceeded():
            return {'error': 'USER_OVER_QUOTA'}, 409

        if blueprint.preallocated_credits:
            preconsumed_amount = blueprint.cost()
            total_credits_spent = preconsumed_amount + user.credits_spent
            if user.credits_quota < total_credits_spent:
                return {'error': 'USER_OVER_QUOTA'}, 409

        instances_for_user = Instance.query.filter_by(
            blueprint_id=blueprint.id,
            user_id=user.id
        ).filter(Instance.state != 'deleted').all()

        user_instance_limit = blueprint.full_config.get('maximum_instances_per_user', USER_INSTANCE_LIMIT)
        if instances_for_user and len(instances_for_user) >= user_instance_limit:
            return {'error': 'BLUEPRINT_INSTANCE_LIMIT_REACHED'}, 409

        instance = Instance(blueprint, user)
        # XXX: Choosing the name should be done in the model's constructor method
        # decide on a name that is not used currently
        existing_names = set(x.name for x in Instance.query.all())
        # Note: the potential race is solved by unique constraint in database
        while True:
            c_name = Instance.generate_name(prefix=app.dynamic_config.get('INSTANCE_NAME_PREFIX'))
            if c_name not in existing_names:
                instance.name = c_name
                break
        db.session.add(instance)
        db.session.commit()

        if not app.dynamic_config.get('SKIP_TASK_QUEUE'):
            run_update.delay(instance.id)

        return marshal(instance, instance_fields), 200


class InstanceView(restful.Resource):
    parser = reqparse.RequestParser()
    parser.add_argument('state', type=str)
    parser.add_argument('public_ip', type=str)
    parser.add_argument('error_msg', type=str)
    parser.add_argument('client_ip', type=str)
    parser.add_argument('instance_data', type=str)
    parser.add_argument('to_be_deleted', type=bool)

    @auth.login_required
    @marshal_with(instance_fields)
    def get(self, instance_id):
        user = g.user
        args = {'instance_id': instance_id}
        query = apply_rules_instances(user, args)
        instance = query.first()
        if not instance:
            abort(404)

        blueprint = Blueprint.query.filter_by(id=instance.blueprint_id).first()
        instance.blueprint_id = blueprint.id
        instance.username = instance.user
        instance_logs = get_logs_from_db(instance.id)
        instance.logs = marshal(instance_logs, instance_log_fields)

        if 'allow_update_client_connectivity' in blueprint.full_config \
                and blueprint.full_config['allow_update_client_connectivity']:
            instance.can_update_connectivity = True

        age = 0
        if instance.provisioned_at:
            age = (datetime.datetime.utcnow() - instance.provisioned_at).total_seconds()
        instance.lifetime_left = max(blueprint.maximum_lifetime - age, 0)
        instance.maximum_lifetime = blueprint.maximum_lifetime
        instance.cost_multiplier = blueprint.cost_multiplier

        return instance

    @auth.login_required
    def delete(self, instance_id):
        user = g.user
        query = Instance.query.filter_by(id=instance_id)
        if not user.is_admin and not is_group_manager(user):
            query = query.filter_by(user_id=user.id)
        instance = query.first()
        if not instance:
            abort(404)
        group = instance.blueprint.group
        if not user.is_admin and not is_group_manager(user, group) and instance.user_id != user.id:
            abort(403)
        instance.to_be_deleted = True
        instance.state = Instance.STATE_DELETING
        instance.deprovisioned_at = datetime.datetime.utcnow()
        db.session.commit()
        if not app.dynamic_config.get('SKIP_TASK_QUEUE'):
            run_update.delay(instance.id)

    @auth.login_required
    def put(self, instance_id):
        user = g.user
        form = UserIPForm()
        if not form.validate_on_submit():
            logging.warn("validation error on UserIPForm")
            return form.errors, 422

        instance = Instance.query.filter_by(id=instance_id, user_id=user.id).first()
        if not instance:
            abort(404)

        blueprint = Blueprint.query.filter_by(id=instance.blueprint_id).first()
        if 'allow_update_client_connectivity' in blueprint.full_config \
                and blueprint.full_config['allow_update_client_connectivity']:
            instance.client_ip = form.client_ip.data
            if not app.dynamic_config.get('SKIP_TASK_QUEUE'):
                update_user_connectivity.delay(instance.id)
            db.session.commit()

        else:
            abort(400)

    @auth.login_required
    @requires_admin
    def patch(self, instance_id):
        args = self.parser.parse_args()
        instance = Instance.query.filter_by(id=instance_id).first()
        if not instance:
            abort(404)

        if args.get('state'):
            instance.state = args['state']
            if instance.state == Instance.STATE_RUNNING:
                if not instance.provisioned_at:
                    instance.provisioned_at = datetime.datetime.utcnow()
            if args['state'] == Instance.STATE_FAILED:
                instance.errored = True

            db.session.commit()

        if args.get('to_be_deleted'):
            instance.to_be_deleted = args['to_be_deleted']
            db.session.commit()

        if args.get('error_msg'):
            instance.error_msg = args['error_msg']
            db.session.commit()

        if args.get('public_ip'):
            instance.public_ip = args['public_ip']
            db.session.commit()

        if args.get('instance_data'):
            try:
                instance.instance_data = json.loads(args['instance_data'])
            except ValueError:
                logging.warn("invalid instance_data passed to view: %s" % args['instance_data'])
            db.session.commit()


class InstanceLogs(restful.Resource):
    parser = reqparse.RequestParser()
    parser.add_argument('log_record', type=dict)
    parser.add_argument('log_type', type=str)
    parser.add_argument('send_log_fetch_task', type=bool)

    @auth.login_required
    @marshal_with(instance_log_fields)
    def get(self, instance_id):
        args = self.parser.parse_args()
        instance = Instance.query.filter_by(id=instance_id).first()
        if not instance:
            abort(404)
        if args.get('log_type'):
            log_type = args['log_type']
        instance_logs = get_logs_from_db(instance_id, log_type)
        return instance_logs

    @auth.login_required
    @requires_admin
    def patch(self, instance_id):
        args = self.parser.parse_args()
        instance = Instance.query.filter_by(id=instance_id).first()
        if not instance:
            abort(404)
        if args.get('send_log_fetch_task'):
            if not app.dynamic_config.get('SKIP_TASK_QUEUE'):
                fetch_running_instance_logs.delay(instance_id)
        if args.get('log_record'):
            log_record = args['log_record']
            instance_log = process_logs(instance_id, log_record)
            db.session.add(instance_log)
            db.session.commit()

        return 'ok'

    @auth.login_required
    @requires_admin
    def delete(self, instance_id):
        args = self.parser.parse_args()
        log_type = args.get('log_type')
        if log_type:
            instance_logs = get_logs_from_db(instance_id, args.get('log_type'))
        else:
            instance_logs = get_logs_from_db(instance_id)
        if not instance_logs:
            logging.warn("There are no log entries to be deleted")

        for instance_log in instance_logs:
            db.session.delete(instance_log)
        db.session.commit()


def get_logs_from_db(instance_id, log_type=None):
    logs_query = InstanceLog.query\
        .filter_by(instance_id=instance_id)
    if log_type:
        logs_query = logs_query.filter_by(log_type=log_type)
    logs_query = logs_query.order_by(InstanceLog.timestamp)
    logs = logs_query.all()
    return logs


def process_logs(instance_id, log_record):

    check_running_log = get_logs_from_db(instance_id, "running")

    if check_running_log:
        instance_log = check_running_log[0]
        if log_record['log_type'] == "running":
            instance_log.timestamp = float(log_record['timestamp'])
            instance_log.message = log_record['message']
            return instance_log

    instance_log = InstanceLog(instance_id)
    instance_log.log_type = log_record['log_type']
    instance_log.log_level = log_record['log_level']
    instance_log.timestamp = float(log_record['timestamp'])
    instance_log.message = log_record['message']

    return instance_log
