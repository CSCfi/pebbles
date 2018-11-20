""" Forms are made with WTForms, which is mostly acceptable but has started to
cause gray hair.


"""

from flask.ext.wtf import Form
from wtforms_alchemy import model_form_factory
from wtforms import BooleanField, FloatField, StringField
# from wtforms import FormField, FieldList
from wtforms.validators import DataRequired, Email, Length, IPAddress, Regexp

from pebbles.models import (
    MAX_EMAIL_LENGTH, MAX_NAME_LENGTH, MAX_PASSWORD_LENGTH,
    MAX_VARIABLE_KEY_LENGTH, MAX_VARIABLE_VALUE_LENGTH,
    MAX_NOTIFICATION_SUBJECT_LENGTH
)

from pebbles.models import db
import re

BaseModelForm = model_form_factory(Form)


class ModelForm(BaseModelForm):
    @classmethod
    def get_session(cls):
        return db.session


class UserForm(ModelForm):
    eppn = StringField('eppn', validators=[DataRequired(), Email(), Length(max=MAX_EMAIL_LENGTH)])
    password = StringField('password', default=None)
    is_admin = BooleanField('is_admin', default=False, false_values=['false', False, ''])


class GroupForm(ModelForm):
    name = StringField('name', validators=[DataRequired(), Regexp('^(?!System).+', re.IGNORECASE, message='name cannot start with System')])
    description = StringField('description')
    user_config = StringField('user_config')


class NotificationForm(ModelForm):
    subject = StringField('subject', validators=[DataRequired(), Length(max=MAX_NOTIFICATION_SUBJECT_LENGTH)])
    message = StringField('message', validators=[DataRequired()])


class BlueprintTemplateForm(ModelForm):
    name = StringField('name', validators=[DataRequired(), Length(max=MAX_NAME_LENGTH)])
    config = StringField('config', validators=[DataRequired()])
    plugin = StringField('plugin', validators=[DataRequired()])
    allowed_attrs = StringField('allowed_attrs')
    is_enabled = BooleanField('is_enabled', default=False)


class BlueprintForm(ModelForm):
    name = StringField('name', validators=[DataRequired(), Length(max=MAX_NAME_LENGTH)])
    template_id = StringField('template_id', validators=[DataRequired()])
    config = StringField('config', validators=[DataRequired()])
    is_enabled = BooleanField('is_enabled', default=False)
    group_id = StringField('group_id', validators=[DataRequired()])


class BlueprintTemplateImportForm(ModelForm):
    name = StringField('name', validators=[DataRequired()])
    config = StringField('config', validators=[DataRequired()])
    plugin_name = StringField('plugin_name', validators=[DataRequired()])
    allowed_attrs = StringField('allowed_attrs')


class BlueprintImportForm(ModelForm):
    name = StringField('name', validators=[DataRequired()])
    config = StringField('config', validators=[DataRequired()])
    template_name = StringField('template_name', validators=[DataRequired()])
    group_name = StringField('group_name', validators=[DataRequired()])

# class BlueprintImportForm(Form):
#    blueprints = FieldList(FormField(BlueprintImportFormField), min_entries=1)


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
    eppn = StringField('eppn', validators=[DataRequired()])
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


class NamespacedKeyValueForm(ModelForm):
    namespace = StringField('namespace', validators=[DataRequired()])
    key = StringField('key', validators=[DataRequired()])
    value = StringField('value', validators=[DataRequired()])
    schema = StringField('schema')
    updated_version_ts = FloatField('updated_version_ts')
