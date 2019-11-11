from flask_restful import marshal_with, reqparse
from flask import abort, g
from flask import Blueprint as FlaskBlueprint
from flask_restful import fields
from sqlalchemy.orm.session import make_transient

import logging
import uuid

from pebbles.models import db, BlueprintTemplate, Plugin
from pebbles.forms import BlueprintTemplateForm
from pebbles.server import restful
from pebbles.views.commons import auth, requires_group_manager_or_admin
from pebbles.utils import requires_admin, parse_maximum_lifetime
from pebbles.rules import apply_rules_blueprint_templates

blueprint_templates = FlaskBlueprint('blueprint_templates', __name__)

blueprint_template_fields = {
    'id': fields.String(attribute='id'),
    'name': fields.String,
    'is_enabled': fields.Boolean,
    'plugin': fields.String,
    'config': fields.Raw,
    'schema': fields.Raw,
    'form': fields.Raw,
    'allowed_attrs': fields.Raw,
    'blueprint_schema': fields.Raw,
    'blueprint_form': fields.Raw,
    'blueprint_model': fields.Raw
}


class BlueprintTemplateList(restful.Resource):
    @auth.login_required
    @requires_group_manager_or_admin
    @marshal_with(blueprint_template_fields)
    def get(self):
        user = g.user
        query = apply_rules_blueprint_templates(user)
        query = query.order_by(BlueprintTemplate.name)
        results = []
        for blueprint_template in query.all():
            plugin = Plugin.query.filter_by(id=blueprint_template.plugin).first()
            blueprint_template.schema = plugin.schema
            blueprint_template.form = plugin.form
            # Due to immutable nature of config field, whole dict needs to be reassigned.
            # Issue #444 in github
            blueprint_template_config = blueprint_template.config
            blueprint_template_config['name'] = blueprint_template.name
            blueprint_template.config = blueprint_template_config

            results.append(blueprint_template)
        return results

    @auth.login_required
    @requires_admin
    def post(self):
        form = BlueprintTemplateForm()
        if not form.validate_on_submit():
            logging.warning("validation error on create blueprint_template")
            return form.errors, 422
        blueprint_template = BlueprintTemplate()
        blueprint_template.name = form.name.data
        blueprint_template.plugin = form.plugin.data

        config = form.config.data
        config.pop('name', None)
        blueprint_template.config = config
        try:
            validate_max_lifetime_template(config)  # Validate the maximum lifetime from config
        except ValueError:
            timeformat_error = {"timeformat error": "pattern should be [days]d [hours]h [minutes]m"}
            return timeformat_error, 422

        if isinstance(form.allowed_attrs.data, dict):  # WTForms can only fetch a dict
            blueprint_template.allowed_attrs = form.allowed_attrs.data['allowed_attrs']
            blueprint_template = blueprint_schemaform_config(blueprint_template)

        db.session.add(blueprint_template)
        db.session.commit()


class BlueprintTemplateView(restful.Resource):
    parser = reqparse.RequestParser()
    parser.add_argument('disable_blueprints', type=bool)

    @auth.login_required
    @requires_group_manager_or_admin
    @marshal_with(blueprint_template_fields)
    def get(self, template_id):
        args = {'template_id': template_id}
        query = apply_rules_blueprint_templates(g.user, args)
        blueprint_template = query.first()
        if not blueprint_template:
            abort(404)
        return blueprint_template

    @auth.login_required
    @requires_admin
    def put(self, template_id):
        form = BlueprintTemplateForm()
        if not form.validate_on_submit():
            logging.warning("validation error on update blueprint_template config")
            return form.errors, 422

        blueprint_template = BlueprintTemplate.query.filter_by(id=template_id).first()
        if not blueprint_template:
            abort(404)
        blueprint_template.name = form.config.data.get('name') or form.name.data
        blueprint_template.plugin = form.plugin.data

        config = form.config.data
        config.pop('name', None)
        blueprint_template.config = config
        try:
            validate_max_lifetime_template(config)  # Validate the maximum lifetime from config
        except ValueError:
            timeformat_error = {"timeformat error": "pattern should be [days]d [hours]h [minutes]m"}
            return timeformat_error, 422
        if isinstance(form.allowed_attrs.data, dict):  # WTForms can only fetch a dict
            blueprint_template.allowed_attrs = form.allowed_attrs.data['allowed_attrs']
            blueprint_template = blueprint_schemaform_config(blueprint_template)

        args = self.parser.parse_args()
        blueprint_template = toggle_enable_template(form, args, blueprint_template)

        db.session.add(blueprint_template)
        db.session.commit()


class BlueprintTemplateCopy(restful.Resource):
    @auth.login_required
    @requires_admin
    def put(self, template_id):
        template = BlueprintTemplate.query.get_or_404(template_id)

        db.session.expunge(template)
        make_transient(template)
        template.id = uuid.uuid4().hex
        template.name = format("%s - %s" % (template.name, 'Copy'))
        db.session.add(template)
        db.session.commit()


def toggle_enable_template(form, args, blueprint_template):
    """Logic for activating and deactivating a blueprint template"""
    if form.is_enabled.raw_data:
        blueprint_template.is_enabled = form.is_enabled.raw_data[0]  # WTForms Issue#451
    else:
        blueprint_template.is_enabled = False
        if args.get('disable_blueprints'):
            # Disable all associated blueprints
            blueprints = blueprint_template.blueprints
            for blueprint in blueprints:
                blueprint.is_enabled = False
    return blueprint_template


def blueprint_schemaform_config(blueprint_template):
    """Generates config,schema and model objects used in schemaform ui component for blueprints"""
    plugin = Plugin.query.filter_by(id=blueprint_template.plugin).first()
    schema = plugin.schema
    blueprint_schema = {'type': 'object', 'title': 'Comment', 'description': 'Description', 'required': ['name', 'description'], 'properties': {}}
    config = blueprint_template.config
    blueprint_model = {}

    allowed_attrs = blueprint_template.allowed_attrs
    blueprint_form = allowed_attrs
    allowed_attrs = ['name', 'description'] + allowed_attrs
    for attr in allowed_attrs:
        blueprint_schema['properties'][attr] = schema['properties'][attr]
        if attr in ('name', 'description'):
            blueprint_model[attr] = ''
        else:
            blueprint_model[attr] = config[attr]

    blueprint_form = [
        {
            "key": "name",
            "type": "textfield",
            "placeholder": "Blueprint name"
        },
        {
            "key": "description",
            "type": "textarea",
            "placeholder": "Blueprint details"
        }
    ] + blueprint_form

    blueprint_template.blueprint_schema = blueprint_schema
    blueprint_template.blueprint_form = blueprint_form
    blueprint_template.blueprint_model = blueprint_model

    return blueprint_template


def validate_max_lifetime_template(config):
    """Checks if the maximum lifetime has a valid pattern"""
    if 'maximum_lifetime' in config:
        max_life_str = str(config['maximum_lifetime'])
        if max_life_str:
            parse_maximum_lifetime(max_life_str)
