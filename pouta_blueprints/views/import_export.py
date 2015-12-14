from flask.ext.restful import fields
from flask import Blueprint as FlaskBlueprint
import logging

from flask.ext.restful import marshal_with
from flask import g

from pouta_blueprints.models import db, Blueprint, Plugin
from pouta_blueprints.server import restful
from pouta_blueprints.views.commons import auth
from pouta_blueprints.utils import requires_admin
from pouta_blueprints.forms import BlueprintImportForm

import_export = FlaskBlueprint('import_export', __name__)

blueprint_export_fields = {
    'maximum_lifetime': fields.Integer,
    'name': fields.String,
    'is_enabled': fields.Boolean,
    'plugin_name': fields.String,
    'config': fields.Raw,
}


class ImportExportBlueprints(restful.Resource):
    @auth.login_required
    @marshal_with(blueprint_export_fields)
    def get(self):
        query = Blueprint.query
        if not g.user.is_admin:
            query = query.filter_by(is_enabled=True)

        blueprints = query.all()

        results = []
        for blueprint in blueprints:
            plugin = Plugin.query.filter_by(id=blueprint.plugin).first()
            obj = {'name': blueprint.name, 'maximum_lifetime': blueprint.maximum_lifetime, 'is_enabled': blueprint.is_enabled, 'config': blueprint.config, 'plugin_name': plugin.name}
            results.append(obj)

        return results

    @auth.login_required
    @requires_admin
    def post(self):
        form = BlueprintImportForm()
        logging.warn(form.data)
        logging.warn(form.blueprints.data)
        if not form.validate_on_submit():
            logging.warn(form.errors)
            logging.warn("validation error on create blueprint")
            return form.errors, 422

        for blueprint_form in form.data.blueprints:

            plugin_name = blueprint_form.plugin_name.data
            plugin = Plugin.query.filter_by(name=plugin_name)

            blueprint = Blueprint()
            blueprint.name = blueprint_form.name.data
            blueprint.plugin = plugin.id
            blueprint.config = blueprint_form.config.data

            db.session.add(blueprint)
            db.session.commit()
