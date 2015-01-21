from flask import abort, g
from flask.ext.restful import fields, marshal_with
import logging

from models import User, ActivationToken, Resource, ProvisionedResource
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
    'id': fields.String(attribute='visual_id'),
    'email': fields.String,
    'is_active': fields.Boolean,
    'is_admin': fields.Boolean,
}


class FirstUserView(restful.Resource):
    @marshal_with(user_fields)
    def post(self):
        users = User.query.all()
        form = UserForm()

        if not users:
            if not form.validate_on_submit():
                logging.warn("%s" % form.errors)
                return form.errors, 422
            user = User(form.email.data, form.password.data, is_admin=True)
            user.is_active = True
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
        new_user = User(form.email.data, form.password.data,
                        form.is_admin.data)
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
        return User.query.filter_by(visual_id=user_id).first()

    @auth.login_required
    def delete(self, user_id):
        user = User.query.filter_by(visual_id=user_id).first()
        if not user:
            return abort(404)
        db.session.delete(user)
        db.session.commit()


token_fields = {
    'token': fields.String,
    'is_admin': fields.Boolean,
}


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

provision_fields = {
    'id': fields.String(attribute='visual_id'),
    'provisioned_at': fields.DateTime,
}


class ProvisionList(restful.Resource):
    @auth.login_required
    @marshal_with(provision_fields)
    def get(self):
        user = User.verify_auth_token(auth.username())
        if user.is_admin:
            return ProvisionedResource.query.all()
        return ProvisionedResource.query.filter_by(user_id=user.id)


class ProvisionView(restful.Resource):
    @auth.login_required
    @marshal_with(provision_fields)
    def get(self, provision_id):
        user = User.verify_auth_token(auth.username())
        resource = ProvisionedResource.query.filter_by(visual_id=provision_id). \
            filter_by(user_id=user.id).first()
        if not resource:
            abort(404)
        return resource

    @auth.login_required
    def delete(self, provision_id):
        user = User.verify_auth_token(auth.username())
        resource = ProvisionedResource.query.filter_by(visual_id=provision_id). \
            filter_by(user_id=user.id).first()
        if not resource:
            abort(404)
        # XXX: Send unprovisioning request to task queue
        db.session.delete(resource)
        db.session.commit()

resource_fields = {
    'id': fields.String(attribute='visual_id'),
    'vcpus': fields.String,
    'max_life_time': fields.String,
    'name': fields.String,
}


class ResourceList(restful.Resource):
    @auth.login_required
    @marshal_with(resource_fields)
    def get(self):
        return [{'visual_id': '9b8ccf23d37a4dd785e6674ff08b688b',
                 'vcpus': 4,
                 'max_life_time': 36000,
                 'name': 'dummy'}]
        # return Resource.query.all()


class ResourceView(restful.Resource):
    @auth.login_required
    @marshal_with(resource_fields)
    def get(self, resource_id):
        return Resource.query.filter_by(id=resource_id).first()

    def post(self, resource_id):
        user = User.verify_auth_token(auth.username())
        provision = ProvisionedResource.query.filter_by(resource_id=resource_id). \
            filter_by(user_id=user.id).first()
        if provision:
            abort(409)
        provision = ProvisionedResource(resource_id, user.id)
        db.session.add(provision)
        db.session.commit()
        run_provisioning.delay()
        return ['%s' % user]

api.add_resource(FirstUserView, '/api/v1/initialize')
api.add_resource(UserList, '/api/v1/users')
api.add_resource(UserView, '/api/v1/users/<string:user_id>')
api.add_resource(SessionView, '/api/v1/sessions')
api.add_resource(ActivationView, '/api/v1/activations/<string:activation_id>')
api.add_resource(ResourceList, '/api/v1/resources')
api.add_resource(ResourceView, '/api/v1/resources/<string:resource_id>')
