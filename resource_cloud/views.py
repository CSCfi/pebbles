from wsgi import api, db, restful, app
from flask.ext.restful import fields, marshal_with

from models import User
from forms import UserCreateForm


@app.route("/api/debug")
def debug():
    return "%s" % app.config['SQLALCHEMY_DATABASE_URI']

user_fields = {
    'email': fields.String,
}


class UserView(restful.Resource):
    @marshal_with(user_fields)
    def post(self):
        form = UserCreateForm()
        if not form.validate_on_submit():
            return form.errors, 422

        user = User(form.email.data, form.password.data)
        db.session.add(user)
        db.session.commit()
        return user

    @marshal_with(user_fields)
    def get(self):
        return User.query.all()




api.add_resource(UserView, '/api/v1/users')
