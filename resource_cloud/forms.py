from flask.ext.wtf import Form
from wtforms_alchemy import model_form_factory
from wtforms import BooleanField, StringField
from wtforms.validators import DataRequired, Email, Length

from resource_cloud.models import MAX_PASSWORD_LENGTH
from resource_cloud.server import db

BaseModelForm = model_form_factory(Form)


class ModelForm(BaseModelForm):
    @classmethod
    def get_session(self):
        return db.session


class UserForm(ModelForm):
    email = StringField('email', validators=[DataRequired(), Email()])
    password = StringField('password', default=None)
    is_admin = BooleanField('is_admin', default=False)


class UpdateResourceConfigForm(ModelForm):
    config = StringField('config', validators=[DataRequired()])


class ChangePasswordForm(ModelForm):
    password = StringField('password', validators=[DataRequired(), Length(
        min=8,
        max=MAX_PASSWORD_LENGTH, message=("Password must be between %(min)d and "
                                          "%(max)d characters long"))])


class ProvisionedResourceForm(ModelForm):
    resource = StringField('resource_id', validators=[DataRequired()])


class SessionCreateForm(ModelForm):
    email = StringField('email', validators=[DataRequired()])
    password = StringField('password', validators=[DataRequired()])


class ActivationForm(ModelForm):
    token = StringField('token', validators=[DataRequired()])
    password = StringField('password', validators=[DataRequired(), Length(
        min=8,
        max=MAX_PASSWORD_LENGTH, message=("Password must be between %(min)d and "
                                          "%(max)d characters long"))])
