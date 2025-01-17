import logging
from datetime import timezone, datetime

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
    'message': fields.String,
    'is_read': fields.Boolean,
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
    parser.add_argument('show_unread', type=bool, default=False, location='args')

    @auth.login_required
    @marshal_with(MESSAGE_FIELDS)
    def get(self):
        args = self.parser.parse_args()
        user = get_current_user()
        query = Message.query
        if args.get('show_unread'):
            if user.latest_seen_message_ts:
                query = query.filter(Message.broadcasted > user.latest_seen_message_ts)

        messages = query.all()

        # mark messages read or unread
        for msg in messages:
            if not user.latest_seen_message_ts:
                msg.is_read = False
            elif msg.broadcasted > user.latest_seen_message_ts:
                msg.is_read = False
            else:
                msg.is_read = True

        return messages

    @auth.login_required
    @requires_admin
    def post(self):
        form = MessageForm()
        if not form.validate_on_submit():
            logging.warning("validation error on post new message")
            return form.errors, 422

        message = Message(form.subject.data, form.message.data)

        db.session.add(message)
        db.session.commit()

        return None


class MessageView(restful.Resource):
    @auth.login_required
    @requires_admin
    @marshal_with(MESSAGE_FIELDS)
    def get(self, message_id):
        message = Message.query.filter_by(id=message_id).first()
        if not message:
            abort(404)
        return message

    @auth.login_required
    @marshal_with(MESSAGE_FIELDS)
    def patch(self, message_id):
        message = Message.query.filter_by(id=message_id).first()
        current_user = get_current_user()
        if not message:
            abort(404)
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
        message.broadcasted = datetime.now(timezone.utc)

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
