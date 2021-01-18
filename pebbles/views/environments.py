import datetime
import logging
import uuid

import flask_restful as restful
from dateutil.relativedelta import relativedelta
from flask import Blueprint as FlaskBlueprint
from flask import abort, g
from flask_restful import marshal_with, fields, reqparse
from sqlalchemy.orm.session import make_transient

from pebbles.forms import EnvironmentForm
from pebbles.models import db, Environment, EnvironmentTemplate, Workspace, Instance
from pebbles.rules import apply_rules_environments
from pebbles.utils import parse_maximum_lifetime, requires_workspace_owner_or_admin, requires_admin
from pebbles.views.commons import auth, requires_workspace_manager_or_admin, is_workspace_manager

environments = FlaskBlueprint('environments', __name__)

MAX_ACTIVATION_TOKENS_PER_USER = 3

environment_fields = {
    'id': fields.String(attribute='id'),
    'maximum_lifetime': fields.Integer,
    'name': fields.String,
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
    'manager': fields.Boolean,
    'current_status': fields.String,
    'expiry_time': fields.DateTime,
}


class EnvironmentList(restful.Resource):
    get_parser = reqparse.RequestParser()
    get_parser.add_argument('show_all', type=bool, default=False, location='args')

    @auth.login_required
    @marshal_with(environment_fields)
    def get(self):
        args = self.get_parser.parse_args()
        user = g.user
        query = apply_rules_environments(user, args)
        # sort the results based on the workspace name first and then by environment name
        query = query.join(Workspace, Environment.workspace).order_by(Workspace.name).order_by(Environment.name)
        results = []
        for environment in query.all():
            environment = process_environment(environment)
            results.append(environment)
        return results

    post_parser = reqparse.RequestParser()
    post_parser.add_argument('lifespan_months', type=int, location='json')

    @auth.login_required
    @requires_workspace_manager_or_admin
    def post(self):
        form = EnvironmentForm()
        if not form.validate_on_submit():
            logging.warning("Form validation error on create environment %s" % form.errors)
            return form.errors, 422
        user = g.user
        environment = Environment()
        environment.name = form.name.data
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

        environment.workspace_id = workspace_id

        # System.default environments won't get expiry dates
        if workspace.name != 'System.default':
            args = self.post_parser.parse_args()
            if 'lifespan_months' in args and args.lifespan_months:
                if args.lifespan_months < 1:
                    return dict(message="Months until expiry cannot be negative"), 422
                environment.expiry_time = datetime.datetime.utcnow() + relativedelta(months=+args.lifespan_months)
            else:
                # default expiry date is 6 months
                environment.expiry_time = datetime.datetime.utcnow() + relativedelta(months=+6)

        if 'name' in form.config.data:
            form.config.data.pop('name', None)
        # check that config only contains allowed attributes
        check_allowed_attrs_or_abort(form.config.data, template.allowed_attrs)

        environment.config = form.config.data
        environment.is_enabled = form.is_enabled.data

        try:
            validate_max_lifetime_environment(environment)  # Validate the maximum lifetime from config
        except ValueError:
            timeformat_error = {"timeformat error": "pattern should be [days]d [hours]h [minutes]m"}
            return timeformat_error, 422

        db.session.add(environment)
        db.session.commit()

        return restful.marshal(environment, environment_fields), 200


