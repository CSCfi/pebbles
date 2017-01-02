from flask.ext.restful import marshal_with
from flask import abort
from flask import Blueprint as FlaskBlueprint

import logging

from pebbles.models import User
from pebbles.forms import UserForm
from pebbles.server import restful
from pebbles.views.commons import user_fields, create_user, create_worker, create_system_groups

firstuser = FlaskBlueprint('firstuser', __name__)


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
            logging.warn("creating system group")
            create_system_groups(user)
            return user
        else:
            return abort(403)
