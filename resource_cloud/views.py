from flask import abort, g
from flask.ext.restful import fields, marshal_with
import logging

from models import User, ActivationToken
from forms import UserForm, SessionCreateForm, ActivationForm

from wsgi import api, auth, db, restful, app
from resource_cloud.tasks import run_provisioning


@app.route("/api/debug")
def debug():
    return "%s" % app.config['SQLALCHEMY_DATABASE_URI']


@auth.verify_password
def verify_password(userid_or_token, password):
    g.user = User.verify_auth_token(userid_or_token)
    if not g.user:
        g.user = User.query.filter_by(email=userid_or_token).first()
        if not g.user or not g.user.check_password(password):
            return False
    return True


user_fields = {
    'id': fields.String,
    'email': fields.String,
    'is_active': fields.Boolean,
    'is_admin': fields.Boolean,
}

token_fields = {
    'token': fields.String,
    'is_admin': fields.Boolean,
}


class FirstUserView(restful.Resource):
    @marshal_with(user_fields)
    def post(self):
        users = User.query.all()
        form = UserForm()

        if not form.validate_on_submit():
            logging.warn("%s" % form.errors)
            return form.errors, 422

        if not users:
            user = User(form.email.data, form.password.data, is_admin=True)
            db.session.add(user)
            db.session.commit()
        else:
            return abort(403)


class UserList(restful.Resource):
    @auth.login_required
    @marshal_with(user_fields)
    def post(self):
        form = UserForm()
        if not form.validate_on_submit():
            logging.warn("%s" % form.errors)
            return form.errors, 422
        new_user = User(form.email.data, form.password.data, form.is_admin.data)
        db.session.add(new_user)
        token = ActivationToken(new_user)
        db.session.add(token)
        db.session.commit()
        return new_user

    @auth.login_required
    @marshal_with(user_fields)
    def get(self):
        user = User.verify_auth_token(auth.username())
        if not user.is_admin:
            return abort(401)
        return User.query.all()


class UserView(restful.Resource):
    @auth.login_required
    @marshal_with(user_fields)
    def get(self, user_id):
        return User.query.filter_by(id=user_id)

    @auth.login_required
    def delete(self, user_id):
        user = User.query.filter_by(id=user_id).first()
        if not user:
            return abort(404)
        db.session.delete(user)
        db.session.commit()


class SessionView(restful.Resource):
    @marshal_with(token_fields)
    def post(self):
        form = SessionCreateForm()
        if not form.validate_on_submit():
            return form.errors, 422

        user = User.query.filter_by(email=form.email.data).first()
        if user and user.check_password(form.password.data):
            return {'token': user.generate_auth_token(),
                    'is_admin': user.is_admin}
        return abort(401)


class ActivationView(restful.Resource):
    @marshal_with(user_fields)
    def post(self):
        form = ActivationForm()
        if not form.validate_on_submit():
            return form.errors, 422

        token = ActivationToken.query.filter_by(token=form.token.data).first()
        if not token:
            return abort(404)

        user = User.query.filter_by(id=token.user_id).first()
        if not user:
            return abort(410)
        user.set_password(form.password.data)
        user.is_active = True

        db.session.delete(token)
        db.session.commit()

        return user


class ServiceView(restful.Resource):
    @auth.login_required
    def get(self):
        return [{'name': 'Standard cluster', 'vcpus': 4, 'max_life_time': 18000}]

    def post(self):
        user = User.verify_auth_token(auth.username())
        run_provisioning.delay()
        return ['%s' % user]

api.add_resource(FirstUserView, '/api/v1/initizlie')
api.add_resource(UserList, '/api/v1/users')
api.add_resource(UserView, '/api/v1/users/<string:user_id>')
api.add_resource(SessionView, '/api/v1/sessions')
api.add_resource(ActivationView, '/api/v1/activations<string:activation_id>')
api.add_resource(ServiceView, '/api/v1/services')