class EnvironmentView(restful.Resource):
    parser = reqparse.RequestParser()
    parser.add_argument('current_status', type=str)

    @auth.login_required
    @marshal_with(environment_fields)
    def get(self, environment_id):
        args = {'environment_id': environment_id}
        user = g.user
        query = apply_rules_environments(user, args)
        environment = query.first()
        if not environment:
            abort(404)

        environment = process_environment(environment)
        return environment

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

        if environment.current_status == 'archived' or environment.current_status == 'deleted':
            abort(422)

        if not user.is_admin and not is_workspace_manager(user, environment.workspace):
            logging.warning("invalid workspace for the user")
            abort(403)

        template = EnvironmentTemplate.query.filter_by(id=environment.template_id).first()
        if not template:
            abort(422)

        environment.name = form.config.data.get('name') or form.name.data
        if 'name' in form.config.data:
            form.config.data.pop('name', None)

        # check that config only contains allowed attributes
        check_allowed_attrs_or_abort(form.config.data, template.allowed_attrs)

        environment.config = form.config.data

        if form.is_enabled.raw_data:
            environment.is_enabled = form.is_enabled.raw_data[0]
        else:
            environment.is_enabled = False
        try:
            validate_max_lifetime_environment(environment)  # Validate the maximum lifetime from config
        except ValueError:
            timeformat_error = {"timeformat error": "pattern should be [days]d [hours]h [minutes]m"}
            return timeformat_error, 422
        db.session.add(environment)
        db.session.commit()

    @auth.login_required
    @requires_admin
    def patch(self, environment_id):
        args = self.parser.parse_args()
        environment = Environment.query.filter_by(id=environment_id).first()
        if not environment:
            abort(404)

        if args.get('current_status'):
            environment.current_status = args['current_status']
            environment.is_enabled = False
            db.session.commit()

    @auth.login_required
    @requires_workspace_owner_or_admin
    def delete(self, environment_id):
        environment = Environment.query.filter_by(id=environment_id).first()
        environment_instances = Instance.query.filter_by(environment_id=environment_id).all()
        if not environment:
            logging.warning("trying to delete non-existing environment")
            abort(404)
        elif environment.current_status == 'archived':
            abort(422)
        elif not environment_instances:
            db.session.delete(environment)
            db.session.commit()
        elif environment_instances:
            for instance in environment_instances:
                if instance.state != Instance.STATE_DELETED:
                    instance.to_be_deleted = True
                    instance.state = Instance.STATE_DELETING
                    instance.deprovisioned_at = datetime.datetime.utcnow()
            environment.current_status = environment.STATE_DELETED
            db.session.commit()
        else:
            abort(422)


class EnvironmentCopy(restful.Resource):
    @auth.login_required
    @requires_workspace_manager_or_admin
    def put(self, environment_id):
        user = g.user
        environment = Environment.query.get_or_404(environment_id)

        if environment.current_status == 'archived' or environment.current_status == 'deleted':
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
    template = environment.template
    environment.schema = template.environment_schema
    environment.form = template.environment_form

    # Due to immutable nature of config field, whole dict needs to be reassigned.
    environment_config = environment.config if environment.config else {}
    environment_config['name'] = environment.name
    environment.config = environment_config

    environment.template_name = template.name
    environment.workspace_name = environment.workspace.name
    # rest of the code taken for refactoring from single environment GET query
    environment.cluster = environment.template.cluster
    if user.is_admin or is_workspace_manager(user, environment.workspace):
        environment.manager = True

    environment.labels = []
    if 'labels' in environment.full_config:
        for label in environment.full_config['labels'].split(','):
            environment.labels.append(label.strip())

    return environment


def validate_max_lifetime_environment(environment):
    """Checks if the maximum lifetime for environment has a valid pattern"""
    template = EnvironmentTemplate.query.filter_by(id=environment.template_id).first()
    environment.template = template
    full_config = environment.full_config
    if 'maximum_lifetime' in full_config:
        max_life_str = str(full_config['maximum_lifetime'])
        if max_life_str:
            parse_maximum_lifetime(max_life_str)


# check that config only contains allowed attributes
def check_allowed_attrs_or_abort(attributes, allowed_attributes):
    if not set(attributes.keys()).issubset(set(allowed_attributes)):
        logging.warning(
            'Possible hacking attempt: environment form config keys vs template allowed attrs: %s %s' % (
                attributes.keys(), allowed_attributes))
        abort(403)
