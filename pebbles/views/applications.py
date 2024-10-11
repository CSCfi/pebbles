import datetime
import logging
import uuid

import flask_restful as restful
from flask import Blueprint as FlaskBlueprint
from flask import abort, g, request
from flask_restful import fields, reqparse
from sqlalchemy import select
from sqlalchemy.orm.session import make_transient

from pebbles import rules
from pebbles.forms import ApplicationForm
from pebbles.models import db, Application, ApplicationTemplate, Workspace, ApplicationSession
from pebbles.utils import requires_workspace_owner_or_admin, requires_admin, check_config_against_attribute_limits, \
    check_attribute_limit_format, validate_container_image_url
from pebbles.views import commons
from pebbles.views.commons import auth, requires_workspace_manager_or_admin

applications = FlaskBlueprint('applications', __name__)

application_field_role_map = dict(
    admin={
        'id': fields.String(attribute='id'),
        'name': fields.String,
        'description': fields.String,
        'status': fields.String,
        'maximum_lifetime': fields.Integer,
        'labels': fields.List(fields.String),
        'template_id': fields.String,
        'template_name': fields.String,
        'application_type': fields.String,
        'is_enabled': fields.Boolean,
        'config': fields.Raw,
        'attribute_limits': fields.Raw,
        'workspace_id': fields.String,
        'workspace_name': fields.String,
        'workspace_pseudonym': fields.String,
        'info': {
            'memory': fields.String,
            'memory_gib': fields.Float,
            'shared_folder_enabled': fields.Boolean,
            'work_folder_enabled': fields.Boolean,
            'workspace_expiry_ts': fields.Integer,
            'base_config_image': fields.String,
        },
    },
    manager={
        'id': fields.String(attribute='id'),
        'name': fields.String,
        'description': fields.String,
        'status': fields.String,
        'maximum_lifetime': fields.Integer,
        'labels': fields.List(fields.String),
        'template_id': fields.String,
        'template_name': fields.String,
        'application_type': fields.String,
        'is_enabled': fields.Boolean,
        'config': fields.Raw,
        'attribute_limits': fields.Raw,
        'workspace_id': fields.String,
        'workspace_name': fields.String,
        'info': {
            'memory': fields.String,
            'memory_gib': fields.Float,
            'shared_folder_enabled': fields.Boolean,
            'work_folder_enabled': fields.Boolean,
            'workspace_expiry_ts': fields.Integer,
            'base_config_image': fields.String,
        },
    },
    user={
        'id': fields.String(attribute='id'),
        'name': fields.String,
        'description': fields.String,
        'status': fields.String,
        'maximum_lifetime': fields.Integer,
        'labels': fields.List(fields.String),
        'application_type': fields.String,
        'is_enabled': fields.Boolean,
        'workspace_id': fields.String,
        'workspace_name': fields.String,
        'info': {
            'memory': fields.String,
            'memory_gib': fields.Float,
            'shared_folder_enabled': fields.Boolean,
            'work_folder_enabled': fields.Boolean,
            'workspace_expiry_ts': fields.Integer,
            'base_config_image': fields.String,
        },
    },
)


def extract_role(user, application):
    if user.is_admin:
        return 'admin'
    elif commons.is_workspace_manager(user, application.workspace):
        return 'manager'
    else:
        return 'user'


def marshal_based_on_role(role, application):
    application_fields = application_field_role_map.get(role)
    if not application_fields:
        raise RuntimeError('Unknown role %s passed to marshalling application' % role)
    return restful.marshal(application, application_fields)


