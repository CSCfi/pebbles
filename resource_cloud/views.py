import uuid
import os
from flask import abort, g, request
from flask.ext.restful import fields, marshal_with, reqparse
from sqlalchemy import desc
import logging
import names
import re
import werkzeug
import datetime
from functools import wraps

from resource_cloud.models import User, ActivationToken, Resource, Plugin
from resource_cloud.models import ProvisionedResource, SystemToken, Keypair
from resource_cloud.forms import UserForm, SessionCreateForm, ActivationForm
from resource_cloud.forms import ChangePasswordForm, ResourceForm
from resource_cloud.forms import PluginForm, ProvisionedResourceForm

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
                logging.warn("validation error on first user creation")
                return form.errors, 422
            user = User(form.email.data, form.password.data, is_admin=True)
            user.is_active = True
            worker = User('worker@resource_cloud', app.config['SECRET_KEY'], is_admin=True)
            worker.is_active = True
            db.session.add(user)
            db.session.add(worker)
            db.session.commit()
            return user
        else:
            return abort(403)


class UserList(restful.Resource):
    @staticmethod
    def address_list(value):
        return set(x for x in re.split(r",| |\n|\t", value) if x and '@' in x)

    parser = reqparse.RequestParser()
    parser.add_argument('addresses', type=address_list)

    @staticmethod
    def add_user(email, password=None, is_admin=False):
        user = User(email, password, is_admin)
        db.session.add(user)
        db.session.commit()

        token = ActivationToken(user)
        db.session.add(token)
        db.session.commit()

        send_mails.delay([(user.email, token.token)])

        return user

    @auth.login_required
    @requires_admin
    @marshal_with(user_fields)
    def post(self):
        form = UserForm()
        if not form.validate_on_submit():
            logging.warn("validation error on user add: %s" % form.errors)
            abort(422)
        user = self.add_user(form.email.data, form.password.data, form.is_admin.data)
        return user

    @auth.login_required
    @marshal_with(user_fields)
    def get(self):
        if g.user.is_admin:
            return User.query.all()
        return [g.user]

    @auth.login_required
    @requires_admin
    @marshal_with(user_fields)
    def patch(self):
        try:
            args = self.parser.parse_args()
        except:
            abort(422)
            return
        addresses = args.addresses
        for address in addresses:
            self.add_user(address)
        return User.query.all()


class UserView(restful.Resource):
    @auth.login_required
    @marshal_with(user_fields)
    def get(self, user_id):
        if not g.user.is_admin and user_id != g.user.visual_id:
            abort(403)
        return User.query.filter_by(visual_id=user_id).first()

    @auth.login_required
    def put(self, user_id):
        if not g.user.is_admin and user_id != g.user.visual_id:
            abort(403)
        form = ChangePasswordForm()
        if not form.validate_on_submit():
            logging.warn("validation error on change password: %s" % form.errors)
            return form.errors, 422
        g.user.set_password(form.password.data)
        db.session.add(g.user)
        db.session.commit()

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
    'public_key': fields.String
}


class KeypairList(restful.Resource):
    @auth.login_required
    @marshal_with(public_key_fields)
    def get(self, user_id):
        if not g.user.is_admin and user_id != g.user.visual_id:
            abort(403)

        user = g.user
        if user_id != g.user.visual_id:
            user = User.query.filter_by(visual_id=user_id).first()

        return Keypair.query.filter_by(user_id=user.id).order_by(desc("id")).all()


class KeypairView(restful.Resource):
    @auth.login_required
    @marshal_with(public_key_fields)
    def get(self, user_id, keypair_id):
        pass

    @auth.login_required
    def delete(self, user_id, keypair_id):
        pass


private_key_fields = {
    'private_key': fields.String
}


class CreateKeyPair(restful.Resource):
    @auth.login_required
    @marshal_with(private_key_fields)
    def post(self, user_id):
        if user_id != g.user.visual_id:
            abort(403)
        priv, pub = generate_ssh_keypair()

        for keypair in Keypair.query.filter_by(user_id=g.user.id).all():
            db.session.delete(keypair)
        db.session.commit()

        key = Keypair()
        key.user_id = g.user.id
        key.public_key = pub
        db.session.add(key)
        db.session.commit()

        return {'private_key': priv}


class UploadKeyPair(restful.Resource):
    @auth.login_required
    def post(self, user_id):
        parser = reqparse.RequestParser()
        parser.add_argument('file', type=werkzeug.datastructures.FileStorage, location='files')

        if user_id != g.user.visual_id:
            abort(403)
        args = parser.parse_args()
        if 'file' not in args:
            abort(422)

        existing_key = None
        for keypair in Keypair.query.filter_by(user_id=g.user.id).all():
            existing_key = keypair.public_key
            db.session.delete(keypair)
        db.session.commit()

        key = Keypair()
        key.user_id = g.user.id
        try:
            uploaded_key = args['file'].read()
            key.public_key = uploaded_key
            db.session.add(key)
            db.session.commit()
        except:
            key.public_key = existing_key
            db.session.add(key)
            db.session.commit()
            abort(422)


