from flask.ext.restful import marshal_with
from flask import abort
from flask import Blueprint as FlaskBlueprint
from flask.ext.restful import fields

import logging

from pouta_blueprints.models import db, BlueprintTemplate, Plugin
from pouta_blueprints.forms import BlueprintTemplateForm
from pouta_blueprints.server import restful
from pouta_blueprints.views.commons import auth
from pouta_blueprints.utils import requires_admin, requires_group_owner_or_admin

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
    @requires_group_owner_or_admin
    @marshal_with(blueprint_template_fields)
    def get(self):
        query = BlueprintTemplate.query
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
            logging.warn("validation error on create blueprint_template")
            return form.errors, 422
        blueprint_template = BlueprintTemplate()
        blueprint_template.name = form.name.data
        blueprint_template.plugin = form.plugin.data

        config = form.config.data
        config.pop('name', None)
        blueprint_template.config = config
        if isinstance(form.allowed_attrs.data, dict):  # WTForms can only fetch a dict
            blueprint_template.allowed_attrs = form.allowed_attrs.data['allowed_attrs']
            blueprint_template = blueprint_schemaform_config(blueprint_template)

        db.session.add(blueprint_template)
        db.session.commit()


class BlueprintTemplateView(restful.Resource):
    @auth.login_required
    @requires_group_owner_or_admin
    @marshal_with(blueprint_template_fields)
    def get(self, template_id):
        query = BlueprintTemplate.query.filter_by(id=template_id)
        blueprint_template = query.first()
        if not blueprint_template:
            abort(404)
        return blueprint_template

    @auth.login_required
    @requires_admin
    def put(self, template_id):
        form = BlueprintTemplateForm()
        if not form.validate_on_submit():
            logging.warn("validation error on update blueprint_template config")
            return form.errors, 422

        blueprint_template = BlueprintTemplate.query.filter_by(id=template_id).first()
        if not blueprint_template:
            abort(404)

        blueprint_template.name = form.config.data.get('name') or form.name.data
        blueprint_template.plugin = form.plugin.data

        config = form.config.data
        config.pop('name', None)
        blueprint_template.config = config
        if isinstance(form.allowed_attrs.data, dict):  # WTForms can only fetch a dict
            blueprint_template.allowed_attrs = form.allowed_attrs.data['allowed_attrs']
            blueprint_template = blueprint_schemaform_config(blueprint_template)

        if form.is_enabled.raw_data:
            blueprint_template.is_enabled = form.is_enabled.raw_data[0]
        else:
            blueprint_template.is_enabled = False
        db.session.add(blueprint_template)
        db.session.commit()


def blueprint_schemaform_config(blueprint_template):

    plugin = Plugin.query.filter_by(id=blueprint_template.plugin).first()
    schema = plugin.schema
    blueprint_schema = {'type': 'object', 'title': 'Comment', 'description': 'Description', 'required': ['name', 'description'], 'properties': {}}
    config = blueprint_template.config
    blueprint_model = {}

    allowed_attrs = blueprint_template.allowed_attrs
    allowed_attrs = ['name', 'description'] + allowed_attrs
    for attr in allowed_attrs:
        blueprint_schema['properties'][attr] = schema['properties'][attr]
        if attr in ('name', 'description'):
            blueprint_model[attr] = 'your value'
        else:
            blueprint_model[attr] = config[attr]
    blueprint_form = allowed_attrs
    blueprint_template.blueprint_schema = blueprint_schema
    blueprint_template.blueprint_form = blueprint_form
    blueprint_template.blueprint_model = blueprint_model

    return blueprint_template
