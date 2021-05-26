import datetime
import logging
import uuid

import flask_restful as restful
from flask import Blueprint as FlaskBlueprint
from flask import abort, g
from flask_restful import fields, reqparse
from sqlalchemy.orm.session import make_transient

from pebbles import rules
from pebbles.forms import EnvironmentForm
from pebbles.models import db, Environment, EnvironmentTemplate, Workspace, Instance
from pebbles.rules import apply_rules_environments
from pebbles.utils import requires_workspace_owner_or_admin, requires_admin
from pebbles.views.commons import auth, requires_workspace_manager_or_admin, is_workspace_manager

environments = FlaskBlueprint('environments', __name__)

environment_fields_admin = {
    'id': fields.String(attribute='id'),
    'name': fields.String,
    'description': fields.String,
    'status': fields.String,
    'maximum_lifetime': fields.Integer,
    'labels': fields.List(fields.String),
    'template_id': fields.String,
    'template_name': fields.String,
    'is_enabled': fields.Boolean,
    'cluster': fields.String,
    'config': fields.Raw,
    'full_config': fields.Raw,
    'schema': fields.Raw,
    'form': fields.Raw,
    'workspace_id': fields.String,
    'workspace_name': fields.String,
    'workspace_pseudonym': fields.String,
}

environment_fields_manager = {
    'id': fields.String(attribute='id'),
    'name': fields.String,
    'description': fields.String,
    'status': fields.String,
    'maximum_lifetime': fields.Integer,
    'labels': fields.List(fields.String),
    'template_id': fields.String,
    'template_name': fields.String,
    'is_enabled': fields.Boolean,
    'cluster': fields.String,
    'config': fields.Raw,
    'full_config': fields.Raw,
    'schema': fields.Raw,
    'form': fields.Raw,
    'workspace_id': fields.String,
    'workspace_name': fields.String,
}

