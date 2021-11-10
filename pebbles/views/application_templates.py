import logging
import uuid

import flask_restful as restful
from flask import Blueprint as FlaskBlueprint
from flask import abort, g
from flask_restful import fields
from flask_restful import marshal_with, reqparse
from sqlalchemy.orm import make_transient

from pebbles.forms import ApplicationTemplateForm
from pebbles.models import db, ApplicationTemplate
from pebbles.rules import apply_rules_application_templates
from pebbles.utils import requires_admin
from pebbles.views.commons import auth, requires_workspace_manager_or_admin

application_templates = FlaskBlueprint('application_templates', __name__)

application_template_fields = {
    'id': fields.String(attribute='id'),
    'name': fields.String,
    'description': fields.String,
    'application_type': fields.String,
    'is_enabled': fields.Boolean,
    'base_config': fields.Raw,
    'allowed_attrs': fields.Raw,
}


class ApplicationTemplateList(restful.Resource):
    @auth.login_required
    @requires_workspace_manager_or_admin
    @marshal_with(application_template_fields)
    def get(self):
        user = g.user
        query = apply_rules_application_templates(user)
        query = query.order_by(ApplicationTemplate.name)
        return query.all()

    @auth.login_required
    @requires_admin
    def post(self):
        form = ApplicationTemplateForm()
        if not form.validate_on_submit():
            logging.warning("validation error on create application_template")
            return form.errors, 422
        application_template = ApplicationTemplate()
        application_template.name = form.name.data
        application_template.is_enabled = form.is_enabled.data

        base_config = form.base_config.data
        base_config.pop('name', None)

        application_template.base_config = base_config

        if isinstance(form.allowed_attrs.data, dict):  # WTForms can only fetch a dict
            application_template.allowed_attrs = form.allowed_attrs.data['allowed_attrs']

        db.session.add(application_template)
        db.session.commit()


class ApplicationTemplateView(restful.Resource):
    parser = reqparse.RequestParser()
    parser.add_argument('disable_applications', type=bool)

    @auth.login_required
    @requires_workspace_manager_or_admin
    @marshal_with(application_template_fields)
    def get(self, template_id):
        args = {'template_id': template_id}
        query = apply_rules_application_templates(g.user, args)
        application_template = query.first()
        if not application_template:
            abort(404)
        return application_template

    @auth.login_required
    @requires_admin
    def put(self, template_id):
        form = ApplicationTemplateForm()
        if not form.validate_on_submit():
            logging.warning("validation error on update application_template config")
            return form.errors, 422

        application_template = ApplicationTemplate.query.filter_by(id=template_id).first()
        if not application_template:
            abort(404)
        application_template.name = form.base_config.data.get('name') or form.name.data

        base_config = form.base_config.data
        base_config.pop('name', None)
        application_template.base_config = base_config
        if isinstance(form.allowed_attrs.data, dict):  # WTForms can only fetch a dict
            application_template.allowed_attrs = form.allowed_attrs.data['allowed_attrs']

        args = self.parser.parse_args()
        application_template = toggle_enable_template(form, args, application_template)

        db.session.add(application_template)
        db.session.commit()


class ApplicationTemplateCopy(restful.Resource):
    @auth.login_required
    @requires_admin
    def put(self, template_id):
        template = ApplicationTemplate.query.get_or_404(template_id)

        db.session.expunge(template)
        make_transient(template)
        template.id = uuid.uuid4().hex
        template.name = format("%s - %s" % (template.name, 'Copy'))
        db.session.add(template)
        db.session.commit()


def toggle_enable_template(form, args, application_template):
    """Logic for activating and deactivating a application template"""
    if form.is_enabled.raw_data:
        application_template.is_enabled = form.is_enabled.raw_data[0]  # WTForms Issue#451
    else:
        application_template.is_enabled = False
        if args.get('disable_applications'):
            # Disable all associated applications
            applications = application_template.applications
            for application in applications:
                application.is_enabled = False
    return application_template
