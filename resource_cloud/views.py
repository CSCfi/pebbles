from flask import abort, g
from flask.ext.restful import fields, marshal_with, reqparse
import logging
import names
from functools import wraps

from resource_cloud.models import User, ActivationToken, Resource
from resource_cloud.models import ProvisionedResource, SystemToken, Keypair
from resource_cloud.forms import UserForm, SessionCreateForm, ActivationForm

from resource_cloud.server import api, auth, db, restful, app
from resource_cloud.tasks import run_provisioning, run_deprovisioning
from resource_cloud.tasks import send_mails

from resource_cloud.utils import generate_ssh_keypair

USER_RESOURCE_LIMIT = 5


@app.route("/api/debug")
def debug():
    return "%s" % app.config['SQLALCHEMY_DATABASE_URI']


def requires_admin(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not g.user.is_admin:
            abort(403)
        return f(*args, **kwargs)
    return decorated


@auth.verify_password
def verify_password(userid_or_token, password):
    # first check for system tokens
    if SystemToken.verify(userid_or_token):
        g.user = User('system', is_admin=True)
        return True

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
    @requires_admin
    @marshal_with(user_fields)
    def post(self):
        form = UserForm()
        if not form.validate_on_submit():
            logging.warn("validation error on user add: %s" % form.errors)
            abort(422)
        new_user = User(form.email.data, form.password.data,
                        form.is_admin.data)
        db.session.add(new_user)
        db.session.commit()

        token = ActivationToken(new_user)
        db.session.add(token)
        db.session.commit()

        send_mails.delay([(new_user.email, token.token)])
        return new_user

    @auth.login_required
    @marshal_with(user_fields)
    def get(self):
        if g.user.is_admin:
            return User.query.all()
        return [g.user]


class UserView(restful.Resource):
    @auth.login_required
    @marshal_with(user_fields)
    def get(self, user_id):
        if not g.user.is_admin and user_id != g.user.visual_id:
            abort(403)
        return User.query.filter_by(visual_id=user_id).first()

    @auth.login_required
    @requires_admin
    def delete(self, user_id):
        if not g.user.is_admin:
            abort(403)
        user = User.query.filter_by(visual_id=user_id).first()
        if not user:
            logging.warn("trying to delete non-existing user")
            abort(404)
        db.session.delete(user)
        db.session.commit()


public_key_fields = {
    'id': fields.String(attribute='visual_id'),
    'name': fields.String,
    'public_key': fields.String
}

private_key_fields = {
    'private_key': fields.String
}


class KeypairList(restful.Resource):
    @auth.login_required
    @marshal_with(public_key_fields)
    def get(self, user_id):
        if g.user.is_admin:
            return Keypair.query.all()

        elif user_id != g.user.visual_id:
            abort(403)

        return Keypair.query.filter_by(user_id=g.user.id)

    @auth.login_required
    @marshal_with(private_key_fields)
    def post(self, user_id):
        if user_id != g.user.visual_id:
            abort(403)
        priv, pub = generate_ssh_keypair()
        key = Keypair()
        key.user_id = g.user.id
        key.public_key = pub
        db.session.add(key)
        db.session.commit()
        return {'private_key': priv}


class KeypairView(restful.Resource):
    @auth.login_required
    @marshal_with(public_key_fields)
    def get(self, user_id, keypair_id):
        pass

    @auth.login_required
    def delete(self, user_id, keypair_id):
        pass

token_fields = {
    'token': fields.String,
    'is_admin': fields.Boolean,
}


class SessionView(restful.Resource):
    @marshal_with(token_fields)
    def post(self):
        form = SessionCreateForm()
        if not form.validate_on_submit():
            logging.warn("validation error on user login")
            return form.errors, 422

        user = User.query.filter_by(email=form.email.data).first()
        if user and user.check_password(form.password.data):
            return {'token': user.generate_auth_token(),
                    'is_admin': user.is_admin}
        logging.warn("invalid login credentials for %s" % form.email.data)
        return abort(401)


class ActivationList(restful.Resource):
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
    'name': fields.String,
    'provisioned_at': fields.DateTime,
    'state': fields.String,
}


