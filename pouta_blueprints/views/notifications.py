from flask.ext.restful import fields, marshal_with, reqparse
from flask import abort, g, Blueprint

import logging

from pouta_blueprints.models import db, Notification, User
from pouta_blueprints.forms import NotificationForm
from pouta_blueprints.server import restful
from pouta_blueprints.views.commons import auth
from pouta_blueprints.utils import requires_admin

notifications = Blueprint('notifications', __name__)

notification_fields = {
    'id': fields.String,
    'broadcasted': fields.DateTime(dt_format='iso8601'),
    'subject': fields.String,
    'message': fields.String
}


def get_current_user():
    user = g.user
    if not user:
        abort(400)
    current_user = User.query.filter_by(id=user.id).first()
    if not current_user:
        abort(400)
    return current_user


class NotificationList(restful.Resource):
    parser = reqparse.RequestParser()
    parser.add_argument('show_all', type=bool, default=False)

    @auth.login_required
    @marshal_with(notification_fields)
    def get(self):
        args = self.parser.parse_args()
        if args.get('show_all'):
            return Notification.query.all()

        user = get_current_user()
        return user.unseen_notifications()

    @auth.login_required
    @requires_admin
    def post(self):
        form = NotificationForm()
        if not form.validate_on_submit():
            logging.warn("validation error on post new notification")
            return form.errors, 422

        notification = Notification()
        notification.subject = form.subject.data
        notification.message = form.message.data

        db.session.add(notification)
        db.session.commit()


class NotificationView(restful.Resource):
    @auth.login_required
    def put(self, notification_id):
        user = get_current_user()
        notification = Notification.query.filter_by(id=notification_id).first()
        if not notification:
            abort(404)
        user.latest_seen_notification_ts = notification.broadcasted
        db.session.commit()

    @auth.login_required
    @requires_admin
    def delete(self, notification_id):
        notification = Notification.query.filter_by(id=notification_id).first()
        if not notification:
            abort(404)
        db.session.delete(notification)
        db.session.commit()
