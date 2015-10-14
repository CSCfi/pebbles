from flask.ext.restful import marshal, marshal_with, fields, reqparse
from flask import abort, g
from flask import Blueprint as FlaskBlueprint

import datetime
import logging
import os
import json
import uuid

from pouta_blueprints.models import db, Blueprint, Instance, User, SystemToken
from pouta_blueprints.forms import InstanceForm, UserIPForm
from pouta_blueprints.server import app, restful
from pouta_blueprints.utils import requires_admin, memoize
from pouta_blueprints.tasks import run_update, update_user_connectivity
from pouta_blueprints.views.commons import auth

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


def query_blueprint(blueprint_id):
    return Blueprint.query.filter_by(id=blueprint_id).first()


def query_user(user_id):
    return User.query.filter_by(id=user_id).first()


@instances.route('/')
class InstanceList(restful.Resource):
    @auth.login_required
    @marshal_with(instance_fields)
    def get(self):
        user = g.user
        if user.is_admin:
            instances = Instance.query.filter(Instance.state != Instance.STATE_DELETED).all()
        else:
            instances = Instance.query.filter_by(user_id=user.id). \
                filter((Instance.state != Instance.STATE_DELETED)).all()

        get_blueprint = memoize(query_blueprint)
        get_user = memoize(query_user)
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

        return instances

    @auth.login_required
    def post(self):
        user = g.user

        form = InstanceForm()
        if not form.validate_on_submit():
            logging.warn("validation error on user login")
            return form.errors, 422

        blueprint_id = form.blueprint.data

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

        user_instance_limit = blueprint.config.get('maximum_instances_per_user', USER_INSTANCE_LIMIT)
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
        token = SystemToken('provisioning')
        db.session.add(instance)
        db.session.add(token)
        db.session.commit()

        if not app.dynamic_config.get('SKIP_TASK_QUEUE'):
            run_update.delay(token.token, instance.id)
        return marshal(instance, instance_fields), 200


@instances.route('/<instance_id>', methods=['GET', 'DELETE', 'PATCH'])
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
        query = Instance.query.filter_by(id=instance_id)
        if not user.is_admin:
            query = query.filter_by(user_id=user.id)
        instance = query.first()
        if not instance:
            abort(404)

        blueprint = Blueprint.query.filter_by(id=instance.blueprint_id).first()
        instance.blueprint_id = blueprint.id
        instance.username = instance.user
        instance.logs = InstanceLogs.get_logfile_urls(instance.id)

        if 'allow_update_client_connectivity' in blueprint.config \
                and blueprint.config['allow_update_client_connectivity']:
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
        if not user.is_admin:
            query = query.filter_by(user_id=user.id)
        instance = query.first()
        if not instance:
            abort(404)
        instance.to_be_deleted = True
        instance.state = Instance.STATE_DELETING
        instance.deprovisioned_at = datetime.datetime.utcnow()
        token = SystemToken('provisioning')
        db.session.add(token)
        db.session.commit()
        if not app.dynamic_config.get('SKIP_TASK_QUEUE'):
            run_update.delay(token.token, instance.id)

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
        if 'allow_update_client_connectivity' in blueprint.config\
                and blueprint.config['allow_update_client_connectivity']:
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


@instances.route('/<instance_is>/logs', methods=['GET', 'PATCH'])
class InstanceLogs(restful.Resource):
    parser = reqparse.RequestParser()
    parser.add_argument('type', type=str)
    parser.add_argument('text', type=str)

    @staticmethod
    def get_base_dir_and_filename(instance_id, log_type, create_missing_filename=False):
        log_dir = '/webapps/pouta_blueprints/provisioning_logs/%s' % instance_id

        if not app.dynamic_config.get('WRITE_PROVISIONING_LOGS'):
            return None, None

        # make sure the directory for this instance exists
        if not os.path.isdir(log_dir):
            os.mkdir(log_dir, 0o755)

        # check if we already have a file with the correct extension
        log_file_name = None
        for filename in os.listdir(log_dir):
            if filename.endswith('.' + log_type + '.txt'):
                log_file_name = filename
        if not log_file_name and create_missing_filename:
            log_file_name = '%s.%s.txt' % (uuid.uuid4().hex, log_type)

        return log_dir, log_file_name

    @staticmethod
    def get_logfile_urls(instance_id):
        res = []
        for log_type in ['provisioning', 'deprovisioning']:
            log_dir, log_file_name = InstanceLogs.get_base_dir_and_filename(instance_id, log_type)
            if log_file_name:
                res.append({
                    'url': '/provisioning_logs/%s/%s' % (instance_id, log_file_name),
                    'type': log_type
                })
        return res

    @auth.login_required
    @requires_admin
    def patch(self, instance_id):
        args = self.parser.parse_args()
        instance = Instance.query.filter_by(id=instance_id).first()
        if not instance:
            abort(404)

        log_type = args['type']
        if not log_type:
            abort(403)

        if log_type in ('provisioning', 'deprovisioning'):
            log_dir, log_file_name = self.get_base_dir_and_filename(
                instance_id, log_type, create_missing_filename=True)

            with open('%s/%s' % (log_dir, log_file_name), 'a') as logfile:
                logfile.write(args['text'])
        else:
            abort(403)

        return 'ok'
