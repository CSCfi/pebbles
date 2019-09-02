import logging

from flask import Blueprint as FlaskBlueprint
from flask import abort
from flask_restful import marshal_with

from pebbles.forms import UserForm
from pebbles.models import User
from pebbles.server import restful
from pebbles.views.commons import user_fields, create_user, create_worker, create_system_groups, register_plugins

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
            # create admin account
            user = create_user(form.eppn.data, form.password.data, is_admin=True, email_id=form.email_id.data)
            # create an account for workers
            create_worker()
            logging.warning("creating system group")
            # initialize hard coded basic groups
            create_system_groups(user)
            # initialize plugins
            register_plugins()

            return user
        else:
            return abort(403)
