from flask.ext.restful import fields, marshal_with
from flask import abort, Blueprint

import logging

from pouta_blueprints.models import db, Variable
from pouta_blueprints.forms import VariableForm
from pouta_blueprints.server import restful
from pouta_blueprints.views.commons import auth
from pouta_blueprints.utils import requires_admin

variable_fields = {
    'id': fields.String,
    'key': fields.String,
    'value': fields.String,
    't': fields.String,
}


variables = Blueprint('variables', __name__)


class VariableList(restful.Resource):
    @auth.login_required
    @requires_admin
    @marshal_with(variable_fields)
    def get(self):
        return Variable.query.all()

    @auth.login_required
    @requires_admin
    def post(self):
        form = VariableForm()
        if not form.validate_on_submit():
            logging.warn("validation error on variable form: %s" % form.errors)
            return form.errors, 422
        variable = Variable()
        variable.key = form.key.data
        variable.value = form.value.data
        db.session.add(variable)
        db.session.commit()


class VariableView(restful.Resource):
    @auth.login_required
    @requires_admin
    @marshal_with(variable_fields)
    def get(self, variable_id_or_name):
        variable = Variable.query.filter_by(key=variable_id_or_name).first()
        if not variable:
            variable = Variable.query.filter_by(id=variable_id_or_name).first()
        if not variable:
            abort(404)
        return variable

    @auth.login_required
    @requires_admin
    def put(self, variable_id):
        form = VariableForm()
        if not form.validate_on_submit():
            logging.warn("validation error on variable form: %s" % form.errors)
            return form.errors, 422
        existing_variable = Variable.query.filter_by(key=form.key.data).first()
        if existing_variable and existing_variable.id != variable_id:
            abort(409)
        variable = Variable.query.filter_by(id=variable_id).first()
        if not variable:
            abort(404)
        if variable.readonly:
            logging.warn("unable to modify readonly variables")
            abort(400)
        variable.key = form.key.data
        variable.value = form.value.data
        db.session.commit()
