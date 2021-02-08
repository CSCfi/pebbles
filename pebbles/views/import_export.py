from flask import g
from flask_restful import fields, marshal_with
from flask import Blueprint as FlaskBlueprint
import logging

from pebbles.models import db, Environment, EnvironmentTemplate, Workspace
import flask_restful as restful
from pebbles.views.commons import auth, requires_workspace_manager_or_admin, match_cluster
from pebbles.utils import requires_admin
from pebbles.rules import apply_rules_export_environments
from pebbles.forms import EnvironmentImportForm, EnvironmentTemplateImportForm

import_export = FlaskBlueprint('import_export', __name__)

template_export_fields = {
    'name': fields.String,
    'is_enabled': fields.Boolean,
    'cluster_name': fields.String,
    'config': fields.Raw,
    'allowed_attrs': fields.Raw
}

environment_export_fields = {
    'maximum_lifetime': fields.Integer,
    'name': fields.String,
    'is_enabled': fields.Boolean,
    'template_name': fields.String,
    'config': fields.Raw,
    'workspace_name': fields.String
}


class ImportExportEnvironmentTemplates(restful.Resource):
    @auth.login_required
    @requires_admin
    @marshal_with(template_export_fields)
    def get(self):
        query = EnvironmentTemplate.query

        templates = query.all()

        results = []
        for template in templates:
            selected_cluster = match_cluster(template.cluster)
            obj = {
                'name': template.name,
                'is_enabled': template.is_enabled,
                'base_config': template.base_config,
                'allowed_attrs': template.allowed_attrs,
                'cluster_name': selected_cluster['name']
            }
            results.append(obj)

        return results

    @auth.login_required
    @requires_admin
    def post(self):
        form = EnvironmentTemplateImportForm()

        if not form.validate_on_submit():
            logging.warning(form.errors)
            logging.warning("validation error on create environment")
            return form.errors, 422

        template = EnvironmentTemplate()
        template.name = form.name.data
        selected_cluster = match_cluster(form.cluster_name.data)
        template.cluster = selected_cluster["name"]

        if isinstance(form.allowed_attrs.data, dict):  # WTForms can only fetch a dict
            template.allowed_attrs = form.allowed_attrs.data['allowed_attrs']
        db.session.add(template)
        db.session.commit()


class ImportExportEnvironments(restful.Resource):
    @auth.login_required
    @requires_workspace_manager_or_admin
    @marshal_with(environment_export_fields)
    def get(self):
        user = g.user
        query = apply_rules_export_environments(user)
        environments = query.all()

        results = []
        for environment in environments:
            template = EnvironmentTemplate.query.filter_by(id=environment.template_id).first()
            obj = {
                'name': environment.name,
                'maximum_lifetime': environment.maximum_lifetime,
                'is_enabled': environment.is_enabled,
                'config': environment.config,
                'template_name': template.name,
                'workspace_name': environment.workspace.name
            }
            results.append(obj)
        return results

    @auth.login_required
    @requires_workspace_manager_or_admin
    def post(self):
        form = EnvironmentImportForm()

        if not form.validate_on_submit():
            logging.warning(form.errors)
            logging.warning("validation error on creating environments with import")
            return form.errors, 422

        template_name = form.template_name.data
        template = EnvironmentTemplate.query.filter_by(name=template_name).first()
        if not template:
            logging.warning('no environment template found with name %s', template_name)
            return {"error": "No environment template found"}, 404

        workspace_name = form.workspace_name.data
        workspace = Workspace.query.filter_by(name=workspace_name).first()
        if not workspace:
            logging.warning('no workspace found with name %s', workspace_name)
            return {"error": "No workspace found"}, 404

        environment = Environment()
        environment.name = form.name.data
        environment.template_id = template.id
        environment.workspace_id = workspace.id
        environment.config = form.config.data

        db.session.add(environment)
        db.session.commit()
