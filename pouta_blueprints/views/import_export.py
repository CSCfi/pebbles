from flask.ext.restful import fields
from flask import Blueprint as FlaskBlueprint
import logging

from flask.ext.restful import marshal_with

from pouta_blueprints.models import db, Blueprint, Plugin
from pouta_blueprints.server import restful
from pouta_blueprints.views.commons import auth
from pouta_blueprints.utils import requires_admin
from pouta_blueprints.forms import BlueprintImportFormField
import re

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
    @requires_admin
    @marshal_with(blueprint_export_fields)
    def get(self):
        query = Blueprint.query

        blueprints = query.all()

        results = []
        for blueprint in blueprints:
            plugin = Plugin.query.filter_by(id=blueprint.plugin).first()
            obj = \
                {'name': blueprint.name, 'maximum_lifetime': blueprint.maximum_lifetime,
                 'is_enabled': blueprint.is_enabled, 'config': blueprint.config, 'plugin_name': plugin.name}
            results.append(obj)

        return results

    @auth.login_required
    @requires_admin
    def post(self):
        form = BlueprintImportFormField()

        if not form.validate_on_submit():
            logging.warn(form.errors)
            logging.warn("validation error on create blueprint")
            return form.errors, 422

        # for blueprint_form in form.data.blueprints:

        plugin_name = form.plugin_name.data
        plugin = Plugin.query.filter_by(name=plugin_name).first()

        blueprint = Blueprint()
        blueprint.name = form.name.data
        blueprint.plugin = plugin.id
        blueprint.config = form.config.data

        if 'preallocated_credits' in form.config.data:
            try:
                blueprint.preallocated_credits = bool(form.config.data['preallocated_credits'])
            except:
                pass

        if 'maximum_lifetime' in form.config.data:

            timeformat_error = {"timeformat error": "pattern should be [days]d [hours]h [minutes]m"}
            try:
                max_life_str = str(form.config.data['maximum_lifetime'])
                if max_life_str:
                    m = re.match(r'^(\d+d\s?)?(\d{1,2}h\s?)?(\d{1,2}m\s?)??$', max_life_str)

                    if m:
                        days = hours = mins = 0
                        if m.group(1):
                            days = int(m.group(1).strip()[:-1])
                        if m.group(2):
                            hours = int(m.group(2).strip()[:-1])
                        if m.group(3):
                            mins = int(m.group(3).strip()[:-1])

                        blueprint.maximum_lifetime = days * 86400 + hours * 3600 + mins * 60

                    else:
                        return timeformat_error, 422
                else:
                    blueprint.maximum_lifetime = 3600  # Default value if not provided anything by user
            except:
                return timeformat_error, 422

        if 'cost_multiplier' in form.config.data:
            try:
                blueprint.cost_multiplier = float(form.config.data['cost_multiplier'])
            except:
                pass

        db.session.add(blueprint)
        db.session.commit()
