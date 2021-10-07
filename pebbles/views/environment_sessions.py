import datetime
import json
import logging

import flask_restful as restful
from flask import Blueprint as FlaskBlueprint
from flask import abort, g, current_app
from flask_restful import marshal, marshal_with, fields, reqparse

from pebbles import rules, utils
from pebbles.forms import EnvironmentSessionForm
from pebbles.models import db, Environment, EnvironmentSession, EnvironmentSessionLog, User
from pebbles.rules import apply_rules_environment_sessions
from pebbles.utils import requires_admin, memoize
from pebbles.views.commons import auth, is_workspace_manager

environment_sessions = FlaskBlueprint('environment_sessions', __name__)

environment_session_fields = {
    'id': fields.String,
    'name': fields.String,
    'created_at': fields.DateTime(dt_format='iso8601'),
    'provisioned_at': fields.DateTime(dt_format='iso8601'),
    'deprovisioned_at': fields.DateTime(dt_format='iso8601'),
    'lifetime_left': fields.Integer,
    'maximum_lifetime': fields.Integer,
    'state': fields.String,
    'to_be_deleted': fields.Boolean,
    'log_fetch_pending': fields.Boolean,
    'error_msg': fields.String,
    'username': fields.String,
    'user_id': fields.String,
    'environment': fields.String,
    'environment_id': fields.String,
    'provisioning_config': fields.Raw,
    'session_data': fields.Raw,
}

environment_session_log_fields = {
    'id': fields.String,
    'environment_session_id': fields.String,
    'log_type': fields.String,
    'log_level': fields.String,
    'timestamp': fields.Float,
    'message': fields.String
}


def query_environment(environment_id):
    return Environment.query.filter_by(id=environment_id).first()


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


class EnvironmentSessionList(restful.Resource):

    @auth.login_required
    @marshal_with(environment_session_fields)
    def get(self):
        user = g.user
        q = apply_rules_environment_sessions(user)
        q = q.order_by(EnvironmentSession.provisioned_at)
        environment_sessions = q.all()

        get_environment = memoize(query_environment)
        get_user = memoize(query_user)
        for environment_session in environment_sessions:
            environment_session_logs = get_logs_from_db(environment_session.id)
            environment_session.logs = marshal(environment_session_logs, environment_session_log_fields)

            user = get_user(environment_session.user_id)
            if user:
                environment_session.username = user.ext_id

            environment = get_environment(environment_session.environment_id)
            if not environment:
                logging.warning(
                    "environment_session %s has a reference to non-existing environment" % environment_session.id)
                continue

            age = 0
            if environment_session.provisioned_at:
                age = (datetime.datetime.utcnow() - environment_session.provisioned_at).total_seconds()
            environment_session.lifetime_left = max(environment.maximum_lifetime - age, 0)
            environment_session.maximum_lifetime = environment.maximum_lifetime
            environment_session.cost_multiplier = environment.cost_multiplier

            if environment_session.to_be_deleted and environment_session.state != EnvironmentSession.STATE_DELETED:
                environment_session.state = EnvironmentSession.STATE_DELETING

        return environment_sessions

    @auth.login_required
    def post(self):
        user = g.user

        form = EnvironmentSessionForm()
        if not form.validate_on_submit():
            logging.warning("validation error on user login")
            return form.errors, 422

        environment_id = form.environment.data

        # fetch the environment using shared access rules
        environment = rules.apply_rules_environments(user, dict(environment_id=environment_id)).first()
        if not environment:
            logging.warning('environment_session creation failed, no environment found for id %s', environment_id)
            abort(404)

        # admins and workspace managers are allowed to test disabled environments
        if not environment.is_enabled and not (user.is_admin or is_workspace_manager(user, environment.workspace)):
            logging.warning('environment_session creation failed, environment %s is disabled', environment_id)
            abort(403)

        environment_sessions_for_user = EnvironmentSession.query.filter_by(
            environment_id=environment.id,
            user_id=user.id
        ).filter(EnvironmentSession.state != 'deleted').all()

        if environment_sessions_for_user:
            return {'error': 'ENVIRONMENT_INSTANCE_LIMIT_REACHED'}, 409

        # create the environment_session and assign provisioning config from current environment + template
        environment_session = EnvironmentSession(environment, user)
        environment_session.provisioning_config = utils.get_provisioning_config(environment)

        # XXX: Choosing the name should be done in the model's constructor method
        # decide on a name that is not used currently
        existing_names = set(x.name for x in EnvironmentSession.query.all())
        # Note: the potential race is solved by unique constraint in database
        while True:
            c_name = EnvironmentSession.generate_name(prefix=current_app.config.get('INSTANCE_NAME_PREFIX'))
            if c_name not in existing_names:
                environment_session.name = c_name
                break
        db.session.add(environment_session)
        db.session.commit()

        return marshal(environment_session, environment_session_fields), 200


