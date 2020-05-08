from flask_restful import fields, marshal_with, reqparse
from flask import abort
from flask import Blueprint as FlaskBlueprint

import logging
import time

from pebbles.models import db, NamespacedKeyValue
from pebbles.forms import NamespacedKeyValueForm
import flask_restful as restful
from pebbles.views.commons import auth
from pebbles.utils import requires_admin

namespaced_keyvalues = FlaskBlueprint('namespaced_keyvalues', __name__)


namespace_fields = {
    'namespace': fields.String,
    'key': fields.String,
    'value': fields.Raw,
    'schema': fields.Raw,
    'created_ts': fields.Float,
    'updated_ts': fields.Float
}


class NamespacedKeyValueList(restful.Resource):
    parser = reqparse.RequestParser()
    parser.add_argument('namespace', type=str)
    parser.add_argument('key', type=str)

    @auth.login_required
    @requires_admin
    @marshal_with(namespace_fields)
    def get(self):
        args = self.parser.parse_args()
        namespaced_query = NamespacedKeyValue.query
        if args.get('namespace'):
            namespaced_query = namespaced_query.filter_by(namespace=args.namespace)
        if args.get('key'):
            namespaced_query = namespaced_query.filter(NamespacedKeyValue.key.like("{0}%".format(args.key)))

        return namespaced_query.all()

    @auth.login_required
    @requires_admin
    def post(self):
        form = NamespacedKeyValueForm()

        if not form.validate_on_submit():
            logging.warning(form.errors)
            logging.warning("validation error on creating namespaced key value data")
            return form.errors, 422

        namespace = form.namespace.data
        key = form.key.data
        schema = form.schema.data
        value = form.value.data
        ns_check = NamespacedKeyValue.query.filter_by(namespace=namespace, key=key).first()
        if ns_check:
            logging.warning("a combination of namespace %s with key %s already exists" % (namespace, key))
            abort(422)
        # Create the object with static (mostly) parameters
        namespaced_keyvalue = NamespacedKeyValue(namespace, key, schema)
        # Then value, which is bound to change often
        namespaced_keyvalue.value = value

        curr_ts = round(time.time(), 2)
        namespaced_keyvalue.created_ts = curr_ts
        namespaced_keyvalue.updated_ts = curr_ts

        db.session.add(namespaced_keyvalue)
        db.session.commit()


class NamespacedKeyValueView(restful.Resource):
    parser = reqparse.RequestParser()

    @auth.login_required
    @requires_admin
    @marshal_with(namespace_fields)
    def get(self, namespace, key):
        namespaced_keyvalue = NamespacedKeyValue.query.filter_by(namespace=namespace, key=key).first()
        if not namespaced_keyvalue:
            logging.warning("no NamespacedKeyValue object found for namespace %s with key %s" % (namespace, key))
            abort(404)
        return namespaced_keyvalue

    @auth.login_required
    @requires_admin
    def put(self, namespace, key):
        form = NamespacedKeyValueForm()

        if not form.validate_on_submit():
            logging.warning(form.errors)
            logging.warning("validation error on modifying namespaced key value data")
            return form.errors, 422
        # check for any discrepancies in the form data, the namespace and key should not change!
        if namespace != form.namespace.data or key != form.key.data:
            logging.warning(
                "namespace and key mismatch in the form data. expected %s and %s, got %s and %s" %
                (namespace, key, form.namespace.data, form.key.data)
            )
            abort(422)

        schema = form.schema.data
        value = form.value.data
        updated_version_ts = float(form.updated_version_ts.data)

        namespaced_keyvalue_query = NamespacedKeyValue.query.filter_by(namespace=namespace, key=key)
        # lock row with FOR UPDATE, for really close race conditions
        namespaced_keyvalue = namespaced_keyvalue_query.with_for_update(nowait=True).first()
        if not namespaced_keyvalue:
            logging.warning("no NamespacedKeyValue object found for namespace %s with key %s" % (namespace, key))
            abort(404)
        # Check for concurrency
        namespaced_keyvalue_updated = namespaced_keyvalue_query.filter_by(updated_ts=updated_version_ts).first()
        if not namespaced_keyvalue_updated:
            logging.warning("trying to modify an outdated record")
            return {'error': 'CONCURRENT_MODIFICATION_EXCEPTION'}, 409

        curr_ts = round(time.time(), 2)
        namespaced_keyvalue.updated_ts = curr_ts
        # If schema changes, assign it first
        namespaced_keyvalue.schema = schema
        # the value needs the latest schema to be present
        namespaced_keyvalue.value = value
        db.session.add(namespaced_keyvalue)
        db.session.commit()

    @auth.login_required
    @requires_admin
    def delete(self, namespace, key):
        namespaced_keyvalue = NamespacedKeyValue.query.filter_by(namespace=namespace, key=key).first()
        if not namespaced_keyvalue:
            logging.warning("no NamespacedKeyValue object found for namespace %s with key %s" % (namespace, key))
            abort(404)
        db.session.delete(namespaced_keyvalue)
        db.session.commit()