class ApplicationList(restful.Resource):
    get_parser = reqparse.RequestParser()
    get_parser.add_argument('show_all', type=bool, default=False, location='args')
    get_parser.add_argument('workspace_id', type=str, default=None, required=False, location='args')

    @auth.login_required
    def get(self):
        args = self.get_parser.parse_args()
        user = g.user
        s = rules.generate_application_query(user, args)
        rows = db.session.execute(s).all()
        results = []
        for row in rows:
            application = process_application(row.Application)
            if user.is_admin:
                results.append(marshal_based_on_role('admin', application))
            elif row.WorkspaceMembership.is_manager:
                results.append(marshal_based_on_role('manager', application))
            else:
                results.append(marshal_based_on_role('user', application))

        return results

    @auth.login_required
    @requires_workspace_manager_or_admin
    def post(self):
        form = ApplicationForm()
        if not form.validate_on_submit():
            logging.warning("Form validation error on create application %s" % form.errors)
            return form.errors, 422
        user = g.user
        application = Application()
        template_id = form.template_id.data
        template = ApplicationTemplate.query.filter_by(id=template_id).first()
        if not template:
            abort(422)
        application.template_id = template_id
        workspace_id = form.workspace_id.data
        workspace = Workspace.query.filter_by(id=workspace_id).first()
        if not workspace:
            abort(422)
        if not user.is_admin and not commons.is_workspace_manager(user, workspace):
            logging.warning("invalid workspace for the user")
            abort(403)

        # check workspace quota
        application_count = workspace.applications.filter_by(status='active').count()
        if not (user.is_admin or application_count < workspace.application_quota):
            logging.warning("Maximum number of applications in workspace reached, ws '%s'", workspace.id)
            return dict(
                message="You have reached the maximum number of applications for this workspace."
                        "Contact support if you need more."
            ), 422
        # basic data
        application.name = form.name.data
        application.description = form.description.data
        application.workspace_id = workspace_id

        # base configuration from template
        application.base_config = template.base_config
        application.attribute_limits = template.attribute_limits
        application.application_type = template.application_type

        # for json lists, we need to use raw_data
        application.labels = form.labels.raw_data

        if "image_url" in form.config.data and form.config.data["image_url"]:
            error = validate_container_image_url(form.config.data["image_url"])
            if error:
                return f'Invalid application config: {error}', 422

        application.config = form.config.data
        application.is_enabled = form.is_enabled.data

        error = check_config_against_attribute_limits(application.config, application.attribute_limits)
        if error:
            return 'Application config failed attribute limit check: %s' % error, 422
        application.maximum_lifetime = application.config.get(
            'maximum_lifetime',
            application.base_config.get('maximum_lifetime', 3600)
        )

        db.session.add(application)
        db.session.commit()

        application.workspace = workspace
        application = process_application(application)
        return marshal_based_on_role(extract_role(user, application), application)


class ApplicationView(restful.Resource):
    @auth.login_required
    def get(self, application_id):
        user = g.user
        parser = reqparse.RequestParser()
        parser.add_argument('show_all', type=bool, default=False, location='args')
        args = parser.parse_args()
        args['application_id'] = application_id

        s = rules.generate_application_query(user, args)
        application = db.session.scalar(s)
        if not application:
            abort(404)

        application = process_application(application)
        return marshal_based_on_role(extract_role(user, application), application)

    @auth.login_required
    @requires_workspace_manager_or_admin
    def put(self, application_id):
        form = ApplicationForm()
        if not form.validate_on_submit():
            logging.warning("validation error on update application config")
            return form.errors, 422

        user = g.user
        application = Application.query.filter_by(id=application_id).first()
        if not application:
            abort(404)

        if application.status in (Application.STATUS_ARCHIVED, Application.STATUS_DELETED):
            abort(422)

        if not user.is_admin and not commons.is_workspace_manager(user, application.workspace):
            logging.warning("invalid workspace for the user")
            abort(403)

        application.name = form.name.data
        application.description = form.description.data

        # for json lists, we need to use raw_data
        application.labels = form.labels.raw_data

        if "image_url" in form.config.data and form.config.data["image_url"]:
            error = validate_container_image_url(form.config.data["image_url"])
            if error:
                return f'Invalid application config: {error}', 422

        application.config = form.config.data

        if form.is_enabled.raw_data:
            application.is_enabled = form.is_enabled.raw_data[0]
        else:
            application.is_enabled = False

        error = check_config_against_attribute_limits(application.config, application.attribute_limits)
        if error:
            return 'Application config failed attribute limit check: %s' % error, 422
        application.maximum_lifetime = application.config.get(
            'maximum_lifetime',
            application.maximum_lifetime
        )

        db.session.commit()
        application = process_application(application)
        return marshal_based_on_role(extract_role(user, application), application)

    @auth.login_required
    @requires_admin
    def patch(self, application_id):
        parser = reqparse.RequestParser()
        parser.add_argument('status', type=str)
        args = parser.parse_args()
        application = Application.query.filter_by(id=application_id).first()
        if not application:
            abort(404)

        if args.get('status'):
            application.status = args['status']
            application.is_enabled = False
            db.session.commit()

    @auth.login_required
    @requires_workspace_owner_or_admin
    def delete(self, application_id):
        user = g.user
        s = rules.generate_application_query(user, dict(application_id=application_id))
        application = db.session.scalar(s)
        if not application:
            logging.warning("trying to delete non-existing application")
            abort(404)
        elif not (user.is_admin or commons.is_workspace_manager(user, application.workspace)):
            abort(403)
        elif application.status == Application.STATUS_ARCHIVED:
            abort(403)

        # Check if sessions have been created, and we need to preserve the Application in 'DELETED' state for statistics
        application_sessions = ApplicationSession.query.filter_by(application_id=application_id).all()
        if not application_sessions:
            db.session.delete(application)
            db.session.commit()
        elif application_sessions:
            for application_session in application_sessions:
                if application_session.state != ApplicationSession.STATE_DELETED:
                    application_session.to_be_deleted = True
                    application_session.state = ApplicationSession.STATE_DELETING
                    application_session.deprovisioned_at = datetime.datetime.utcnow()
            application.status = application.STATUS_DELETED
            db.session.commit()
        else:
            abort(422)


