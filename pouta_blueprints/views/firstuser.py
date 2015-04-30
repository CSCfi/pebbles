from flask.ext.restful import marshal_with
from flask import abort
from flask import Blueprint as FlaskBlueprint

import logging

from pouta_blueprints.models import User, create_worker, create_user
from pouta_blueprints.forms import UserForm
from pouta_blueprints.server import restful
from pouta_blueprints.views.commons import user_fields

firstuser = FlaskBlueprint('firstuser', __name__)


@firstuser.route('/')
class FirstUserView(restful.Resource):
    @marshal_with(user_fields)
    def post(self):
        users = User.query.all()
        form = UserForm()

        if not users:
            if not form.validate_on_submit():
                logging.warn("validation error on first user creation")
                return form.errors, 422
            user = create_user(form.email.data, form.password.data, is_admin=True)
            create_worker()
            return user
        else:
            return abort(403)