environment_fields_user = {
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


def marshal_based_on_role(user, environment):
    workspace = environment.workspace
    if user.is_admin:
        return restful.marshal(environment, environment_fields_admin)
    elif rules.is_user_manager_in_workspace(user, workspace):
        return restful.marshal(environment, environment_fields_manager)
    else:
        return restful.marshal(environment, environment_fields_user)


class EnvironmentList(restful.Resource):
    get_parser = reqparse.RequestParser()
    get_parser.add_argument('show_all', type=bool, default=False, location='args')

    @auth.login_required
    def get(self):
        args = self.get_parser.parse_args()
        user = g.user
        query = apply_rules_environments(user, args)
        # sort the results based on the workspace name first and then by environment name
        query = query.join(Workspace, Environment.workspace).order_by(Workspace.name).order_by(Environment.name)
        results = []
        for environment in query.all():
            environment = process_environment(environment)
            results.append(marshal_based_on_role(user, environment))
        return results

    @auth.login_required
    @requires_workspace_manager_or_admin
    def post(self):
        form = EnvironmentForm()
        if not form.validate_on_submit():
            logging.warning("Form validation error on create environment %s" % form.errors)
            return form.errors, 422
        user = g.user
        environment = Environment()
        template_id = form.template_id.data
        template = EnvironmentTemplate.query.filter_by(id=template_id).first()
        if not template:
            abort(422)
        environment.template_id = template_id
        workspace_id = form.workspace_id.data
        workspace = Workspace.query.filter_by(id=workspace_id).first()
        if not workspace:
            abort(422)
        if not user.is_admin and not is_workspace_manager(user, workspace):
            logging.warning("invalid workspace for the user")
            abort(403)
        # check workspace quota
        if not user.is_admin and len([e for e in workspace.environments]) >= workspace.environment_quota:
            logging.warning("Maximum number of environments in workspace reached %s" + workspace.id)
            return dict(
                message="You have reached the maximum number of environments for this workspace."
                        "Contact support if you need more."
            ), 422

        environment.name = form.name.data
        environment.description = form.description.data
        environment.workspace_id = workspace_id
        environment.maximum_lifetime = form.maximum_lifetime.data
        try:
            validate_max_lifetime_environment(environment)  # Validate the maximum lifetime from config
        except ValueError:
            return 'Invalid lifetime for environment', 422

        # for json lists, we need to use raw_data
        environment.labels = form.labels.raw_data
        environment.config = form.config.data
        environment.is_enabled = form.is_enabled.data

        db.session.add(environment)
        db.session.commit()

        environment.workspace = workspace
        return marshal_based_on_role(user, environment)


class EnvironmentView(restful.Resource):
    @auth.login_required
    def get(self, environment_id):
        user = g.user
        parser = reqparse.RequestParser()
        parser.add_argument('show_all', type=bool, default=False, location='args')
        args = parser.parse_args()
        args['environment_id'] = environment_id
        logging.debug('environmentview get args %s', args)

        query = apply_rules_environments(user, args)
        environment = query.first()
        if not environment:
            abort(404)

        environment = process_environment(environment)
        return marshal_based_on_role(user, environment)

    @auth.login_required
    @requires_workspace_manager_or_admin
    def put(self, environment_id):
        form = EnvironmentForm()
        if not form.validate_on_submit():
            logging.warning("validation error on update environment config")
            return form.errors, 422

        user = g.user
        environment = Environment.query.filter_by(id=environment_id).first()
        if not environment:
            abort(404)

        if environment.status in (Environment.STATUS_ARCHIVED, Environment.STATUS_DELETED):
            abort(422)

        if not user.is_admin and not is_workspace_manager(user, environment.workspace):
            logging.warning("invalid workspace for the user")
            abort(403)

        environment.name = form.name.data
        environment.description = form.description.data

        # for json lists, we need to use raw_data
        environment.labels = form.labels.raw_data
        environment.config = form.config.data
        logging.debug('got %s %s %s', environment.name, environment.description, environment.labels)

        if form.is_enabled.raw_data:
            environment.is_enabled = form.is_enabled.raw_data[0]
        else:
            environment.is_enabled = False

        try:
            validate_max_lifetime_environment(environment)  # Validate the maximum lifetime from config
        except ValueError:
            max_lifetime_error = {
                "invalid maximum lifetime": "invalid maximum lifetime %s" % environment.maximum_lifetime
            }
            return max_lifetime_error, 422
        db.session.add(environment)
        db.session.commit()

    @auth.login_required
    @requires_admin
    def patch(self, environment_id):
        parser = reqparse.RequestParser()
        parser.add_argument('status', type=str)
        args = self.parser.parse_args()
        environment = Environment.query.filter_by(id=environment_id).first()
        if not environment:
            abort(404)

        if args.get('status'):
            environment.status = args['status']
            environment.is_enabled = False
            db.session.commit()

    @auth.login_required
    @requires_workspace_owner_or_admin
    def delete(self, environment_id):
        user = g.user
        query = apply_rules_environments(user, dict(environment_id=environment_id))
        environment = query.first()
        environment_instances = Instance.query.filter_by(environment_id=environment_id).all()
        if not environment:
            logging.warning("trying to delete non-existing environment")
            abort(404)
        elif not (user.is_admin or is_workspace_manager(user, environment.workspace)):
            abort(403)
        elif environment.status == Environment.STATUS_ARCHIVED:
            abort(403)

        if not environment_instances:
            db.session.delete(environment)
            db.session.commit()
        elif environment_instances:
            for instance in environment_instances:
                if instance.state != Instance.STATE_DELETED:
                    instance.to_be_deleted = True
                    instance.state = Instance.STATE_DELETING
                    instance.deprovisioned_at = datetime.datetime.utcnow()
            environment.status = environment.STATUS_DELETED
            db.session.commit()
        else:
            abort(422)


class EnvironmentCopy(restful.Resource):
    @auth.login_required
    @requires_workspace_manager_or_admin
    def put(self, environment_id):
        user = g.user
        environment = Environment.query.get_or_404(environment_id)

        if not environment.status == Environment.STATUS_ACTIVE:
            abort(422)
        if not user.is_admin and not is_workspace_manager(user, environment.workspace):
            logging.warning(
                "user is {} not workspace manager for environment {}".format(user.id, environment.workspace.id))
            abort(403)

        db.session.expunge(environment)
        make_transient(environment)
        environment.id = uuid.uuid4().hex
        environment.name = format("%s - %s" % (environment.name, 'Copy'))
        db.session.add(environment)
        db.session.commit()


def process_environment(environment):
    user = g.user

    # shortcut properties for UI
    environment.template_name = environment.template.name
    environment.workspace_name = environment.workspace.name
    environment.workspace_pseudonym = environment.workspace.pseudonym

    # rest of the code taken for refactoring from single environment GET query
    environment.cluster = environment.template.cluster
    if user.is_admin or is_workspace_manager(user, environment.workspace):
        environment.manager = True

    return environment


def validate_max_lifetime_environment(environment):
    """Checks if the maximum lifetime for environment:
      - lower than the one defined in the template
      - higher than zero"""
    if not getattr(environment, 'template', None):
        template = EnvironmentTemplate.query.filter_by(id=environment.template_id).first()
    else:
        template = environment.template

    if 'maximum_lifetime' in template.base_config:
        template_max_lifetime = int(template.base_config['maximum_lifetime'])
    else:
        template_max_lifetime = 3600

    # valid case
    if 0 < environment.maximum_lifetime <= template_max_lifetime:
        return

    raise ValueError('Invalid maximum_lifetime %d for environment %s' % (
        environment.maximum_lifetime, environment.name))