token_fields = {
    'token': fields.String,
    'user_id': fields.String,
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
                    'is_admin': user.is_admin,
                    'user_id': user.visual_id}
        logging.warn("invalid login credentials for %s" % form.email.data)
        return abort(401)


class ActivationList(restful.Resource):
    @staticmethod
    def post():
        form = ActivationForm()
        if not form.validate_on_submit():
            return form.errors, 422

        token = ActivationToken.query.filter_by(token=form.token.data).first()
        if not token:
            return abort(410)

        user = User.query.filter_by(id=token.user_id).first()
        if not user:
            return abort(410)

        user.set_password(form.password.data)
        user.is_active = True

        db.session.delete(token)
        db.session.commit()


provision_fields = {
    'id': fields.String(attribute='visual_id'),
    'name': fields.String,
    'provisioned_at': fields.DateTime,
    'lifetime_left': fields.Integer,
    'state': fields.String,
    'user_id': fields.String,
    'resource_id': fields.String,
    'public_ip': fields.String,
}


class ProvisionedResourceList(restful.Resource):
    @auth.login_required
    @marshal_with(provision_fields)
    def get(self):
        user = g.user
        if user.is_admin:
            provisions = ProvisionedResource.query. \
                filter(ProvisionedResource.state != 'deleted').all()
        else:
            provisions = ProvisionedResource.query.filter_by(user_id=user.id). \
                filter((ProvisionedResource.state != 'deleted')).all()

        for provision in provisions:
            if user.is_admin:
                res_owner = User.query.filter_by(id=provision.user_id).first()
                provision.user_id = res_owner.visual_id
            else:
                provision.user_id = user.visual_id

            res_parent = Resource.query.filter_by(id=provision.resource_id).first()

            if not res_parent:
                logging.warn("provisioned resource %s has a reference to "
                             "non-existing resource" % provision.visual_id)
                continue

            provision.resource_id = res_parent.visual_id
            age = 0
            if provision.provisioned_at:
                age = (datetime.datetime.utcnow() - provision.provisioned_at).total_seconds()
            provision.lifetime_left = max(res_parent.max_lifetime - age, 0)

        return provisions

    @auth.login_required
    def post(self):
        user = g.user

        form = ProvisionedResourceForm()
        if not form.validate_on_submit():
            logging.warn("validation error on user login")
            return form.errors, 422

        resource_id = form.resource.data

        resource = Resource.query.filter_by(visual_id=resource_id).first()
        if not resource:
            abort(404)

        resources_for_user = ProvisionedResource.query.filter_by(resource_id=resource_id). \
            filter_by(user_id=user.id).filter(ProvisionedResource.state != 'deleted').all()
        if resources_for_user and len(resources_for_user) >= USER_RESOURCE_LIMIT:
            abort(409)

        provision = ProvisionedResource(resource.id, user.id)

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


class ProvisionedResourceView(restful.Resource):
    parser = reqparse.RequestParser()
    parser.add_argument('state', type=str)
    parser.add_argument('public_ip', type=str)

    @auth.login_required
    @marshal_with(provision_fields)
    def get(self, provision_id):
        user = g.user
        provision = ProvisionedResource.query.filter_by(visual_id=provision_id)
        if not user.is_admin:
            provision = provision.filter_by(user_id=user.id)
        provision = provision.first()
        if not provision:
            abort(404)

        if user.is_admin:
            res_owner = User.query.filter_by(id=provision.user_id).first()
            provision.user_id = res_owner.visual_id
        else:
            provision.user_id = user.visual_id

        res_parent = Resource.query.filter_by(id=provision.resource_id).first()
        provision.resource_id = res_parent.visual_id

        return provision

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
        qr = ProvisionedResource.query.filter_by(visual_id=provision_id)
        if not user.is_admin:
            qr = qr.filter_by(user_id=user.id)
        pr = qr.first()
        if not pr:
            abort(404)

        # TODO: add a model for state transitions
        if args['state']:
            if args['state'] == 'deleting':
                if pr.state in ['starting', 'running', 'failed']:
                    pr.state = args['state']
                    self.delete(provision_id)
            else:
                pr.state = args['state']
                if pr.state == 'running' and user.is_admin:
                    if not pr.provisioned_at:
                        pr.provisioned_at = datetime.datetime.utcnow()

            db.session.commit()

        if args['public_ip'] and user.is_admin:
            pr.public_ip = args['public_ip']
            db.session.commit()


