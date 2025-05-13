import json
import logging
from datetime import datetime, timezone

import flask_restful as restful
from flask import Blueprint as FlaskBlueprint
from flask import abort, g, current_app
from flask_restful import marshal_with, fields, reqparse
from sqlalchemy import exists

from pebbles import rules, utils
from pebbles.forms import ApplicationSessionForm
from pebbles.models import db, Application, ApplicationSession, ApplicationSessionLog, User
from pebbles.utils import requires_admin
from pebbles.views.commons import auth, is_workspace_manager, requires_workspace_manager_or_admin

application_sessions = FlaskBlueprint('application_sessions', __name__)

application_session_fields_admin = {
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
    'application': fields.String,
    'application_id': fields.String,
    'provisioning_config': fields.Raw,
    'session_data': fields.Raw,
    'info': {
        'container_image': fields.Raw,
    },
}

application_session_fields_manager = {
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
    'application': fields.String,
    'application_id': fields.String,
    'session_data': fields.Raw,
    'info': {
        'container_image': fields.Raw,
    },
}

application_session_fields_user = {
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
    'application': fields.String,
    'application_id': fields.String,
    'session_data': fields.Raw,
    'info': {
        'container_image': fields.Raw,
    },
}

application_session_log_fields = {
    'id': fields.String,
    'application_session_id': fields.String,
    'log_type': fields.String,
    'log_level': fields.String,
    'timestamp': fields.Float,
    'message': fields.String
}

MAX_APPLICATION_SESSIONS_PER_USER = 2


def marshal_based_on_role(user, application_session):
    if user.is_admin:
        return restful.marshal(application_session, application_session_fields_admin)
    elif is_workspace_manager(user):
        return restful.marshal(application_session, application_session_fields_manager)
    else:
        return restful.marshal(application_session, application_session_fields_user)


def query_application(application_id):
    return Application.query.filter_by(id=application_id).first()


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


class ApplicationSessionList(restful.Resource):
    list_parser = reqparse.RequestParser()
    list_parser.add_argument('limit', type=int, location='args')

    @auth.login_required
    def get(self):
        user = g.user

        args = self.list_parser.parse_args()
        s = rules.generate_application_session_query(user, args)
        rows = db.session.execute(s).all()
        current_sessions = []
        for row in rows:
            application_session = row.ApplicationSession
            application = row.Application
            application_session.username = row.User.ext_id
            application_session.lifetime_left = max(
                application.maximum_lifetime - application_session.get_age_secs(), 0
            )
            application_session.maximum_lifetime = application.maximum_lifetime
            application_session.cost_multiplier = application.cost_multiplier

            if application_session.to_be_deleted and application_session.state != ApplicationSession.STATE_DELETED:
                application_session.state = ApplicationSession.STATE_DELETING

            # data for info field
            application_session.container_image = application_session.provisioning_config.get('image')

            current_sessions.append(marshal_based_on_role(user, application_session))

        return current_sessions

    @auth.login_required
    def post(self):
        user = g.user

        form = ApplicationSessionForm()
        if not form.validate_on_submit():
            logging.warning('form validation error on creating session')
            return form.errors, 422

        application_id = form.application_id.data

        # fetch the application using shared access rules
        application = db.session.scalar(rules.generate_application_query(user, dict(application_id=application_id)))
        if not application:
            logging.warning('application_session creation failed, no application found for id %s', application_id)
            abort(404)

        # check that the application's workspace has not expired
        if application.workspace and application.workspace.has_expired():
            logging.warning('application_session creation failed, application %s has expired', application_id)
            return 'Application has expired', 409

        # only admins and workspace managers are allowed to test disabled applications
        if not application.is_enabled and not (user.is_admin or is_workspace_manager(user, application.workspace)):
            logging.warning('application_session creation failed, application %s is disabled', application_id)
            return 'Application is disabled', 409

        # check existing sessions and enforce limits. There is still a potential race here by request flooding, this
        # can be fixed later by obtaining a lock per user
        application_sessions_for_user = ApplicationSession.query.filter_by(
            user_id=user.id
        ).filter(ApplicationSession.state != 'deleted').all()
        # first check the global limit
        if not user.is_admin and len(application_sessions_for_user) >= MAX_APPLICATION_SESSIONS_PER_USER:
            return 'Application session limit %s reached. Please close existing sessions first' \
                   ' before starting this application.' % MAX_APPLICATION_SESSIONS_PER_USER, 409
        # then check that we don't have an existing session already
        for session in application_sessions_for_user:
            if session.application_id == application_id:
                return 'There is already an existing session for this application', 409

        # then check that workspace is not out of resources
        application_sessions_in_ws = ApplicationSession.query \
            .filter(ApplicationSession.state != 'deleted') \
            .join(Application) \
            .filter_by(workspace_id=application.workspace_id).all()
        # sum up existing resources + the new session on top
        ws_consumed_mem = application.config.get('memory_gib', application.base_config.get('memory_gib', 1.0))
        for sess in application_sessions_in_ws:
            ws_consumed_mem += sess.provisioning_config.get('memory_gib', 1.0)

        if ws_consumed_mem > application.workspace.memory_limit_gib:
            logging.info('workspace %s is over memory limit', application.workspace_id)
            return 'Concurrent session memory limit for workspace exceeded', 409

        # create the application_session and assign provisioning config from current application + template
        application_session = ApplicationSession(application, user)
        db.session.add(application_session)
        application_session.provisioning_config = utils.get_provisioning_config(application)

        # data for info field
        application_session.container_image = application_session.provisioning_config.get('image')

        # Note: the potential race is solved by unique constraint in database
        retry_count = 0
        while True:
            # decide on a name that is not used currently
            c_name = ApplicationSession.generate_name(prefix=current_app.config.get('SESSION_NAME_PREFIX'))
            if not db.session.query(exists().where(ApplicationSession.name == c_name)).scalar():
                application_session.name = c_name
                break
            retry_count += 1

        if retry_count > 10:
            logging.warning('Session name retries: %d, consider expanding the number of permutations', retry_count)

        db.session.commit()

        return marshal_based_on_role(user, application_session), 200


