from flask.ext.restful import marshal_with, fields
from flask import abort, g
from flask import Blueprint as FlaskBlueprint

import logging

from pouta_blueprints.models import db, Blueprint, Group
from pouta_blueprints.forms import BlueprintForm
from pouta_blueprints.server import restful
from pouta_blueprints.views.commons import auth
from pouta_blueprints.utils import requires_group_owner_or_admin, parse_maximum_lifetime
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
    'owner': fields.Boolean
}


class BlueprintList(restful.Resource):
    @auth.login_required
    @marshal_with(blueprint_fields)
    def get(self):
        user = g.user
        query = apply_rules_blueprints(user)
        query = query.join(Group, Blueprint.group).order_by(Group.name)
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
            if user.is_admin or blueprint.group in user.owned_groups:
                blueprint.owner = True

            results.append(blueprint)
        return results

    @auth.login_required
    @requires_group_owner_or_admin
    def post(self):
        form = BlueprintForm()
        if not form.validate_on_submit():
            logging.warn("validation error on create blueprint")
            return form.errors, 422

        user = g.user
        blueprint = Blueprint()
        blueprint.name = form.name.data

        group_id = form.group_id.data
        group = Group.query.filter_by(id=group_id).first()
        if not user.is_admin and group not in user.owned_groups:
            logging.warn("invalid group for the user")
            abort(406)
        blueprint.group_id = group_id

        form.config.data.pop('name', None)
        blueprint.config = form.config.data
        blueprint.template_id = form.template_id.data
        blueprint = set_blueprint_fields_from_config(blueprint)
        db.session.add(blueprint)
        db.session.commit()


class BlueprintView(restful.Resource):
    @auth.login_required
    @marshal_with(blueprint_fields)
    def get(self, blueprint_id):
        args = {'blueprint_id': blueprint_id}
        query = apply_rules_blueprints(g.user, args)
        blueprint = query.first()
        if not blueprint:
            abort(404)
        blueprint.full_config = get_full_blueprint_config(blueprint)
        blueprint.plugin = blueprint.template.plugin
        return blueprint

    @auth.login_required
    @requires_group_owner_or_admin
    def put(self, blueprint_id):
        form = BlueprintForm()
        if not form.validate_on_submit():
            logging.warn("validation error on update blueprint config")
            return form.errors, 422

        user = g.user
        blueprint = Blueprint.query.filter_by(id=blueprint_id).first()
        if not blueprint:
            abort(404)
        if not user.is_admin and blueprint.group not in user.owned_groups:
            logging.warn("invalid group for the user")
            abort(406)

        blueprint.name = form.config.data.get('name') or form.name.data
        form.config.data.pop('name', None)
        blueprint.config = form.config.data

        blueprint = set_blueprint_fields_from_config(blueprint)

        if form.is_enabled.raw_data:
            blueprint.is_enabled = form.is_enabled.raw_data[0]
        else:
            blueprint.is_enabled = False

        db.session.add(blueprint)
        db.session.commit()


def get_full_blueprint_config(blueprint):

    template = blueprint.template
    allowed_attrs = template.allowed_attrs
    allowed_attrs = ['name', 'description'] + allowed_attrs
    full_config = template.config
    bp_config = blueprint.config
    for attr in allowed_attrs:
        if attr in bp_config:
            full_config[attr] = bp_config[attr]
    return full_config


def set_blueprint_fields_from_config(blueprint):

    config = blueprint.config

    if 'preallocated_credits' in config:
        try:
            blueprint.preallocated_credits = bool(config['preallocated_credits'])
        except:
            pass

    if 'maximum_lifetime' in config:

        timeformat_error = {"timeformat error": "pattern should be [days]d [hours]h [minutes]m"}
        try:
            max_life_str = str(config['maximum_lifetime'])
            if max_life_str:
                maximum_lifetime = parse_maximum_lifetime(max_life_str)
                blueprint.maximum_lifetime = maximum_lifetime
            else:
                blueprint.maximum_lifetime = 3600  # Default value if not provided anything by user
        except ValueError:
            return timeformat_error, 422

        if 'cost_multiplier' in config:
            try:
                blueprint.cost_multiplier = float(config['cost_multiplier'])
            except:
                pass

    return blueprint
