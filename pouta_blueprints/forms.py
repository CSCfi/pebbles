from flask.ext.wtf import Form
from wtforms_alchemy import model_form_factory
from wtforms import BooleanField, StringField
from wtforms.validators import DataRequired, Email, Length, IPAddress

from pouta_blueprints.models import (
    MAX_EMAIL_LENGTH, MAX_NAME_LENGTH, MAX_PASSWORD_LENGTH,
    MAX_VARIABLE_KEY_LENGTH, MAX_VARIABLE_VALUE_LENGTH
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


class BlueprintForm(ModelForm):
    name = StringField('name', validators=[DataRequired(), Length(max=MAX_NAME_LENGTH)])
    config = StringField('config', validators=[DataRequired()])
    plugin = StringField('plugin', validators=[DataRequired()])
    is_enabled = BooleanField('is_enabled', default=False)


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
