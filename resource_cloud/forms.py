from flask.ext.wtf import Form
from wtforms_alchemy import model_form_factory

from models import User
from wsgi import db

BaseModelForm = model_form_factory(Form)


class ModelForm(BaseModelForm):
    @classmethod
    def get_session(self):
        return db.session


class UserCreateForm(ModelForm):
    class Meta:
        model = User
