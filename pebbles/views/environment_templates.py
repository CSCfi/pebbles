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
from pebbles.utils import requires_admin, parse_maximum_lifetime
from pebbles.views.commons import auth, requires_workspace_manager_or_admin, match_cluster

environment_templates = FlaskBlueprint('environment_templates', __name__)

environment_template_fields = {
    'id': fields.String(attribute='id'),
    'name': fields.String,
    'is_enabled': fields.Boolean,
    'cluster': fields.String,
    'config': fields.Raw,
    'schema': fields.Raw,
    'form': fields.Raw,
    'allowed_attrs': fields.Raw,
    'environment_schema': fields.Raw,
    'environment_form': fields.Raw,
    'environment_model': fields.Raw
}


class EnvironmentTemplateList(restful.Resource):
    @auth.login_required
    @requires_workspace_manager_or_admin
    @marshal_with(environment_template_fields)
    def get(self):
        user = g.user
        query = apply_rules_environment_templates(user)
        query = query.order_by(EnvironmentTemplate.name)
        results = []
        for environment_template in query.all():
            selected_cluster = match_cluster(environment_template.cluster)
            environment_template.schema = selected_cluster["schema"]
            environment_template.form = selected_cluster["form"]
            # Due to immutable nature of config field, whole dict needs to be reassigned.
            environment_template_config = environment_template.config if environment_template.config else {}
            environment_template_config['name'] = environment_template.name
            environment_template.config = environment_template_config

            results.append(environment_template)
        return results

    @auth.login_required
    @requires_admin
    def post(self):
        form = EnvironmentTemplateForm()
        if not form.validate_on_submit():
            logging.warning("validation error on create environment_template")
            return form.errors, 422
        environment_template = EnvironmentTemplate()
        environment_template.name = form.name.data
        environment_template.cluster = form.cluster.data

        config = form.config.data
        config.pop('name', None)
        environment_template.config = config
        try:
            validate_max_lifetime_template(config)  # Validate the maximum lifetime from config
        except ValueError:
            timeformat_error = {"timeformat error": "pattern should be [days]d [hours]h [minutes]m"}
            return timeformat_error, 422

        if isinstance(form.allowed_attrs.data, dict):  # WTForms can only fetch a dict
            environment_template.allowed_attrs = form.allowed_attrs.data['allowed_attrs']
            environment_template = environment_schemaform_config(environment_template)

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
        environment_template.name = form.config.data.get('name') or form.name.data
        environment_template.cluster = form.cluster.data

        config = form.config.data
        config.pop('name', None)
        environment_template.config = config
        try:
            validate_max_lifetime_template(config)  # Validate the maximum lifetime from config
        except ValueError:
            timeformat_error = {"timeformat error": "pattern should be [days]d [hours]h [minutes]m"}
            return timeformat_error, 422
        if isinstance(form.allowed_attrs.data, dict):  # WTForms can only fetch a dict
            environment_template.allowed_attrs = form.allowed_attrs.data['allowed_attrs']
            environment_template = environment_schemaform_config(environment_template)

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


def environment_schemaform_config(environment_template):
    """Generates config,schema and model objects used in schemaform ui component for environments"""
    selected_cluster = match_cluster(environment_template.cluster)
    environment_schema = dict(
        type='object',
        title='Comment',
        description='Description',
        required=['name', 'description'],
        properties={}
    )
    config = environment_template.config
    environment_model = {}

    allowed_attrs = environment_template.allowed_attrs
    environment_form = allowed_attrs
    allowed_attrs = ['name', 'description'] + allowed_attrs
    for attr in allowed_attrs:
        environment_schema['properties'][attr] = selected_cluster['schema']['properties'][attr]
        if attr in ('name', 'description'):
            environment_model[attr] = ''
        else:
            environment_model[attr] = config[attr]

    # add common fields to form
    environment_form.insert(0, dict(key="name", type="textfield", placeholder="Environment name"))
    environment_form.insert(1, dict(key="description", type="textarea", placeholder="Environment details"))

    environment_template.environment_schema = environment_schema
    environment_template.environment_form = environment_form
    environment_template.environment_model = environment_model

    return environment_template


def validate_max_lifetime_template(config):
    """Checks if the maximum lifetime has a valid pattern"""
    if 'maximum_lifetime' in config:
        max_life_str = str(config['maximum_lifetime'])
        if max_life_str:
            parse_maximum_lifetime(max_life_str)
