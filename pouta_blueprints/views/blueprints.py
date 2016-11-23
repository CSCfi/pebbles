from flask.ext.restful import marshal_with, fields
from flask import abort, g
from flask import Blueprint as FlaskBlueprint

import logging

from pouta_blueprints.models import db, Blueprint, BlueprintTemplate, Group
from pouta_blueprints.forms import BlueprintForm
from pouta_blueprints.server import restful
from pouta_blueprints.views.commons import auth, requires_group_manager_or_admin, is_group_manager
from pouta_blueprints.utils import parse_maximum_lifetime, get_full_blueprint_config
from pouta_blueprints.rules import apply_rules_blueprints

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
    'group_id': fields.String,
    'group_name': fields.String,
    'manager': fields.Boolean
}


class BlueprintList(restful.Resource):
    @auth.login_required
    @marshal_with(blueprint_fields)
    def get(self):
        user = g.user
        query = apply_rules_blueprints(user)
        # sort the results based on the group name first and then by blueprint name
        query = query.join(Group, Blueprint.group).order_by(Group.name).order_by(Blueprint.name)
        results = []
        for blueprint in query.all():
            template = blueprint.template
            blueprint.schema = template.blueprint_schema
            blueprint.form = template.blueprint_form
            # Due to immutable nature of config field, whole dict needs to be reassigned.
            # Issue #444 in github
            blueprint_config = blueprint.config
            blueprint.full_config = get_full_blueprint_config(blueprint)
            blueprint_config['name'] = blueprint.name
            blueprint.config = blueprint_config

            blueprint.template_name = template.name
            blueprint.group_name = blueprint.group.name
            if user.is_admin or is_group_manager(user, blueprint.group):
                blueprint.manager = True

            results.append(blueprint)
        return results

    @auth.login_required
    @requires_group_manager_or_admin
    def post(self):
        form = BlueprintForm()
        if not form.validate_on_submit():
            logging.warn("validation error on create blueprint")
            return form.errors, 422
        user = g.user
        blueprint = Blueprint()
        blueprint.name = form.name.data
        template_id = form.template_id.data
        template = BlueprintTemplate.query.filter_by(id=template_id).first()
        if not template:
            abort(422)
        blueprint.template_id = template_id
        group_id = form.group_id.data
        group = Group.query.filter_by(id=group_id).first()
        if not group:
            abort(422)
        if not user.is_admin and not is_group_manager(user, group):
            logging.warn("invalid group for the user")
            abort(403)
        blueprint.group_id = group_id
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
    @auth.login_required
    @marshal_with(blueprint_fields)
    def get(self, blueprint_id):
        args = {'blueprint_id': blueprint_id}
        user = g.user
        query = apply_rules_blueprints(user, args)
        blueprint = query.first()
        if not blueprint:
            abort(404)
        blueprint.plugin = blueprint.template.plugin
        if user.is_admin or blueprint.group in user.managed_groups:
            blueprint.full_config = get_full_blueprint_config(blueprint)
        return blueprint

    @auth.login_required
    @requires_group_manager_or_admin
    def put(self, blueprint_id):
        form = BlueprintForm()
        if not form.validate_on_submit():
            logging.warn("validation error on update blueprint config")
            return form.errors, 422

        user = g.user
        blueprint = Blueprint.query.filter_by(id=blueprint_id).first()
        if not blueprint:
            abort(404)
        # group_id = form.group_id.data
        # group = Group.query.filter_by(id=group_id).first()
        # if not group:
        #    abort(422)
        if not user.is_admin and not is_group_manager(user, blueprint.group):
            logging.warn("invalid group for the user")
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


def validate_max_lifetime_blueprint(blueprint):
    template = BlueprintTemplate.query.filter_by(id=blueprint.template_id).first()
    blueprint.template = template
    full_config = get_full_blueprint_config(blueprint)
    if 'maximum_lifetime' in full_config:
        max_life_str = str(full_config['maximum_lifetime'])
        if max_life_str:
            parse_maximum_lifetime(max_life_str)
