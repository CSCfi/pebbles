import datetime
import logging
import uuid

import flask_restful as restful
from flask import Blueprint as FlaskBlueprint
from flask import abort, g
from flask_restful import fields, reqparse
from sqlalchemy.orm.session import make_transient

from pebbles import rules
from pebbles.forms import ApplicationForm
from pebbles.models import db, Application, ApplicationTemplate, Workspace, ApplicationSession
from pebbles.rules import apply_rules_applications
from pebbles.utils import requires_workspace_owner_or_admin, requires_admin
from pebbles.views.commons import auth, requires_workspace_manager_or_admin, is_workspace_manager

applications = FlaskBlueprint('applications', __name__)

application_fields_admin = {
    'id': fields.String(attribute='id'),
    'name': fields.String,
    'description': fields.String,
    'status': fields.String,
    'maximum_lifetime': fields.Integer,
    'labels': fields.List(fields.String),
    'template_id': fields.String,
    'template_name': fields.String,
    'is_enabled': fields.Boolean,
    'config': fields.Raw,
    'full_config': fields.Raw,
    'workspace_id': fields.String,
    'workspace_name': fields.String,
    'workspace_pseudonym': fields.String,
}

application_fields_manager = {
    'id': fields.String(attribute='id'),
    'name': fields.String,
    'description': fields.String,
    'status': fields.String,
    'maximum_lifetime': fields.Integer,
    'labels': fields.List(fields.String),
    'template_id': fields.String,
    'template_name': fields.String,
    'is_enabled': fields.Boolean,
    'config': fields.Raw,
    'full_config': fields.Raw,
    'workspace_id': fields.String,
    'workspace_name': fields.String,
}

application_fields_user = {
    'id': fields.String(attribute='id'),
    'name': fields.String,
    'description': fields.String,
    'status': fields.String,
    'maximum_lifetime': fields.Integer,
    'labels': fields.List(fields.String),
    'is_enabled': fields.Boolean,
    'workspace_id': fields.String,
    'workspace_name': fields.String,
}


def marshal_based_on_role(user, application):
    workspace = application.workspace
    if user.is_admin:
        return restful.marshal(application, application_fields_admin)
    elif rules.is_user_manager_in_workspace(user, workspace):
        return restful.marshal(application, application_fields_manager)
    else:
        return restful.marshal(application, application_fields_user)


class ApplicationList(restful.Resource):
    get_parser = reqparse.RequestParser()
    get_parser.add_argument('show_all', type=bool, default=False, location='args')
    get_parser.add_argument('applications_count', type=bool, default=False, location='args')
    get_parser.add_argument('workspace_id', type=str, default=None, required=False, location='args')

    @auth.login_required
    def get(self):
        args = self.get_parser.parse_args()
        user = g.user
        query = apply_rules_applications(user, args)
        # sort the results based on the workspace name first and then by application name
        query = query.join(Workspace, Application.workspace).order_by(Workspace.name).order_by(Application.name)
        results = []
        for application in query.all():
            application = process_application(application)
            results.append(marshal_based_on_role(user, application))
        if args is not None and 'applications_count' in args and args.get('applications_count'):
            return len(results)
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
        if not user.is_admin and not is_workspace_manager(user, workspace):
            logging.warning("invalid workspace for the user")
            abort(403)
        # check workspace quota
        if not user.is_admin and len([e for e in workspace.applications]) >= workspace.application_quota:
            logging.warning("Maximum number of applications in workspace reached %s" + workspace.id)
            return dict(
                message="You have reached the maximum number of applications for this workspace."
                        "Contact support if you need more."
            ), 422

        application.name = form.name.data
        application.description = form.description.data
        application.workspace_id = workspace_id
        application.maximum_lifetime = form.maximum_lifetime.data
        try:
            validate_max_lifetime_application(application)  # Validate the maximum lifetime from config
        except ValueError:
            return 'Invalid lifetime for application', 422

        # for json lists, we need to use raw_data
        application.labels = form.labels.raw_data
        application.config = form.config.data
        application.is_enabled = form.is_enabled.data

        db.session.add(application)
        db.session.commit()

        application.workspace = workspace
        return marshal_based_on_role(user, application)


