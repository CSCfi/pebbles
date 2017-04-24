from flask.ext.restful import fields, marshal_with
from flask import abort, Blueprint

import logging

from pebbles.models import db, Variable
from pebbles.forms import VariableForm
from pebbles.server import restful
from pebbles.views.commons import auth
from pebbles.utils import requires_admin

variable_fields = {
    'id': fields.String,
    'key': fields.String,
    'value': fields.Raw,
    'readonly': fields.Boolean,
    't': fields.String,
}


variables = Blueprint('variables', __name__)
PUBLIC_CONFIG_VARIABLES = (
    'ENABLE_SHIBBOLETH_LOGIN',
    'INSTALLATION_NAME',
    'INSTALLATION_DESCRIPTION',
    'BRAND_IMAGE'
)


class VariableList(restful.Resource):
    @auth.login_required
    @requires_admin
    @marshal_with(variable_fields)
    def get(self):
        return Variable.query.order_by(Variable.key).all()

    @auth.login_required
    @requires_admin
    def post(self):
        form = VariableForm()
        if not form.validate_on_submit():
            return form.errors, 422
        variable = Variable(form.key.data, form.value.data)
        db.session.add(variable)
        db.session.commit()


class VariableView(restful.Resource):
    @auth.login_required
    @requires_admin
    @marshal_with(variable_fields)
    def get(self, variable_id):
        # accept both id and name
        variable = Variable.query.filter_by(key=variable_id).first()
        if not variable:
            variable = Variable.query.filter_by(id=variable_id).first()
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
            return {'error': 'duplicate key'}, 409
        variable = Variable.query.filter_by(id=variable_id).first()
        if not variable:
            abort(404)
        if variable.readonly:
            logging.warn("unable to modify readonly variables")
            return {'error': 'unable to modify readonly variable'}, 409
        variable.key = form.key.data
        variable.value = form.value.data
        db.session.commit()


class PublicVariableList(restful.Resource):
    """The list of variables that are needed for the frontend to construct a branded page.
    Installation name, logo url etc.

    Additionally this is the only API call that does not require authentication and therefore it is a good place to
    monitor that the back-end (and database connection) are healthy.
    """

    @marshal_with(variable_fields)
    def get(self):
        try:
            return Variable.query.filter(Variable.key.in_(PUBLIC_CONFIG_VARIABLES)).order_by(Variable.key).all()
        except Exception as ex:
            logging.error("error in retrieving variables" + str(ex))
            return []