class ProvisionedResourceLogs(restful.Resource):
    parser = reqparse.RequestParser()
    parser.add_argument('type', type=str)
    parser.add_argument('text', type=str)

    @staticmethod
    def get_base_dir_and_filename(prov_res_id, log_type):
        log_dir = '/webapps/resource_cloud/provisioning_logs/%s' % prov_res_id

        # make sure the directory for this provisioned resource exists
        if not os.path.isdir(log_dir):
            os.mkdir(log_dir, 0o755)

        # check if we already have a file with the correct extension
        log_file_name = None
        for filename in os.listdir(log_dir):
            if filename.endswith('.' + log_type):
                log_file_name = filename
        if not log_file_name:
            log_file_name = '%s.%s' % (uuid.uuid4().hex, log_type)

        return log_dir, log_file_name

    @auth.login_required
    def get(self, provision_id):
        user = g.user
        provision = ProvisionedResource.query.filter_by(visual_id=provision_id)
        if not user.is_admin:
            provision = provision.filter_by(user_id=user.id)
        provision = provision.first()
        if not provision:
            abort(404)

        res = []
        for log_type in ['provisioning', 'deprovisioning']:
            log_dir, log_file_name = self.get_base_dir_and_filename(provision_id, log_type)
            res.append({'url': '/provisioning_logs/%s/%s' % (provision_id, log_file_name), 'type': log_type})

        return res

    @auth.login_required
    @requires_admin
    def patch(self, provision_id):
        args = self.parser.parse_args()
        pr = ProvisionedResource.query.filter_by(visual_id=provision_id).first()
        if not pr:
            abort(404)

        log_type = args['type']
        if not log_type:
            abort(403)

        if log_type in ('provisioning', 'deprovisioning'):
            log_dir, log_file_name = self.get_base_dir_and_filename(provision_id, log_type)

            with open('%s/%s' % (log_dir, log_file_name), 'a') as logfile:
                logfile.write(args['text'])
        else:
            abort(403)

        return 'ok'


resource_fields = {
    'id': fields.String(attribute='visual_id'),
    'vcpus': fields.String(default="4"),
    'max_lifetime': fields.Integer,
    'name': fields.String,
    'is_enabled': fields.Boolean,
    'plugin': fields.String,
    'config': fields.String,
}


class ResourceList(restful.Resource):
    @auth.login_required
    @marshal_with(resource_fields)
    def get(self):
        if g.user.is_admin and request.args.get('show_deactivated'):
            return Resource.query.all()
        return Resource.query.filter_by(is_enabled=True).all()

    @auth.login_required
    @requires_admin
    def post(self):
        form = ResourceForm()
        if not form.validate_on_submit():
            logging.warn("validation error on create resource")
            return form.errors, 422

        resource = Resource()
        resource.name = form.name.data
        resource.plugin = form.plugin.data
        resource.config = form.config.data

        db.session.add(resource)
        db.session.commit()


class ResourceView(restful.Resource):
    @auth.login_required
    @marshal_with(resource_fields)
    def get(self, resource_id):
        return Resource.query.filter_by(visual_id=resource_id).first()

    @auth.login_required
    @requires_admin
    def put(self, resource_id):
        form = ResourceForm()
        if not form.validate_on_submit():
            logging.warn("validation error on update resource config")
            return form.errors, 422

        resource = Resource.query.filter_by(visual_id=resource_id).first()
        resource.name = form.name.data
        resource.config = form.config.data
        resource.plugin = form.plugin.data
        resource.is_enabled = form.is_enabled.data

        db.session.add(resource)
        db.session.commit()


plugin_fields = {
    'id': fields.String(attribute='visual_id'),
    'name': fields.String,
    'schema': fields.Raw,
    'form': fields.Raw,
    'model': fields.String,
}


class PluginList(restful.Resource):
    @auth.login_required
    @requires_admin
    @marshal_with(plugin_fields)
    def get(self):
        return Plugin.query.all()

    @auth.login_required
    @requires_admin
    def post(self):
        form = PluginForm()
        if not form.validate_on_submit():
            logging.warn("validation error on update resource config")
            return form.errors, 422

        plugin = Plugin.query.filter_by(name=form.plugin.data).first()
        if not plugin:
            plugin = Plugin()
            plugin.name = form.plugin.data

        plugin.schema = form.schema.data
        plugin.form = form.schema.data
        plugin.model = form.model.data

        db.session.add(plugin)
        db.session.commit()


api_root = '/api/v1'
api.add_resource(FirstUserView, api_root + '/initialize')
api.add_resource(UserList,
                 api_root + '/users',
                 methods=['GET', 'POST', 'PATCH'])
api.add_resource(UserView, api_root + '/users/<string:user_id>')
api.add_resource(KeypairList, api_root + '/users/<string:user_id>/keypairs')
api.add_resource(KeypairView, api_root + '/users/<string:user_id>/keypairs/<string:keypair_id>')
api.add_resource(CreateKeyPair, api_root + '/users/<string:user_id>/keypairs/create')
api.add_resource(UploadKeyPair, api_root + '/users/<string:user_id>/keypairs/upload')
api.add_resource(SessionView, api_root + '/sessions')
api.add_resource(ActivationList, api_root + '/activations')
api.add_resource(ResourceList, api_root + '/resources')
api.add_resource(ResourceView, api_root + '/resources/<string:resource_id>')
api.add_resource(ProvisionedResourceList, api_root + '/provisioned_resources')
api.add_resource(ProvisionedResourceView,
                 api_root + '/provisioned_resources/<string:provision_id>',
                 methods=['GET', 'POST', 'DELETE', 'PATCH'])
api.add_resource(ProvisionedResourceLogs,
                 api_root + '/provisioned_resources/<string:provision_id>/logs',
                 methods=['GET', 'PATCH'])
api.add_resource(PluginList, api_root + '/plugins')