class ApplicationView(restful.Resource):
    @auth.login_required
    def get(self, application_id):
        user = g.user
        parser = reqparse.RequestParser()
        parser.add_argument('show_all', type=bool, default=False, location='args')
        args = parser.parse_args()
        args['application_id'] = application_id
        logging.debug('environmentview get args %s', args)

        query = apply_rules_applications(user, args)
        application = query.first()
        if not application:
            abort(404)

        application = process_application(application)
        return marshal_based_on_role(user, application)

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

        if not user.is_admin and not is_workspace_manager(user, application.workspace):
            logging.warning("invalid workspace for the user")
            abort(403)

        application.name = form.name.data
        application.description = form.description.data

        # for json lists, we need to use raw_data
        application.labels = form.labels.raw_data
        application.config = form.config.data
        logging.debug('got %s %s %s', application.name, application.description, application.labels)

        if form.is_enabled.raw_data:
            application.is_enabled = form.is_enabled.raw_data[0]
        else:
            application.is_enabled = False

        try:
            validate_max_lifetime_application(application)  # Validate the maximum lifetime from config
        except ValueError:
            max_lifetime_error = {
                "invalid maximum lifetime": "invalid maximum lifetime %s" % application.maximum_lifetime
            }
            return max_lifetime_error, 422
        db.session.add(application)
        db.session.commit()

    @auth.login_required
    @requires_admin
    def patch(self, application_id):
        parser = reqparse.RequestParser()
        parser.add_argument('status', type=str)
        args = self.parser.parse_args()
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
        query = apply_rules_applications(user, dict(application_id=application_id))
        application = query.first()
        application_sessions = ApplicationSession.query.filter_by(application_id=application_id).all()
        if not application:
            logging.warning("trying to delete non-existing application")
            abort(404)
        elif not (user.is_admin or is_workspace_manager(user, application.workspace)):
            abort(403)
        elif application.status == Application.STATUS_ARCHIVED:
            abort(403)

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


class ApplicationCopy(restful.Resource):
    @auth.login_required
    @requires_workspace_manager_or_admin
    def put(self, application_id):
        user = g.user
        application = Application.query.get_or_404(application_id)

        if not application.status == Application.STATUS_ACTIVE:
            abort(422)
        if not user.is_admin and not is_workspace_manager(user, application.workspace):
            logging.warning(
                "user is {} not workspace manager for application {}".format(user.id, application.workspace.id))
            abort(403)

        db.session.expunge(application)
        make_transient(application)
        application.id = uuid.uuid4().hex
        application.name = format("%s - %s" % (application.name, 'Copy'))
        db.session.add(application)
        db.session.commit()


def process_application(application):
    user = g.user

    # shortcut properties for UI
    application.template_name = application.template.name
    application.workspace_name = application.workspace.name
    application.workspace_pseudonym = application.workspace.pseudonym

    # rest of the code taken for refactoring from single application GET query
    application.cluster = application.workspace.cluster
    if user.is_admin or is_workspace_manager(user, application.workspace):
        application.manager = True

    return application


def validate_max_lifetime_application(application):
    """Checks if the maximum lifetime for application:
      - lower than the one defined in the template
      - higher than zero"""
    if not getattr(application, 'template', None):
        template = ApplicationTemplate.query.filter_by(id=application.template_id).first()
    else:
        template = application.template

    if 'maximum_lifetime' in template.base_config:
        template_max_lifetime = int(template.base_config['maximum_lifetime'])
    else:
        template_max_lifetime = 3600

    # valid case
    if 0 < application.maximum_lifetime <= template_max_lifetime:
        return

    raise ValueError('Invalid maximum_lifetime %d for application %s' % (
        application.maximum_lifetime, application.name))
