from flask import g
from flask_restful import fields, marshal_with
from flask import Blueprint as FlaskBlueprint
import logging

from pebbles.models import db, Blueprint, BlueprintTemplate, Plugin, Workspace
import flask_restful as restful
from pebbles.views.commons import auth, requires_workspace_manager_or_admin
from pebbles.views.blueprint_templates import blueprint_schemaform_config
from pebbles.utils import requires_admin
from pebbles.rules import apply_rules_export_blueprints
from pebbles.forms import BlueprintImportForm, BlueprintTemplateImportForm

import_export = FlaskBlueprint('import_export', __name__)

template_export_fields = {
    'name': fields.String,
    'is_enabled': fields.Boolean,
    'plugin_name': fields.String,
    'config': fields.Raw,
    'allowed_attrs': fields.Raw
}

blueprint_export_fields = {
    'maximum_lifetime': fields.Integer,
    'name': fields.String,
    'is_enabled': fields.Boolean,
    'template_name': fields.String,
    'config': fields.Raw,
    'workspace_name': fields.String
}


class ImportExportBlueprintTemplates(restful.Resource):
    @auth.login_required
    @requires_admin
    @marshal_with(template_export_fields)
    def get(self):
        query = BlueprintTemplate.query

        templates = query.all()

        results = []
        for template in templates:
            plugin = Plugin.query.filter_by(id=template.plugin).first()
            obj = {
                'name': template.name,
                'is_enabled': template.is_enabled,
                'config': template.config,
                'allowed_attrs': template.allowed_attrs,
                'plugin_name': plugin.name
            }
            results.append(obj)

        return results

    @auth.login_required
    @requires_admin
    def post(self):
        form = BlueprintTemplateImportForm()

        if not form.validate_on_submit():
            logging.warning(form.errors)
            logging.warning("validation error on create blueprint")
            return form.errors, 422

        plugin_name = form.plugin_name.data
        plugin = Plugin.query.filter_by(name=plugin_name).first()

        if not plugin:
            logging.warning('no plugins found with name %s', plugin_name)
            return {"error": "No plugins found"}, 404

        template = BlueprintTemplate()
        template.name = form.name.data
        template.plugin = plugin.id
        template.config = form.config.data

        if isinstance(form.allowed_attrs.data, dict):  # WTForms can only fetch a dict
            template.allowed_attrs = form.allowed_attrs.data['allowed_attrs']
            template = blueprint_schemaform_config(template)
        db.session.add(template)
        db.session.commit()


class ImportExportBlueprints(restful.Resource):
    @auth.login_required
    @requires_workspace_manager_or_admin
    @marshal_with(blueprint_export_fields)
    def get(self):
        user = g.user
        query = apply_rules_export_blueprints(user)
        blueprints = query.all()

        results = []
        for blueprint in blueprints:
            template = BlueprintTemplate.query.filter_by(id=blueprint.template_id).first()
            obj = {
                'name': blueprint.name,
                'maximum_lifetime': blueprint.maximum_lifetime,
                'is_enabled': blueprint.is_enabled,
                'config': blueprint.config,
                'template_name': template.name,
                'workspace_name': blueprint.workspace.name
            }
            results.append(obj)
        return results

    @auth.login_required
    @requires_workspace_manager_or_admin
    def post(self):
        form = BlueprintImportForm()

        if not form.validate_on_submit():
            logging.warning(form.errors)
            logging.warning("validation error on creating blueprints with import")
            return form.errors, 422

        template_name = form.template_name.data
        template = BlueprintTemplate.query.filter_by(name=template_name).first()
        if not template:
            logging.warning('no blueprint template found with name %s', template_name)
            return {"error": "No blueprint template found"}, 404

        workspace_name = form.workspace_name.data
        workspace = Workspace.query.filter_by(name=workspace_name).first()
        if not workspace:
            logging.warning('no workspace found with name %s', workspace_name)
            return {"error": "No workspace found"}, 404

        blueprint = Blueprint()
        blueprint.name = form.name.data
        blueprint.template_id = template.id
        blueprint.workspace_id = workspace.id
        blueprint.config = form.config.data

        db.session.add(blueprint)
        db.session.commit()
