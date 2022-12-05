import logging

import flask_restful as restful
from flask import Blueprint as FlaskBlueprint
from flask import abort
from flask_restful import reqparse, fields, marshal_with

from pebbles.forms import ServiceAnnouncementForm
from pebbles.models import db, ServiceAnnouncement
from pebbles.utils import requires_admin
from pebbles.views.commons import auth

service_announcements = FlaskBlueprint('service_announcements', __name__)

SERVICE_ANNOUNCEMENT_FIELDS = {
    'id': fields.String,
    'subject': fields.String,
    'content': fields.String,
    'level': fields.Integer,
    'targets': fields.String,
    'is_enabled': fields.Boolean,
    'is_public': fields.Boolean,
    'created_at': fields.String
}


class ServiceAnnouncementList(restful.Resource):
    parser = reqparse.RequestParser()

    @marshal_with(SERVICE_ANNOUNCEMENT_FIELDS)
    def get(self):
        query = ServiceAnnouncement.query
        query = query.filter(ServiceAnnouncement.is_enabled, ServiceAnnouncement.is_public)
        announcements = query.all()
        return announcements

    @auth.login_required
    @requires_admin
    @marshal_with(SERVICE_ANNOUNCEMENT_FIELDS)
    def post(self):
        form = ServiceAnnouncementForm()
        if not form.validate_on_submit():
            logging.warning("validation error on post new service_announcement")
            return form.errors, 422

        announcement = ServiceAnnouncement(form.subject.data, form.content.data, form.level.data,
                                           form.targets.data, form.is_enabled.data, form.is_public.data)

        db.session.add(announcement)
        db.session.commit()

        return announcement


class ServiceAnnouncementView(restful.Resource):

    @auth.login_required
    @requires_admin
    @marshal_with(SERVICE_ANNOUNCEMENT_FIELDS)
    def put(self, service_announcement_id):
        announcement = ServiceAnnouncement.query.filter_by(id=service_announcement_id).first()
        if not announcement:
            abort(404)

        form = ServiceAnnouncementForm()
        if not form.validate_on_submit():
            logging.warning("validation error on update service_announcement")
            return form.errors, 422

        announcement.subject = form.subject.data
        announcement.content = form.content.data
        announcement.level = form.level.data
        announcement.targets = form.targets.data
        announcement.is_enabled = form.is_enabled.data
        announcement.is_public = form.is_public.data

        db.session.commit()

        return announcement

    @auth.login_required
    @requires_admin
    def delete(self, service_announcement_id):
        announcement = ServiceAnnouncement.query.filter_by(id=service_announcement_id).first()
        if not announcement:
            abort(404)
        db.session.delete(announcement)
        db.session.commit()
