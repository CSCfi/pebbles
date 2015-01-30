from flask.ext.wtf import Form
from wtforms_alchemy import model_form_factory
from wtforms import StringField
from wtforms.validators import DataRequired

from resource_cloud.models import User
from resource_cloud.server import db

BaseModelForm = model_form_factory(Form)


class ModelForm(BaseModelForm):
    @classmethod
    def get_session(self):
        return db.session


class UserForm(ModelForm):
    class Meta:
        model = User


class SessionCreateForm(ModelForm):
    email = StringField('email', validators=[DataRequired()])
    password = StringField('password', validators=[DataRequired()])


class ActivationForm(ModelForm):
    token = StringField('token', validators=[DataRequired()])
    password = StringField('password', validators=[DataRequired()])
