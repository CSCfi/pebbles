import datetime
import logging
import uuid

import flask_restful as restful
from dateutil.relativedelta import relativedelta
from flask import Blueprint as FlaskBlueprint
from flask import abort, g
from flask_restful import marshal_with, fields, reqparse
from sqlalchemy.orm.session import make_transient

from pebbles.forms import BlueprintForm
from pebbles.models import db, Blueprint, BlueprintTemplate, Workspace, Instance
from pebbles.rules import apply_rules_blueprints
from pebbles.utils import parse_maximum_lifetime, requires_workspace_owner_or_admin, requires_admin
from pebbles.views.commons import auth, requires_workspace_manager_or_admin, is_workspace_manager

blueprints = FlaskBlueprint('blueprints', __name__)

MAX_ACTIVATION_TOKENS_PER_USER = 3

blueprint_fields = {
    'id': fields.String(attribute='id'),
    'maximum_lifetime': fields.Integer,
    'name': fields.String,
    'template_id': fields.String,
    'template_name': fields.String,
    'is_enabled': fields.Boolean,
    'plugin': fields.String,
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


class BlueprintList(restful.Resource):
    get_parser = reqparse.RequestParser()
    get_parser.add_argument('show_all', type=bool, default=False, location='args')

    @auth.login_required
    @marshal_with(blueprint_fields)
    def get(self):
        args = self.get_parser.parse_args()
        user = g.user
        query = apply_rules_blueprints(user, args)
        # sort the results based on the workspace name first and then by blueprint name
        query = query.join(Workspace, Blueprint.workspace).order_by(Workspace.name).order_by(Blueprint.name)
        results = []
        for blueprint in query.all():
            blueprint = process_blueprint(blueprint)
            results.append(blueprint)
        return results

    post_parser = reqparse.RequestParser()
    post_parser.add_argument('lifespan_months', type=int, location='json')

    @auth.login_required
    @requires_workspace_manager_or_admin
    def post(self):
        form = BlueprintForm()
        if not form.validate_on_submit():
            logging.warning("validation error on create blueprint")
            return form.errors, 422
        user = g.user
        blueprint = Blueprint()
        blueprint.name = form.name.data
        template_id = form.template_id.data
        template = BlueprintTemplate.query.filter_by(id=template_id).first()
        if not template:
            abort(422)
        blueprint.template_id = template_id
        workspace_id = form.workspace_id.data
        workspace = Workspace.query.filter_by(id=workspace_id).first()
        if not workspace:
            abort(422)
        if not user.is_admin and not is_workspace_manager(user, workspace):
            logging.warning("invalid workspace for the user")
            abort(403)
        user_owned_blueprints = apply_rules_blueprints(user).filter_by(workspace_id=workspace_id).count()
        if not user.blueprint_quota and not user_owned_blueprints:
            user.blueprint_quota = 1
        elif not user.blueprint_quota and user_owned_blueprints:
            user.blueprint_quota = user_owned_blueprints

        if not user.is_admin and user_owned_blueprints >= user.blueprint_quota and user.is_workspace_owner:
            logging.warning("Maximum User_blueprint_quota %s is reached" % user_owned_blueprints)
            return dict(
                message="You reached maximum number of blueprints that can be created."
                        " If you wish create more workspaces contact administrator"
            ), 422

        blueprint.workspace_id = workspace_id

        # System.default blueprints won't get expiry dates
        if workspace.name != 'System.default':
            args = self.post_parser.parse_args()
            if 'lifespan_months' in args and args.lifespan_months:
                if args.lifespan_months < 1:
                    return dict(message="Months until expiry cannot be negative"), 422
                blueprint.expiry_time = datetime.datetime.utcnow() + relativedelta(months=+args.lifespan_months)
            else:
                # default expiry date is 6 months
                blueprint.expiry_time = datetime.datetime.utcnow() + relativedelta(months=+6)

        if 'name' in form.config.data:
            form.config.data.pop('name', None)
        blueprint.config = form.config.data

        try:
            validate_max_lifetime_blueprint(blueprint)  # Validate the maximum lifetime from config
        except ValueError:
            timeformat_error = {"timeformat error": "pattern should be [days]d [hours]h [minutes]m"}
            return timeformat_error, 422

        db.session.add(blueprint)
        db.session.commit()


class BlueprintView(restful.Resource):
    parser = reqparse.RequestParser()
    parser.add_argument('current_status', type=str)

    @auth.login_required
    @marshal_with(blueprint_fields)
    def get(self, blueprint_id):
        args = {'blueprint_id': blueprint_id}
        user = g.user
        query = apply_rules_blueprints(user, args)
        blueprint = query.first()
        if not blueprint:
            abort(404)

        blueprint = process_blueprint(blueprint)
        return blueprint

    @auth.login_required
    @requires_workspace_manager_or_admin
    def put(self, blueprint_id):
        form = BlueprintForm()
        if not form.validate_on_submit():
            logging.warning("validation error on update blueprint config")
            return form.errors, 422

        user = g.user
        blueprint = Blueprint.query.filter_by(id=blueprint_id).first()
        if not blueprint:
            abort(404)

        if blueprint.current_status == 'archived' or blueprint.current_status == 'deleted':
            abort(422)

        if not user.is_admin and not is_workspace_manager(user, blueprint.workspace):
            logging.warning("invalid workspace for the user")
            abort(403)

        blueprint.name = form.config.data.get('name') or form.name.data
        if 'name' in form.config.data:
            form.config.data.pop('name', None)
        blueprint.config = form.config.data

        if form.is_enabled.raw_data:
            blueprint.is_enabled = form.is_enabled.raw_data[0]
        else:
            blueprint.is_enabled = False
        try:
            validate_max_lifetime_blueprint(blueprint)  # Validate the maximum lifetime from config
        except ValueError:
            timeformat_error = {"timeformat error": "pattern should be [days]d [hours]h [minutes]m"}
            return timeformat_error, 422
        db.session.add(blueprint)
        db.session.commit()

    @auth.login_required
    @requires_admin
    def patch(self, blueprint_id):
        args = self.parser.parse_args()
        blueprint = Blueprint.query.filter_by(id=blueprint_id).first()
        if not blueprint:
            abort(404)

        if args.get('current_status'):
            blueprint.current_status = args['current_status']
            blueprint.is_enabled = False
            db.session.commit()

    @auth.login_required
    @requires_workspace_owner_or_admin
    def delete(self, blueprint_id):
        blueprint = Blueprint.query.filter_by(id=blueprint_id).first()
        blueprint_instances = Instance.query.filter_by(blueprint_id=blueprint_id).all()
        if not blueprint:
            logging.warning("trying to delete non-existing blueprint")
            abort(404)
        elif blueprint.current_status == 'archived':
            abort(422)
        elif not blueprint_instances:
            db.session.delete(blueprint)
            db.session.commit()
        elif blueprint_instances:
            for instance in blueprint_instances:
                if instance.state != Instance.STATE_DELETED:
                    instance.to_be_deleted = True
                    instance.state = Instance.STATE_DELETING
                    instance.deprovisioned_at = datetime.datetime.utcnow()
            blueprint.current_status = blueprint.STATE_DELETED
            db.session.commit()
        else:
            abort(422)


class BlueprintCopy(restful.Resource):
    @auth.login_required
    @requires_workspace_manager_or_admin
    def put(self, blueprint_id):
        user = g.user
        blueprint = Blueprint.query.get_or_404(blueprint_id)

        if blueprint.current_status == 'archived' or blueprint.current_status == 'deleted':
            abort(422)
        if not user.is_admin and not is_workspace_manager(user, blueprint.workspace):
            logging.warning("user is {} not workspace manager for blueprint {}".format(user.id, blueprint.workspace.id))
            abort(403)

        db.session.expunge(blueprint)
        make_transient(blueprint)
        blueprint.id = uuid.uuid4().hex
        blueprint.name = format("%s - %s" % (blueprint.name, 'Copy'))
        db.session.add(blueprint)
        db.session.commit()


def process_blueprint(blueprint):
    user = g.user
    template = blueprint.template
    blueprint.schema = template.blueprint_schema
    blueprint.form = template.blueprint_form
    # Due to immutable nature of config field, whole dict needs to be reassigned.
    # Issue #444 in github
    blueprint_config = blueprint.config
    blueprint_config['name'] = blueprint.name
    blueprint.config = blueprint_config

    blueprint.template_name = template.name
    blueprint.workspace_name = blueprint.workspace.name
    # rest of the code taken for refactoring from single blueprint GET query
    blueprint.plugin = blueprint.template.plugin
    if user.is_admin or is_workspace_manager(user, blueprint.workspace):
        blueprint.manager = True
    return blueprint


def validate_max_lifetime_blueprint(blueprint):
    """Checks if the maximum lifetime for blueprint has a valid pattern"""
    template = BlueprintTemplate.query.filter_by(id=blueprint.template_id).first()
    blueprint.template = template
    full_config = blueprint.full_config
    if 'maximum_lifetime' in full_config:
        max_life_str = str(full_config['maximum_lifetime'])
        if max_life_str:
            parse_maximum_lifetime(max_life_str)
