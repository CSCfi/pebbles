""" Forms are made with WTForms, which is mostly acceptable but has started to
cause gray hair.
"""
from flask_wtf import FlaskForm
from wtforms import BooleanField, StringField, IntegerField
from wtforms.validators import DataRequired, Email, Length, AnyOf

from pebbles.models import (
    MAX_EMAIL_LENGTH, MAX_NAME_LENGTH,
    MAX_MESSAGE_SUBJECT_LENGTH
)


class UserForm(FlaskForm):
    ext_id = StringField('ext_id', validators=[DataRequired(), Email(), Length(max=MAX_EMAIL_LENGTH)])
    email_id = StringField('email_id', validators=[Email(), Length(max=MAX_EMAIL_LENGTH)])
    password = StringField('password', default=None)
    is_admin = BooleanField('is_admin', default=False, false_values=['false', False, ''])


WS_TYPE_FIXED_TIME = 'fixed-time-course'
WS_TYPE_LONG_RUNNING = 'long-running-course'
VALID_WS_TYPES = [WS_TYPE_FIXED_TIME, WS_TYPE_LONG_RUNNING]


class WorkspaceForm(FlaskForm):
    name = StringField('name')
    description = StringField('description')
    expiry_ts = IntegerField()
    workspace_type = StringField(
        name='workspace_type',
        validators=[AnyOf(VALID_WS_TYPES + [None, ], message='Unknown workspace_type')],
    )
    contact = StringField('contact')


class MessageForm(FlaskForm):
    subject = StringField('subject', validators=[DataRequired(), Length(max=MAX_MESSAGE_SUBJECT_LENGTH)])
    message = StringField('message', validators=[DataRequired()])


class ServiceAnnouncementForm(FlaskForm):
    subject = StringField('subject', validators=[DataRequired()])
    content = StringField('content', validators=[DataRequired()])
    level = IntegerField('level', default=1)
    targets = StringField('targets', validators=[DataRequired()])
    is_enabled = BooleanField('is_enabled', default=False)
    is_public = BooleanField('is_public', default=False)


class ApplicationTemplateForm(FlaskForm):
    name = StringField('name', validators=[DataRequired(), Length(max=MAX_NAME_LENGTH)])
    base_config = StringField('base_config', validators=[DataRequired()])
    attribute_limits = StringField('attribute_limits')
    is_enabled = BooleanField('is_enabled', default=False)


class ApplicationForm(FlaskForm):
    name = StringField('name', validators=[DataRequired(), Length(max=MAX_NAME_LENGTH)])
    description = StringField('description')
    template_id = StringField('template_id', validators=[DataRequired()])
    labels = StringField('labels', validators=[Length(max=1024)])
    maximum_lifetime = IntegerField('maximum_lifetime')
    config = StringField('config')
    is_enabled = BooleanField('is_enabled', default=False)
    workspace_id = StringField('workspace_id', validators=[DataRequired()])


class ApplicationSessionForm(FlaskForm):
    application_id = StringField('application_id', validators=[DataRequired()])


class SessionCreateForm(FlaskForm):
    ext_id = StringField('ext_id', validators=[DataRequired()])
    password = StringField('password', validators=[DataRequired()])


class LockForm(FlaskForm):
    owner = StringField('owner')


class CustomImageForm(FlaskForm):
    name = StringField('name', validators=[DataRequired()])
    workspace_id = StringField('workspace_id', validators=[DataRequired()])
    definition = StringField('image_content', validators=[DataRequired()])
