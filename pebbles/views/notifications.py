from flask_restful import fields, marshal_with, reqparse
from flask import abort, g, Blueprint

import logging

from pebbles.models import db, Notification, User
from pebbles.forms import NotificationForm
from pebbles.server import restful
from pebbles.views.commons import auth
from pebbles.utils import requires_admin
import datetime

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
    parser.add_argument('show_all', type=bool, default=False, location='args')
    parser.add_argument('show_recent', type=bool, default=False, location='args')

    @auth.login_required
    @marshal_with(notification_fields)
    def get(self):
        args = self.parser.parse_args()
        if args.get('show_all'):
            return Notification.query.all()
        if args.get('show_recent'):
            timevalue = datetime.datetime.utcnow() - datetime.timedelta(minutes=1)  # minute before the current time
            recent_notifications = Notification.query.filter(Notification.broadcasted >= timevalue).all()
            return recent_notifications

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
    parser = reqparse.RequestParser()
    parser.add_argument('send_mail', type=bool, default=False)
    parser.add_argument('send_mail_group_owner', type=bool, default=False)

    @auth.login_required
    @marshal_with(notification_fields)
    def get(self, notification_id):
        notification = Notification.query.filter_by(id=notification_id).first()
        if not notification:
            abort(404)
        return notification

    @auth.login_required
    @marshal_with(notification_fields)
    def patch(self, notification_id):
        text = {"subject": " ", "message": " "}
        args = self.parser.parse_args()
        notification = Notification.query.filter_by(id=notification_id).first()
        current_user = get_current_user()
        if not notification:
            abort(404)
        if current_user.is_admin is True and args.get('send_mail'):
            Users = User.query.filter_by(is_active='t')
            for user in Users:
                if user.eppn != 'worker@pebbles':
                    text['subject'] = notification.subject
                    text['message'] = notification.message
                    logging.warning('email sending not implemented')
        if current_user.is_admin is True and args.get('send_mail_group_owner'):
            Users = User.query.filter_by(is_group_owner='t')
            for user in Users:
                if user.eppn != 'worker@pebbles':
                    text['subject'] = notification.subject
                    text['message'] = notification.message
                    logging.warning('email sending not implemented')
        else:
            current_user.latest_seen_notification_ts = notification.broadcasted
            db.session.commit()

    @auth.login_required
    @requires_admin
    def put(self, notification_id):
        notification = Notification.query.filter_by(id=notification_id).first()
        if not notification:
            abort(404)

        form = NotificationForm()
        if not form.validate_on_submit():
            logging.warn("validation error on update notification")
            return form.errors, 422

        notification.subject = form.subject.data
        notification.message = form.message.data
        notification.broadcasted = datetime.datetime.utcnow()

        db.session.commit()

    @auth.login_required
    @requires_admin
    def delete(self, notification_id):
        notification = Notification.query.filter_by(id=notification_id).first()
        if not notification:
            abort(404)
        db.session.delete(notification)
        db.session.commit()
