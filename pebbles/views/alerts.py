import time

import flask_restful as restful
from flask import Blueprint as FlaskBlueprint
from flask import abort, request
from flask_restful import marshal_with, fields

from pebbles.models import Alert
from pebbles.models import db
from pebbles.utils import requires_admin
from pebbles.views.commons import auth

alerts = FlaskBlueprint('alerts', __name__)

alert_fields = {
    'target': fields.String,
    'source': fields.String,
    'status': fields.String,
    'data': fields.Raw,
    'update_ts': fields.Integer
}

# Limit in seconds when alert status is considered expired
AGE_LIMIT = 60 * 3


class AlertList(restful.Resource):
    @auth.login_required
    @requires_admin
    @marshal_with(alert_fields)
    def get(self):
        res = Alert.query.all()
        for alert in res:
            if alert.update_ts < time.time() - AGE_LIMIT:
                alert.status = 'data expired'
        return res

    @auth.login_required
    @requires_admin
    @marshal_with(alert_fields)
    def post(self):
        target = request.json.get('target')
        source = request.json.get('source')
        if not (target and source):
            return "target and source have to be defined", 422

        status = request.json.get('status')
        data = request.json.get('data', '[]')

        alert = Alert.query.filter_by(target=target, source=source).first()
        if not alert:
            alert = Alert(target, source, status, data)
            db.session.add(alert)
        else:
            alert.status = status
            alert.data = data
            alert.update_ts = time.time()

        db.session.commit()

        return alert


class AlertView(restful.Resource):
    @auth.login_required
    @requires_admin
    @marshal_with(alert_fields)
    def get(self, target, source):
        q = Alert.query.filter_by(target=target, source=source)
        alert = q.first()
        if not alert:
            abort(404)
        return alert


class SystemStatus(restful.Resource):
    @staticmethod
    def get():
        for alert in Alert.query.all():
            if alert.status != 'ok' or alert.update_ts < time.time() - AGE_LIMIT:
                return 'warning'

        return 'ok'