class ApplicationSessionView(restful.Resource):

    @auth.login_required
    def get(self, application_session_id):
        user = g.user
        args = {'application_session_id': application_session_id}
        application_session = db.session.scalar(rules.generate_application_session_query(user, args))
        if not application_session:
            abort(404)

        application = Application.query.filter_by(id=application_session.application_id).first()
        application_session.application_id = application.id
        application_session.username = application_session.user

        application_session.lifetime_left = max(
            application.maximum_lifetime - application_session.get_age_secs(), 0
        )
        application_session.maximum_lifetime = application.maximum_lifetime
        application_session.cost_multiplier = application.cost_multiplier

        if application_session.to_be_deleted and application_session.state != ApplicationSession.STATE_DELETED:
            application_session.state = ApplicationSession.STATE_DELETING

        # data for info field
        application_session.container_image = application_session.provisioning_config.get('image')

        return marshal_based_on_role(user, application_session)

    @auth.login_required
    def delete(self, application_session_id):
        user = g.user
        args = {'application_session_id': application_session_id}
        application_session = db.session.scalar(rules.generate_application_session_query(user, args))
        if not application_session:
            abort(404)
        workspace = application_session.application.workspace
        if not user.is_admin and not is_workspace_manager(user, workspace) and application_session.user_id != user.id:
            abort(403)
        application_session.to_be_deleted = True
        application_session.deprovisioned_at = datetime.now(timezone.utc)
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
    @requires_workspace_manager_or_admin
    def patch(self, application_session_id):
        user = g.user

        # check that the user has rights to access the session
        opts = dict(application_session_id=application_session_id)
        application_session = db.session.scalar(rules.generate_application_session_query(user, opts))
        if not application_session:
            abort(404)

        args = self.patch_parser.parse_args()

        # managers can set log fetching
        if args.get('log_fetch_pending') is not None:
            application_session.log_fetch_pending = args['log_fetch_pending']
            db.session.commit()
            return

        # only admin attributes from this point on
        if not g.user.is_admin:
            abort(403)

        if args.get('state'):
            state = args.get('state')
            if state not in ApplicationSession.VALID_STATES:
                abort(422)
            application_session.state = args['state']
            if application_session.state == ApplicationSession.STATE_RUNNING:
                if not application_session.provisioned_at:
                    application_session.provisioned_at = datetime.now(timezone.utc)
            if application_session.state == ApplicationSession.STATE_FAILED:
                application_session.errored = True
            if application_session.state == ApplicationSession.STATE_DELETED:
                delete_logs_from_db(application_session_id)
            db.session.commit()

        if args.get('to_be_deleted'):
            application_session.to_be_deleted = args['to_be_deleted']
            application_session.deprovisioned_at = datetime.now(timezone.utc)
            db.session.commit()

        if args.get('error_msg'):
            application_session.error_msg = args['error_msg']
            db.session.commit()

        if args.get('session_data'):
            try:
                application_session.session_data = json.loads(args['session_data'])
            except ValueError:
                logging.warning("invalid session_data passed to view: %s" % args['session_data'])
            db.session.commit()


