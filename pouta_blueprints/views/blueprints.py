from flask.ext.restful import marshal_with, fields
from flask import abort, g
from flask import Blueprint as FlaskBlueprint

import logging

from pouta_blueprints.models import db, Blueprint, Plugin
from pouta_blueprints.forms import BlueprintForm
from pouta_blueprints.server import restful
from pouta_blueprints.views.commons import auth
from pouta_blueprints.utils import requires_admin

blueprints = FlaskBlueprint('blueprints', __name__)

MAX_ACTIVATION_TOKENS_PER_USER = 3


blueprint_fields = {
    'id': fields.String(attribute='id'),
    'maximum_lifetime': fields.Integer,
    'name': fields.String,
    'is_enabled': fields.Boolean,
    'plugin': fields.String,
    'config': fields.Raw,
    'schema': fields.Raw,
    'form': fields.Raw
}


@blueprints.route('/')
class BlueprintList(restful.Resource):
    @auth.login_required
    @marshal_with(blueprint_fields)
    def get(self):
        query = Blueprint.query
        if not g.user.is_admin:
            query = query.filter_by(is_enabled=True)

        results = []
        for blueprint in query.all():
            plugin = Plugin.query.filter_by(id=blueprint.plugin).first()
            blueprint.schema = plugin.schema
            blueprint.form = plugin.form
            results.append(blueprint)
        return results

    @auth.login_required
    @requires_admin
    def post(self):
        form = BlueprintForm()
        if not form.validate_on_submit():
            logging.warn("validation error on create blueprint")
            return form.errors, 422

        blueprint = Blueprint()
        blueprint.name = form.name.data
        blueprint.plugin = form.plugin.data
        blueprint.config = form.config.data

        for config_key in ('maximum_lifetime', 'preallocated_credits', 'cost_multiplier'):
            if config_key in form.config.data:
                try:
                    setattr(blueprint, config_key, int(form.config.data[config_key]))
                except:
                    logging.warn('unable to parse %s for a blueprint, got %s' % (config_key, form.config.data[config_key]))

        db.session.add(blueprint)
        db.session.commit()


@blueprints.route('/<string:blueprint_id>')
class BlueprintView(restful.Resource):
    @auth.login_required
    @marshal_with(blueprint_fields)
    def get(self, blueprint_id):
        return Blueprint.query.filter_by(id=blueprint_id).first()

    @auth.login_required
    @requires_admin
    def put(self, blueprint_id):
        form = BlueprintForm()
        if not form.validate_on_submit():
            logging.warn("validation error on update blueprint config")
            return form.errors, 422

        blueprint = Blueprint.query.filter_by(id=blueprint_id).first()
        if not blueprint:
            abort(404)
        blueprint.name = form.name.data
        blueprint.config = form.config.data
        if 'maximum_lifetime' in blueprint.config:
            try:
                blueprint.maximum_lifetime = int(blueprint.config['maximum_lifetime'])
            except:
                pass

        blueprint.plugin = form.plugin.data
        blueprint.is_enabled = form.is_enabled.data

        db.session.add(blueprint)
        db.session.commit()