class EnvironmentSessionView(restful.Resource):

    @auth.login_required
    @marshal_with(environment_session_fields)
    def get(self, environment_session_id):
        user = g.user
        args = {'environment_session_id': environment_session_id}
        query = apply_rules_environment_sessions(user, args)
        environment_session = query.first()
        if not environment_session:
            abort(404)

        environment = Environment.query.filter_by(id=environment_session.environment_id).first()
        environment_session.environment_id = environment.id
        environment_session.username = environment_session.user

        age = 0
        if environment_session.provisioned_at:
            age = (datetime.datetime.utcnow() - environment_session.provisioned_at).total_seconds()
        environment_session.lifetime_left = max(environment.maximum_lifetime - age, 0)
        environment_session.maximum_lifetime = environment.maximum_lifetime
        environment_session.cost_multiplier = environment.cost_multiplier

        return environment_session

    @auth.login_required
    def delete(self, environment_session_id):
        user = g.user
        query = EnvironmentSession.query.filter_by(id=environment_session_id)
        if not user.is_admin and not is_workspace_manager(user):
            query = query.filter_by(user_id=user.id)
        environment_session = query.first()
        if not environment_session:
            abort(404)
        workspace = environment_session.environment.workspace
        if not user.is_admin and not is_workspace_manager(user, workspace) and environment_session.user_id != user.id:
            abort(403)
        environment_session.to_be_deleted = True
        environment_session.deprovisioned_at = datetime.datetime.utcnow()
        db.session.commit()

        # Action queued, return 202 Accepted
        return None, 202

    patch_parser = reqparse.RequestParser()
    patch_parser.add_argument('state', type=str)
    patch_parser.add_argument('error_msg', type=str)
    patch_parser.add_argument('session_data', type=str)
    patch_parser.add_argument('to_be_deleted', type=bool)
    patch_parser.add_argument('log_fetch_pending', type=bool)
    patch_parser.add_argument('send_email', type=bool)

    @auth.login_required
    @requires_admin
    def patch(self, environment_session_id):
        args = self.patch_parser.parse_args()
        environment_session = EnvironmentSession.query.filter_by(id=environment_session_id).first()
        if not environment_session:
            abort(404)

        if args.get('state'):
            state = args.get('state')
            if state not in EnvironmentSession.VALID_STATES:
                abort(422)
            environment_session.state = args['state']
            if environment_session.state == EnvironmentSession.STATE_RUNNING:
                if not environment_session.provisioned_at:
                    environment_session.provisioned_at = datetime.datetime.utcnow()
            if environment_session.state == EnvironmentSession.STATE_FAILED:
                environment_session.errored = True
            if environment_session.state == EnvironmentSession.STATE_DELETED:
                delete_logs_from_db(environment_session_id)
            db.session.commit()

        if args.get('to_be_deleted'):
            environment_session.to_be_deleted = args['to_be_deleted']
            environment_session.deprovisioned_at = datetime.datetime.utcnow()
            db.session.commit()

        if args.get('log_fetch_pending') is not None:
            environment_session.log_fetch_pending = args['log_fetch_pending']
            db.session.commit()

        if args.get('error_msg'):
            environment_session.error_msg = args['error_msg']
            db.session.commit()

        if args.get('session_data'):
            try:
                environment_session.session_data = json.loads(args['session_data'])
            except ValueError:
                logging.warning("invalid session_data passed to view: %s" % args['session_data'])
            db.session.commit()


class EnvironmentSessionLogs(restful.Resource):

    @auth.login_required
    @marshal_with(environment_session_log_fields)
    def get(self, environment_session_id):
        user = g.user
        parser = reqparse.RequestParser()
        parser.add_argument('log_type', type=str, default=None, required=False, location='args')
        args = parser.parse_args()
        query = apply_rules_environment_sessions(user, dict(environment_session_id=environment_session_id))
        environment_session = query.first()
        if not environment_session:
            abort(404)

        environment_session_logs = get_logs_from_db(environment_session_id, args.get('log_type'))

        return environment_session_logs

    @auth.login_required
    @requires_admin
    def patch(self, environment_session_id):
        patch_parser = reqparse.RequestParser()
        patch_parser.add_argument('log_record', type=dict)
        args = patch_parser.parse_args()

        if args.get('log_record'):
            log_record = args['log_record']

            environment_session_log = None
            # provisioning logs: check if we already have a matching line and can skip adding a duplicate
            if log_record['log_type'] == 'provisioning':
                existing_logs = get_logs_from_db(environment_session_id, log_record['log_type'])
                for log_line in existing_logs:
                    if log_line.timestamp == log_record['timestamp'] and \
                            log_line.environment_session_id == log_record['environment_session_id'] and \
                            log_line.log_type == log_record['log_type']:
                        return 'no change'

            # running logs: patch the the existing entry with new timestamp and message
            if log_record['log_type'] == 'running':
                existing_logs = get_logs_from_db(environment_session_id, log_record['log_type'])
                if existing_logs:
                    environment_session_log = existing_logs[0]
                    environment_session_log.timestamp = float(log_record['timestamp'])
                    environment_session_log.message = log_record['message']

            # no previous log record found, add a new one to the session
            if not environment_session_log:
                environment_session_log = EnvironmentSessionLog(
                    environment_session_id,
                    log_record['log_level'],
                    log_record['log_type'],
                    log_record['timestamp'],
                    log_record['message'],
                )
                db.session.add(environment_session_log)

            db.session.commit()

        return 'ok'

    @auth.login_required
    @requires_admin
    def delete(self, environment_session_id):
        parser = reqparse.RequestParser()
        parser.add_argument('log_type', type=str, default=None, required=False, location='args')
        args = parser.parse_args()
        delete_logs_from_db(environment_session_id, args.get('log_type'))


def get_logs_from_db(environment_session_id, log_type=None):
    logs_query = EnvironmentSessionLog.query \
        .filter_by(environment_session_id=environment_session_id) \
        .order_by(EnvironmentSessionLog.timestamp)
    if log_type:
        logs_query = logs_query.filter_by(log_type=log_type)
    logs_query = logs_query.order_by(EnvironmentSessionLog.timestamp)
    logs = logs_query.all()
    return logs


def delete_logs_from_db(environment_session_id, log_type=None):
    environment_session_logs = get_logs_from_db(environment_session_id, log_type)
    if not environment_session_logs:
        logging.warning("There are no log entries to be deleted")

    for environment_session_log in environment_session_logs:
        db.session.delete(environment_session_log)
    db.session.commit()