class ProvisionedResourceList(restful.Resource):
    @auth.login_required
    @marshal_with(provision_fields)
    def get(self):
        user = g.user
        if user.is_admin:
            return ProvisionedResource.query. \
                filter(ProvisionedResource.state != 'deleted').all()
        return ProvisionedResource.query.filter_by(user_id=user.id). \
            filter((ProvisionedResource.state != 'deleted')).all()


class ProvisionedResourceView(restful.Resource):
    parser = reqparse.RequestParser()
    parser.add_argument('state', type=str)

    @auth.login_required
    @marshal_with(provision_fields)
    def get(self, provision_id):
        user = g.user
        resource = ProvisionedResource.query.filter_by(visual_id=provision_id)
        if not user.is_admin:
            resource = resource.filter_by(user_id=user.id)
        resource = resource.first()
        if not resource:
            abort(404)
        return resource

    @auth.login_required
    def delete(self, provision_id):
        user = g.user
        pr = ProvisionedResource.query.filter_by(visual_id=provision_id). \
            filter_by(user_id=user.id).first()
        if not pr:
            abort(404)
        pr.state = 'deleting'
        token = SystemToken('provisioning')
        db.session.add(token)
        db.session.commit()
        run_deprovisioning.delay(token.token, pr.visual_id)

    @auth.login_required
    def patch(self, provision_id):
        user = g.user
        args = self.parser.parse_args()
        print('got args %s' % args)
        qr = ProvisionedResource.query.filter_by(visual_id=provision_id)
        if not user.is_admin:
            qr = qr.filter_by(user_id=user.id)
        pr = qr.first()
        if not pr:
            abort(404)

        # TODO: add a model for state transitions
        if args['state']:
            if args['state'] == 'deleting':
                if pr.state in ['starting', 'running']:
                    pr.state = args['state']
                    self.delete(provision_id)
            else:
                pr.state = args['state']

            db.session.commit()
        pass


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

    @auth.login_required
    def post(self, resource_id):
        user = g.user
        resources_for_user = ProvisionedResource.query.filter_by(resource_id=resource_id). \
            filter_by(user_id=user.id).filter(ProvisionedResource.state != 'deleted').all()
        if resources_for_user and len(resources_for_user) >= USER_RESOURCE_LIMIT:
            abort(409)

        provision = ProvisionedResource(resource_id, user.id)

        # decide on a name that is not used currently
        all_resources = ProvisionedResource.query.all()
        existing_names = [x.name for x in all_resources]
        # Note: the potential race is solved by unique constraint in database
        while True:
            c_name = names.get_first_name(gender='female').lower()
            if c_name not in existing_names:
                provision.name = c_name
                break
        token = SystemToken('provisioning')
        db.session.add(provision)
        db.session.add(token)
        db.session.commit()
        run_provisioning.delay(token.token, provision.visual_id)
        return ['%s' % user]


api.add_resource(FirstUserView, '/api/v1/initialize')
api.add_resource(UserList, '/api/v1/users')
api.add_resource(UserView, '/api/v1/users/<string:user_id>')
api.add_resource(KeypairList, '/api/v1/users/<string:user_id>/keypairs')
api.add_resource(KeypairView, '/api/v1/users/<string:user_id>/keypairs/<string:keypair_id>')
api.add_resource(SessionView, '/api/v1/sessions')
api.add_resource(ActivationList, '/api/v1/activations')
api.add_resource(ResourceList, '/api/v1/resources')
api.add_resource(ResourceView, '/api/v1/resources/<string:resource_id>')
api.add_resource(ProvisionedResourceList, '/api/v1/provisioned_resources')
api.add_resource(ProvisionedResourceView,
                 '/api/v1/provisioned_resources/<string:provision_id>',
                 methods=['GET', 'POST', 'DELETE', 'PATCH'])