class ApplicationSessionLogs(restful.Resource):

    @auth.login_required
    @marshal_with(application_session_log_fields)
    def get(self, application_session_id):
        user = g.user
        parser = reqparse.RequestParser()
        parser.add_argument('log_type', type=str, default=None, required=False, location='args')
        args = parser.parse_args()
        args['application_session_id'] = application_session_id
        application_session = db.session.scalar(rules.generate_application_session_query(user, args))
        if not application_session:
            abort(404)

        application_session_logs = get_logs_from_db(application_session_id, args.get('log_type'))

        return application_session_logs

    @auth.login_required
    @requires_admin
    def patch(self, application_session_id):
        patch_parser = reqparse.RequestParser()
        patch_parser.add_argument('log_record', type=dict)
        args = patch_parser.parse_args()

        if args.get('log_record'):
            log_record = args['log_record']

            application_session_log = None
            # provisioning logs: check if we already have a matching line and can skip adding a duplicate
            if log_record['log_type'] == 'provisioning':
                existing_logs = get_logs_from_db(application_session_id, log_record['log_type'])
                for log_line in existing_logs:
                    if log_line.timestamp == log_record['timestamp'] and log_line.log_type == log_record['log_type']:
                        return 'no change'

            # running logs: patch the existing entry with new timestamp and message
            if log_record['log_type'] == 'running':
                existing_logs = get_logs_from_db(application_session_id, log_record['log_type'])
                if existing_logs:
                    application_session_log = existing_logs[0]
                    application_session_log.timestamp = float(log_record['timestamp'])
                    application_session_log.message = log_record['message']

            # no previous log record found, add a new one to the session
            if not application_session_log:
                application_session_log = ApplicationSessionLog(
                    application_session_id,
                    log_record['log_level'],
                    log_record['log_type'],
                    log_record['timestamp'],
                    log_record['message'],
                )
                db.session.add(application_session_log)

            db.session.commit()

        return 'ok'

    @auth.login_required
    @requires_admin
    def delete(self, application_session_id):
        parser = reqparse.RequestParser()
        parser.add_argument('log_type', type=str, default=None, required=False, location='args')
        args = parser.parse_args()
        delete_logs_from_db(application_session_id, args.get('log_type'))


def get_logs_from_db(application_session_id, log_type=None):
    logs_query = ApplicationSessionLog.query \
        .filter_by(application_session_id=application_session_id) \
        .order_by(ApplicationSessionLog.timestamp)
    if log_type:
        logs_query = logs_query.filter_by(log_type=log_type)
    logs_query = logs_query.order_by(ApplicationSessionLog.timestamp)
    logs = logs_query.all()
    return logs


def delete_logs_from_db(application_session_id, log_type=None):
    application_session_logs = get_logs_from_db(application_session_id, log_type)
    if not application_session_logs:
        logging.debug('There are no application log entries to be deleted')
        return

    for application_session_log in application_session_logs:
        db.session.delete(application_session_log)
    db.session.commit()
