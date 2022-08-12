from flask import g
from flask_restful import fields, marshal_with
from flask import Blueprint as FlaskBlueprint
import logging

from pebbles.models import db, Application, ApplicationTemplate, Workspace
import flask_restful as restful
from pebbles.views.commons import auth, requires_workspace_manager_or_admin, match_cluster, is_workspace_manager
from pebbles.utils import requires_admin
from pebbles.rules import apply_rules_export_applications
from pebbles.forms import ApplicationImportForm, ApplicationTemplateImportForm

import_export = FlaskBlueprint('import_export', __name__)

template_export_fields = {
    'name': fields.String,
    'is_enabled': fields.Boolean,
    'cluster_name': fields.String,
    'config': fields.Raw,
    'attribute_limits': fields.Raw
}

application_export_fields = {
    'maximum_lifetime': fields.Integer,
    'name': fields.String,
    'is_enabled': fields.Boolean,
    'template_name': fields.String,
    'config': fields.Raw,
    'workspace_name': fields.String
}


class ImportExportApplicationTemplates(restful.Resource):
    @auth.login_required
    @requires_admin
    @marshal_with(template_export_fields)
    def get(self):
        query = ApplicationTemplate.query

        templates = query.all()

        results = []
        for template in templates:
            obj = {
                'name': template.name,
                'is_enabled': template.is_enabled,
                'base_config': template.base_config,
                'attribute_limits': template.attribute_limits,
            }
            results.append(obj)

        return results

    @auth.login_required
    @requires_admin
    def post(self):
        form = ApplicationTemplateImportForm()

        if not form.validate_on_submit():
            logging.warning(form.errors)
            logging.warning("validation error on create application")
            return form.errors, 422

        template = ApplicationTemplate()
        template.name = form.name.data
        selected_cluster = match_cluster(form.cluster_name.data)
        template.cluster = selected_cluster["name"]

        if isinstance(form.attribute_limits.data, dict):  # WTForms can only fetch a dict
            template.attribute_limits = form.attribute_limits.data['attribute_limits']
        db.session.add(template)
        db.session.commit()


class ImportExportApplications(restful.Resource):
    @auth.login_required
    @requires_workspace_manager_or_admin
    @marshal_with(application_export_fields)
    def get(self):
        user = g.user
        query = apply_rules_export_applications(user)
        applications = query.all()

        results = []
        for application in applications:
            template = ApplicationTemplate.query.filter_by(id=application.template_id).first()
            obj = {
                'name': application.name,
                'maximum_lifetime': application.maximum_lifetime,
                'is_enabled': application.is_enabled,
                'config': application.config,
                'template_name': template.name,
                'workspace_name': application.workspace.name
            }
            results.append(obj)
        return results

    @auth.login_required
    @requires_workspace_manager_or_admin
    def post(self):
        user = g.user
        form = ApplicationImportForm()

        if not form.validate_on_submit():
            logging.warning(form.errors)
            logging.warning("validation error on creating applications with import")
            return form.errors, 422

        template_name = form.template_name.data
        template = ApplicationTemplate.query.filter_by(name=template_name).first()
        if not template:
            logging.warning('no application template found with name %s', template_name)
            return {"error": "No application template found"}, 404

        workspace_name = form.workspace_name.data
        workspace = Workspace.query.filter_by(name=workspace_name).first()
        if not user.is_admin:
            if not workspace or not is_workspace_manager(user, workspace):
                logging.warning('no workspace found with name %s', workspace_name)
                return {"error": "No workspace found"}, 404

        application = Application()
        application.name = form.name.data
        application.template_id = template.id
        application.workspace_id = workspace.id
        application.config = form.config.data
        application.base_config = template.base_config
        application.attribute_limits = template.attribute_limits

        db.session.add(application)
        db.session.commit()
