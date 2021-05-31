""" Forms are made with WTForms, which is mostly acceptable but has started to
cause gray hair.
"""
import re

from flask_wtf import Form
from wtforms import BooleanField, FloatField, StringField, IntegerField
from wtforms.validators import DataRequired, Email, Length, IPAddress, Regexp
from wtforms_alchemy import model_form_factory

from pebbles.models import (
    MAX_EMAIL_LENGTH, MAX_NAME_LENGTH,
    MAX_VARIABLE_KEY_LENGTH, MAX_VARIABLE_VALUE_LENGTH,
    MAX_MESSAGE_SUBJECT_LENGTH
)
from pebbles.models import db

BaseModelForm = model_form_factory(Form)


class ModelForm(BaseModelForm):
    @classmethod
    def get_session(cls):
        return db.session


class UserForm(ModelForm):
    ext_id = StringField('ext_id', validators=[DataRequired(), Email(), Length(max=MAX_EMAIL_LENGTH)])
    email_id = StringField('email_id', validators=[Email(), Length(max=MAX_EMAIL_LENGTH)])
    password = StringField('password', default=None)
    is_admin = BooleanField('is_admin', default=False, false_values=['false', False, ''])


class WorkspaceForm(ModelForm):
    name = StringField(
        'name',
        validators=[
            DataRequired(),
            Regexp('^(?!System).+', re.IGNORECASE, message='name cannot start with System')
        ]
    )
    description = StringField('description')
    user_config = StringField('user_config')


class MessageForm(ModelForm):
    subject = StringField('subject', validators=[DataRequired(), Length(max=MAX_MESSAGE_SUBJECT_LENGTH)])
    message = StringField('message', validators=[DataRequired()])


class EnvironmentTemplateForm(ModelForm):
    name = StringField('name', validators=[DataRequired(), Length(max=MAX_NAME_LENGTH)])
    base_config = StringField('base_config')
    cluster = StringField('cluster', validators=[DataRequired()])
    allowed_attrs = StringField('allowed_attrs')
    is_enabled = BooleanField('is_enabled', default=False)


class EnvironmentForm(ModelForm):
    name = StringField('name', validators=[DataRequired(), Length(max=MAX_NAME_LENGTH)])
    description = StringField('description')
    template_id = StringField('template_id', validators=[DataRequired()])
    labels = StringField('labels', validators=[Length(max=1024)])
    maximum_lifetime = IntegerField('maximum_lifetime', validators=[DataRequired()])
    config = StringField('config')
    is_enabled = BooleanField('is_enabled', default=False)
    workspace_id = StringField('workspace_id', validators=[DataRequired()])


class EnvironmentTemplateImportForm(ModelForm):
    name = StringField('name', validators=[DataRequired()])
    config = StringField('config', validators=[DataRequired()])
    cluster_name = StringField('cluster_name', validators=[DataRequired()])
    allowed_attrs = StringField('allowed_attrs')


class EnvironmentImportForm(ModelForm):
    name = StringField('name', validators=[DataRequired()])
    config = StringField('config', validators=[DataRequired()])
    template_name = StringField('template_name', validators=[DataRequired()])
    workspace_name = StringField('workspace_name', validators=[DataRequired()])


class InstanceForm(ModelForm):
    environment = StringField('environment_id', validators=[DataRequired()])


class SessionCreateForm(ModelForm):
    ext_id = StringField('ext_id', validators=[DataRequired()])
    password = StringField('password', validators=[DataRequired()])


class UserIPForm(ModelForm):
    client_ip = StringField('client_ip', validators=[IPAddress(ipv6=True)])


class VariableForm(ModelForm):
    key = StringField(
        'key', validators=[DataRequired(), Length(max=MAX_VARIABLE_KEY_LENGTH)])
    value = StringField(
        'value', validators=[Length(max=MAX_VARIABLE_VALUE_LENGTH)])


class NamespacedKeyValueForm(ModelForm):
    namespace = StringField('namespace', validators=[DataRequired()])
    key = StringField('key', validators=[DataRequired()])
    value = StringField('value', validators=[DataRequired()])
    schema = StringField('schema')
    updated_version_ts = FloatField('updated_version_ts')


class LockForm(ModelForm):
    owner = StringField('owner')
