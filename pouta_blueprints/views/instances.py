from flask.ext.restful import marshal_with, fields, reqparse
from flask import abort, g
from flask import Blueprint as FlaskBlueprint

import datetime
import logging
import re
import os
import json
import uuid

from pouta_blueprints.models import db, Blueprint, Instance, SystemToken
from pouta_blueprints.forms import InstanceForm
from pouta_blueprints.server import app, restful
from pouta_blueprints.utils import requires_admin
from pouta_blueprints.tasks import run_provisioning, run_deprovisioning, update_user_connectivity
from pouta_blueprints.views.commons import auth, user_fields

instances = FlaskBlueprint('instances', __name__)

USER_INSTANCE_LIMIT = 5

instance_fields = {
    'id': fields.String,
    'name': fields.String,
    'provisioned_at': fields.DateTime,
    'lifetime_left': fields.Integer,
    'max_lifetime': fields.Integer,
    'runtime': fields.Float,
    'state': fields.String,
    'error_msg': fields.String,
    'user': fields.Nested(user_fields),
    'blueprint_id': fields.String,
    'can_update_connectivity': fields.Boolean(default=False),
    'instance_data': fields.Raw,
    'public_ip': fields.String,
    'client_ip': fields.String(default='not set'),
    'logs': fields.Raw,
}


@instances.route('/')
class InstanceList(restful.Resource):
    @auth.login_required
    @marshal_with(instance_fields)
    def get(self):
        user = g.user
        if user.is_admin:
            instances = Instance.query.filter(Instance.state != 'deleted').all()
        else:
            instances = Instance.query.filter_by(user_id=user.id). \
                filter((Instance.state != 'deleted')).all()

        for instance in instances:
            instance.logs = InstanceLogs.get_logfile_urls(instance.id)

            blueprint = Blueprint.query.filter_by(id=instance.blueprint_id).first()

            if not blueprint:
                logging.warn("instance %s has a reference to non-existing blueprint" % instance.id)
                continue

            instance.blueprint_id = blueprint.id
            age = 0
            if instance.provisioned_at:
                age = (datetime.datetime.utcnow() - instance.provisioned_at).total_seconds()
            instance.lifetime_left = max(blueprint.max_lifetime - age, 0)
            instance.max_lifetime = blueprint.max_lifetime

        return instances

    @auth.login_required
    def post(self):
        user = g.user

        form = InstanceForm()
        if not form.validate_on_submit():
            logging.warn("validation error on user login")
            return form.errors, 422

        blueprint_id = form.blueprint.data

        blueprint = Blueprint.query.filter_by(id=blueprint_id).filter_by(is_enabled=True).first()
        if not blueprint:
            abort(404)

        blueprints_for_user = Instance.query.filter_by(blueprint_id=blueprint.id). \
            filter_by(user_id=user.id).filter(Instance.state != 'deleted').all()
        user_instance_limit = blueprint.config.get('maximum_instances_per_user', USER_INSTANCE_LIMIT)
        if blueprints_for_user and len(blueprints_for_user) >= user_instance_limit:
            abort(409)

        instance = Instance(blueprint, user)

        # decide on a name that is not used currently
        all_instances = Instance.query.all()
        existing_names = [x.name for x in all_instances]
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
            run_provisioning.delay(token.token, instance.id)


@instances.route('/<instance_id>', methods=['GET', 'DELETE', 'PATCH'])
class InstanceView(restful.Resource):
    parser = reqparse.RequestParser()
    parser.add_argument('state', type=str)
    parser.add_argument('public_ip', type=str)
    parser.add_argument('error_msg', type=str)
    parser.add_argument('client_ip', type=str)
    parser.add_argument('instance_data', type=str)

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

        instance.logs = InstanceLogs.get_logfile_urls(instance.id)

        if 'allow_update_client_connectivity' in blueprint.config \
                and blueprint.config['allow_update_client_connectivity']:
            instance.can_update_connectivity = True

        age = 0
        if instance.provisioned_at:
            age = (datetime.datetime.utcnow() - instance.provisioned_at).total_seconds()
        instance.lifetime_left = max(blueprint.max_lifetime - age, 0)
        instance.max_lifetime = blueprint.max_lifetime

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
        instance.state = 'deleting'
        instance.deprovisioned_at = datetime.datetime.utcnow()
        token = SystemToken('provisioning')
        db.session.add(token)
        db.session.commit()
        if not app.dynamic_config.get('SKIP_TASK_QUEUE'):
            run_deprovisioning.delay(token.token, instance.id)

    @auth.login_required
    def patch(self, instance_id):
        user = g.user
        args = self.parser.parse_args()
        query = Instance.query.filter_by(id=instance_id)
        if not user.is_admin:
            query = query.filter_by(user_id=user.id)
        instance = query.first()
        if not instance:
            abort(404)

        # TODO: add a model for state transitions
        if args.get('state'):
            if args['state'] == 'deprovisioning':
                if instance.state in ['starting', 'running', 'failed']:
                    instance.state = args['state']
                    instance.error_msg = ''
                    self.delete(instance_id)
            else:
                instance.state = args['state']
                if instance.state == 'running' and user.is_admin:
                    if not instance.provisioned_at:
                        instance.provisioned_at = datetime.datetime.utcnow()

            db.session.commit()

        if args.get('error_msg') and user.is_admin:
            instance.error_msg = args['error_msg']
            db.session.commit()

        if args.get('public_ip') and user.is_admin:
            instance.public_ip = args['public_ip']
            db.session.commit()

        if args.get('instance_data') and user.is_admin:
            try:
                instance.instance_data = json.loads(args['instance_data'])
            except ValueError:
                logging.warn("invalid instance_data passed to view: %s" % args['instance_data'])
            db.session.commit()

        if args['client_ip']:
            blueprint = Blueprint.query.filter_by(id=instance.blueprint_id).first()
            if 'allow_update_client_connectivity' in blueprint.config \
                    and blueprint.config['allow_update_client_connectivity']:
                new_ip = args['client_ip']
                ipv4_re = '^(?:(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.){3}(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)$'
                if re.match(ipv4_re, new_ip):
                    instance.client_ip = new_ip
                    if not app.dynamic_config.get('SKIP_TASK_QUEUE'):
                        update_user_connectivity.delay(instance.id)
                else:
                    # 400 Bad Request
                    abort(400)
            else:
                abort(401)

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
                res.append({'url': '/provisioning_logs/%s/%s' % (instance_id, log_file_name), 'type': log_type})
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
