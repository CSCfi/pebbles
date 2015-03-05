from flask.ext.wtf import Form
from wtforms_alchemy import model_form_factory
from wtforms import BooleanField, StringField
from wtforms.validators import DataRequired, Email, Length

from resource_cloud.models import MAX_EMAIL_LENGTH, MAX_NAME_LENGTH, MAX_PASSWORD_LENGTH
from resource_cloud.server import db

BaseModelForm = model_form_factory(Form)


class ModelForm(BaseModelForm):
    @classmethod
    def get_session(cls):
        return db.session


class UserForm(ModelForm):
    email = StringField('email', validators=[DataRequired(), Email(), Length(max=MAX_EMAIL_LENGTH)])
    password = StringField('password', default=None)
    is_admin = BooleanField('is_admin', default=False)


class ResourceForm(ModelForm):
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
    resource = StringField('blueprint_id', validators=[DataRequired()])


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
