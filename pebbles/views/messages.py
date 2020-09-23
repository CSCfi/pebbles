import datetime
import logging

import flask_restful as restful
from flask import Blueprint as FlaskBlueprint
from flask import abort, g
from flask_restful import reqparse, fields, marshal_with

from pebbles.forms import MessageForm
from pebbles.models import db, Message, User
from pebbles.utils import requires_admin
from pebbles.views.commons import auth

messages = FlaskBlueprint('messages', __name__)

MESSAGE_FIELDS = {
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


class MessageList(restful.Resource):
    parser = reqparse.RequestParser()
    parser.add_argument('show_all', type=bool, default=False, location='args')
    parser.add_argument('show_recent', type=bool, default=False, location='args')

    @auth.login_required
    @marshal_with(MESSAGE_FIELDS)
    def get(self):
        args = self.parser.parse_args()
        if args.get('show_all'):
            return Message.query.all()
        if args.get('show_recent'):
            timevalue = datetime.datetime.utcnow() - datetime.timedelta(minutes=1)  # minute before the current time
            recent_messages = Message.query.filter(Message.broadcasted >= timevalue).all()
            return recent_messages

        user = get_current_user()
        q = Message.query
        if user.latest_seen_message_ts:
            q = q.filter(Message.broadcasted > user.latest_seen_message_ts)
        return q.all()

    @auth.login_required
    @requires_admin
    def post(self):
        form = MessageForm()
        if not form.validate_on_submit():
            logging.warning("validation error on post new message")
            return form.errors, 422

        message = Message()
        message.subject = form.subject.data
        message.message = form.message.data

        db.session.add(message)
        db.session.commit()

        return None


class MessageView(restful.Resource):
    parser = restful.reqparse.RequestParser()
    parser.add_argument('send_mail', type=bool, default=False)
    parser.add_argument('send_mail_group_owner', type=bool, default=False)

    @auth.login_required
    @marshal_with(MESSAGE_FIELDS)
    def get(self, message_id):
        message = Message.query.filter_by(id=message_id).first()
        if not message:
            abort(404)
        return message

    @auth.login_required
    @marshal_with(MESSAGE_FIELDS)
    def patch(self, message_id):
        text = {"subject": " ", "message": " "}
        args = self.parser.parse_args()
        message = Message.query.filter_by(id=message_id).first()
        current_user = get_current_user()
        if not message:
            abort(404)
        if current_user.is_admin is True and args.get('send_mail'):
            users = User.query.filter_by(is_active='t')
            for user in users:
                if user.eppn != 'worker@pebbles':
                    text['subject'] = message.subject
                    text['message'] = message.message
                    logging.warning('email sending not implemented')
        if current_user.is_admin is True and args.get('send_mail_group_owner'):
            users = User.query.filter_by(is_group_owner='t')
            for user in users:
                if user.eppn != 'worker@pebbles':
                    text['subject'] = message.subject
                    text['message'] = message.message
                    logging.warning('email sending not implemented')
        else:
            current_user.latest_seen_message_ts = message.broadcasted
            db.session.commit()

    @auth.login_required
    @requires_admin
    def put(self, message_id):
        message = Message.query.filter_by(id=message_id).first()
        if not message:
            abort(404)

        form = MessageForm()
        if not form.validate_on_submit():
            logging.warning("validation error on update message")
            return form.errors, 422

        message.subject = form.subject.data
        message.message = form.message.data
        message.broadcasted = datetime.datetime.utcnow()

        db.session.commit()

        return None

    @auth.login_required
    @requires_admin
    def delete(self, message_id):
        message = Message.query.filter_by(id=message_id).first()
        if not message:
            abort(404)
        db.session.delete(message)
        db.session.commit()
