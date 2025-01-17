from datetime import datetime
import time

import flask_restful as restful
from flask import Blueprint as FlaskBlueprint
from flask import abort, request
from flask_restful import marshal_with, fields, reqparse

from pebbles.models import Alert
from pebbles.models import db
from pebbles.utils import requires_admin
from pebbles.views.commons import auth

alerts = FlaskBlueprint('alerts', __name__)

alert_fields = {
    'id': fields.String,
    'target': fields.String,
    'source': fields.String,
    'status': fields.String,
    'first_seen_ts': fields.Integer,
    'last_seen_ts': fields.Integer,
    'data': fields.Raw,
}

# Limit in seconds when alert status is considered expired
EXPIRY_AGE_LIMIT = 60 * 3


class AlertList(restful.Resource):
    get_parser = reqparse.RequestParser()
    get_parser.add_argument('include_archived', type=str, default=None, location='args')
    get_parser.add_argument('since_ts', type=int, default=0, location='args')

    @auth.login_required
    @requires_admin
    @marshal_with(alert_fields)
    def get(self):
        args = self.get_parser.parse_args()

        q = Alert.query
        if not args.get('include_archived'):
            q = q.filter(Alert.status != 'archived')

        if args.get('since_ts'):
            q = q.filter(Alert._last_seen_ts > datetime.fromtimestamp(args.get('since_ts')))

        alerts = q.order_by(Alert._first_seen_ts).all()

        # if an alert with status 'ok' is too old, set it expired
        for alert in alerts:
            if alert.status == 'ok' and alert.last_seen_ts < time.time() - EXPIRY_AGE_LIMIT:
                alert.status = 'data expired'

        return alerts

    @auth.login_required
    @requires_admin
    @marshal_with(alert_fields)
    def post(self):
        res = []

        for entry in request.json:
            target = entry.get('target')
            source = entry.get('source')
            status = entry.get('status')
            data = entry.get('data', dict())
            if not (target and source and status):
                return "target, source and status have to be defined", 422

            alert_id = Alert.generate_alert_id(target, source, data)
            alert = Alert.query.filter_by(id=alert_id).first()
            if not alert:
                alert = Alert(alert_id, target, source, status, data)
                db.session.add(alert)
            else:
                alert.status = status
                alert.last_seen_ts = time.time()
            res.append(alert)

        db.session.commit()

        return res


class AlertView(restful.Resource):
    @auth.login_required
    @requires_admin
    @marshal_with(alert_fields)
    def get(self, id):
        q = Alert.query.filter_by(id=id)
        alert = q.first()
        if not alert:
            abort(404)
        return alert


class AlertReset(restful.Resource):
    @auth.login_required
    @requires_admin
    @marshal_with(alert_fields)
    def post(self, target, source):
        firing_alerts = Alert.query.filter_by(target=target, source=source, status='firing').all()
        for alert in firing_alerts:
            alert.status = 'archived'

        status = 'ok'
        data = dict()

        alert_id = Alert.generate_alert_id(target, source, data)
        alert = Alert.query.filter_by(id=alert_id).first()
        if not alert:
            alert = Alert(alert_id, target, source, status, data)
            db.session.add(alert)
        else:
            alert.last_seen_ts = time.time()

        db.session.commit()
        return firing_alerts


class SystemStatus(restful.Resource):
    @staticmethod
    def get():
        active_alerts = Alert.query.filter(Alert.status != 'archived').all()

        for alert in active_alerts:
            if alert.status == 'firing' or alert.last_seen_ts < time.time() - EXPIRY_AGE_LIMIT:
                return 'warning'

        return 'ok'
