from flask.ext.restful import fields, marshal_with
from flask import abort, Blueprint

import logging
import json

from pebbles.models import db, Plugin
from pebbles.forms import PluginForm
from pebbles.server import restful
from pebbles.views.commons import auth
from pebbles.utils import requires_admin

plugins = Blueprint('plugins', __name__)

plugin_fields = {
    'id': fields.String,
    'name': fields.String,
    'schema': fields.Raw,
    'form': fields.Raw,
    'model': fields.Raw,
}


class PluginList(restful.Resource):
    @auth.login_required
    @requires_admin
    @marshal_with(plugin_fields)
    def get(self):
        return Plugin.query.all()

    @auth.login_required
    @requires_admin
    def post(self):
        form = PluginForm()
        if not form.validate_on_submit():
            logging.warn("validation error on update blueprint config")
            return form.errors, 422

        plugin = Plugin.query.filter_by(name=form.plugin.data).first()
        if not plugin:
            plugin = Plugin()
            plugin.name = form.plugin.data

        plugin.schema = json.loads(form.schema.data)
        plugin.form = json.loads(form.form.data)
        plugin.model = json.loads(form.model.data)

        db.session.add(plugin)
        db.session.commit()


class PluginView(restful.Resource):
    @auth.login_required
    @requires_admin
    @marshal_with(plugin_fields)
    def get(self, plugin_id):
        plugin = Plugin.query.filter_by(id=plugin_id).first()
        if not plugin:
            abort(404)
        return plugin