class ApplicationAttributeLimits(restful.Resource):
    @auth.login_required
    @requires_admin
    def put(self, application_id):
        user = g.user
        application = db.session.scalar(rules.generate_application_query(user, dict(application_id=application_id)))

        if not application:
            logging.warning('application %s does not exist', application_id)
            return 'The application does not exist', 404

        attribute_limits = request.get_json().get('attribute_limits', None)
        if not attribute_limits:
            return 'request is missing attribute_limits', 422
        if type(attribute_limits) is not list:
            return 'attribute_limits needs to be a list', 422

        # check that attribute limits are well-formed
        error = check_attribute_limit_format(attribute_limits)
        if error:
            return 'Invalid attribute limit format, error: %s' % error, 422

        # check that current config is valid with the new limits
        error = check_config_against_attribute_limits(application.config, attribute_limits)
        if error:
            return 'Invalid attribute limits, error: %s' % error, 422

        application.attribute_limits = attribute_limits
        db.session.commit()
        return application.attribute_limits


class ApplicationCopy(restful.Resource):
    parser = reqparse.RequestParser()
    parser.add_argument('workspace_id', type=str, default=None, required=False, location='args')

    @auth.login_required
    @requires_workspace_manager_or_admin
    def put(self, application_id):
        user = g.user
        application = Application.query.filter_by(id=application_id).first_or_404()
        args = self.parser.parse_args()

        # Specific target workspace or just cloning in current one?
        if args.get('workspace_id', None):
            target_workspace = Workspace.query.filter_by(id=args.get('workspace_id')).first()
            # check that user has manager rights in the target workspace
            if not (user.is_admin or commons.is_workspace_manager(user, target_workspace)):
                logging.warning(
                    'ApplicationCopy: user {} is not manager in workspace {}'.format(user.id, target_workspace.id))
                abort(403)
        else:
            target_workspace = application.workspace

        # check rights to the source workspace
        if not (user.is_admin or commons.is_workspace_manager(user, application.workspace)):
            logging.warning(
                'ApplicationCopy: user {} is not manager in workspace {}'.format(user.id, target_workspace.id))
            abort(403)

        # check status
        if not application.status == Application.STATUS_ACTIVE:
            abort(422)

        # check workspace quota
        application_count = target_workspace.applications.filter_by(status='active').count()
        if not (user.is_admin or application_count < target_workspace.application_quota):
            logging.warning('Maximum number of applications in workspace reached, ws "%s"', target_workspace.id)

            return dict(message='You have reached the maximum number of applications for this workspace.'
                                'Contact support if you need more.'), 422

        db.session.expunge(application)
        make_transient(application)
        application.id = uuid.uuid4().hex
        application.workspace_id = target_workspace.id
        application.name = format('%s - %s' % (application.name, 'Copy'))
        application.is_enabled = False
        db.session.add(application)
        db.session.commit()


def process_application(application):
    # cache application template names in the request context to avoid lookups on every call
    template_name_cache = g.setdefault('template_name_cache', dict())
    if application.template_id not in template_name_cache.keys():
        result = db.session.execute(
            select(ApplicationTemplate.id, ApplicationTemplate.name)
        ).all()
        for row in result:
            template_name_cache[row[0]] = row[1]

    # shortcut properties for UI
    application.template_name = template_name_cache.get(application.template_id)

    application.workspace_name = application.workspace.name
    application.workspace_pseudonym = application.workspace.pseudonym
    application.workspace_expiry_ts = application.workspace.expiry_ts
    application.base_config_image = application.base_config.get('image')

    # generate human-readable memory information
    memory_gib = float(application.config.get('memory_gib', application.base_config.get('memory_gib')))
    application.memory_gib = memory_gib
    if memory_gib % 1:
        application.memory = '%dMiB' % round(memory_gib * 1024)
    else:
        application.memory = '%dGiB' % memory_gib

    # rest of the code taken for refactoring from single application GET query
    application.cluster = application.workspace.cluster

    if 'enable_user_work_folder' in application.config and application.config['enable_user_work_folder']:
        application.work_folder_enabled = True
    else:
        application.work_folder_enabled = False

    if application.workspace_name.startswith('System.default'):
        application.shared_folder_enabled = False
    elif 'enable_shared_folder' in application.config:
        if application.config['enable_shared_folder']:
            application.shared_folder_enabled = True
        else:
            application.shared_folder_enabled = False
    else:
        application.shared_folder_enabled = True

    return application
