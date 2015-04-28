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
}

variables = Blueprint('variables', __name__)


@variables.route('/')
class VariableList(restful.Resource):
    @auth.login_required
    @requires_admin
    @marshal_with(variable_fields)
    def get(self):
        return Variable.query.all()


@variables.route('/<string:variable_id>')
class VariableView(restful.Resource):
    @auth.login_required
    @requires_admin
    def put(self, variable_id):
        form = VariableForm()
        if not form.validate_on_submit():
            logging.warn("validation error on variable form: %s" % form.errors)
            return form.errors, 422
        variable = Variable.query.filter_by(id=variable_id).first()
        if not variable:
            abort(404)
        variable.key = form.key.data
        variable.value = form.value.data
        db.session.commit()

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
