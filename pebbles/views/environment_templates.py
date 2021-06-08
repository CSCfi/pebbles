import logging
import uuid

import flask_restful as restful
from flask import Blueprint as FlaskBlueprint
from flask import abort, g
from flask_restful import fields
from flask_restful import marshal_with, reqparse
from sqlalchemy.orm import make_transient

from pebbles.forms import EnvironmentTemplateForm
from pebbles.models import db, EnvironmentTemplate
from pebbles.rules import apply_rules_environment_templates
from pebbles.utils import requires_admin
from pebbles.views.commons import auth, requires_workspace_manager_or_admin

environment_templates = FlaskBlueprint('environment_templates', __name__)

environment_template_fields = {
    'id': fields.String(attribute='id'),
    'name': fields.String,
    'description': fields.String,
    'environment_type': fields.String,
    'is_enabled': fields.Boolean,
    'base_config': fields.Raw,
    'allowed_attrs': fields.Raw,
}


class EnvironmentTemplateList(restful.Resource):
    @auth.login_required
    @requires_workspace_manager_or_admin
    @marshal_with(environment_template_fields)
    def get(self):
        user = g.user
        query = apply_rules_environment_templates(user)
        query = query.order_by(EnvironmentTemplate.name)
        return query.all()

    @auth.login_required
    @requires_admin
    def post(self):
        form = EnvironmentTemplateForm()
        if not form.validate_on_submit():
            logging.warning("validation error on create environment_template")
            return form.errors, 422
        environment_template = EnvironmentTemplate()
        environment_template.name = form.name.data
        environment_template.is_enabled = form.is_enabled.data

        base_config = form.base_config.data
        base_config.pop('name', None)

        environment_template.base_config = base_config

        if isinstance(form.allowed_attrs.data, dict):  # WTForms can only fetch a dict
            environment_template.allowed_attrs = form.allowed_attrs.data['allowed_attrs']

        db.session.add(environment_template)
        db.session.commit()


class EnvironmentTemplateView(restful.Resource):
    parser = reqparse.RequestParser()
    parser.add_argument('disable_environments', type=bool)

    @auth.login_required
    @requires_workspace_manager_or_admin
    @marshal_with(environment_template_fields)
    def get(self, template_id):
        args = {'template_id': template_id}
        query = apply_rules_environment_templates(g.user, args)
        environment_template = query.first()
        if not environment_template:
            abort(404)
        return environment_template

    @auth.login_required
    @requires_admin
    def put(self, template_id):
        form = EnvironmentTemplateForm()
        if not form.validate_on_submit():
            logging.warning("validation error on update environment_template config")
            return form.errors, 422

        environment_template = EnvironmentTemplate.query.filter_by(id=template_id).first()
        if not environment_template:
            abort(404)
        environment_template.name = form.base_config.data.get('name') or form.name.data

        base_config = form.base_config.data
        base_config.pop('name', None)
        environment_template.base_config = base_config
        if isinstance(form.allowed_attrs.data, dict):  # WTForms can only fetch a dict
            environment_template.allowed_attrs = form.allowed_attrs.data['allowed_attrs']

        args = self.parser.parse_args()
        environment_template = toggle_enable_template(form, args, environment_template)

        db.session.add(environment_template)
        db.session.commit()


class EnvironmentTemplateCopy(restful.Resource):
    @auth.login_required
    @requires_admin
    def put(self, template_id):
        template = EnvironmentTemplate.query.get_or_404(template_id)

        db.session.expunge(template)
        make_transient(template)
        template.id = uuid.uuid4().hex
        template.name = format("%s - %s" % (template.name, 'Copy'))
        db.session.add(template)
        db.session.commit()


def toggle_enable_template(form, args, environment_template):
    """Logic for activating and deactivating a environment template"""
    if form.is_enabled.raw_data:
        environment_template.is_enabled = form.is_enabled.raw_data[0]  # WTForms Issue#451
    else:
        environment_template.is_enabled = False
        if args.get('disable_environments'):
            # Disable all associated environments
            environments = environment_template.environments
            for environment in environments:
                environment.is_enabled = False
    return environment_template
