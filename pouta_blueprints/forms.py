from flask.ext.wtf import Form
from wtforms_alchemy import model_form_factory
from wtforms import BooleanField, StringField, FormField, FieldList
from wtforms.validators import DataRequired, Email, Length, IPAddress

from pouta_blueprints.models import (
    MAX_EMAIL_LENGTH, MAX_NAME_LENGTH, MAX_PASSWORD_LENGTH,
    MAX_VARIABLE_KEY_LENGTH, MAX_VARIABLE_VALUE_LENGTH,
    MAX_NOTIFICATION_SUBJECT_LENGTH
)

from pouta_blueprints.models import db

BaseModelForm = model_form_factory(Form)


class ModelForm(BaseModelForm):
    @classmethod
    def get_session(cls):
        return db.session


class UserForm(ModelForm):
    email = StringField('email', validators=[DataRequired(), Email(), Length(max=MAX_EMAIL_LENGTH)])
    password = StringField('password', default=None)
    is_admin = BooleanField('is_admin', default=False, false_values=['false', False, ''])


class GroupForm(ModelForm):
    name = StringField('name', validators=[DataRequired()])
    join_code = StringField('join_code', validators=[DataRequired()])
    description = StringField('description', default=None)
    users = StringField('users', default=None)
    banned_users = StringField('banned_users', default=None)
    owners = StringField('owners', default=None)


class NotificationForm(ModelForm):
    subject = StringField('subject', validators=[DataRequired(), Length(max=MAX_NOTIFICATION_SUBJECT_LENGTH)])
    message = StringField('message', validators=[DataRequired()])


class BlueprintForm(ModelForm):
    name = StringField('name', validators=[DataRequired(), Length(max=MAX_NAME_LENGTH)])
    config = StringField('config', validators=[DataRequired()])
    plugin = StringField('plugin', validators=[DataRequired()])
    is_enabled = BooleanField('is_enabled', default=False)
    group_id = StringField('group_id', validators=[DataRequired()])


class BlueprintImportFormField(Form):
    name = StringField('name', validators=[DataRequired()])
    config = StringField('config', validators=[DataRequired()])
    plugin_name = StringField('plugin_name', validators=[DataRequired()])


class BlueprintImportForm(Form):
    blueprints = FieldList(FormField(BlueprintImportFormField), min_entries=1)


class ChangePasswordForm(ModelForm):
    password = StringField('password', validators=[DataRequired(), Length(
        min=8,
        max=MAX_PASSWORD_LENGTH, message=("Password must be between %(min)d and "
                                          "%(max)d characters long"))])


class PasswordResetRequestForm(ModelForm):
    email = StringField('email', validators=[DataRequired(), Email(), Length(max=MAX_EMAIL_LENGTH)])


class InstanceForm(ModelForm):
    blueprint = StringField('blueprint_id', validators=[DataRequired()])


class SessionCreateForm(ModelForm):
    email = StringField('email', validators=[DataRequired()])
    password = StringField('password', validators=[DataRequired()])


class ActivationForm(ModelForm):
    password = StringField('password', validators=[DataRequired(), Length(
        min=8,
        max=MAX_PASSWORD_LENGTH, message=("Password must be between %(min)d and "
                                          "%(max)d characters long"))])


class PluginForm(ModelForm):
    plugin = StringField('plugin', validators=[DataRequired()])
    schema = StringField('schema', validators=[DataRequired()])
    form = StringField('form', validators=[DataRequired()])
    model = StringField('model', validators=[DataRequired()])


class UserIPForm(ModelForm):
    client_ip = StringField('client_ip', validators=[IPAddress(ipv6=True)])


class VariableForm(ModelForm):
    key = StringField(
        'key', validators=[DataRequired(), Length(max=MAX_VARIABLE_KEY_LENGTH)])
    value = StringField(
        'value', validators=[Length(max=MAX_VARIABLE_VALUE_LENGTH)])
