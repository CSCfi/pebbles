import uuid
import os
from flask import abort, g, request
from flask.ext.restful import fields, marshal_with, reqparse
from sqlalchemy import desc
import json
import logging
import names
import re
import werkzeug
import datetime
from functools import wraps

from pouta_blueprints.models import User, ActivationToken, Blueprint, Plugin
from pouta_blueprints.models import Instance, SystemToken, Keypair
from pouta_blueprints.forms import UserForm, SessionCreateForm, ActivationForm
from pouta_blueprints.forms import ChangePasswordForm, PasswordResetRequestForm
from pouta_blueprints.forms import BlueprintForm
from pouta_blueprints.forms import PluginForm, InstanceForm

from pouta_blueprints.server import auth, db, restful, app
from pouta_blueprints.tasks import run_provisioning, run_deprovisioning
from pouta_blueprints.tasks import send_mails

from pouta_blueprints.utils import generate_ssh_keypair

USER_INSTANCE_LIMIT = 5


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
            worker = User('worker@pouta_blueprints', app.config['SECRET_KEY'], is_admin=True)
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

        if not app.config['SKIP_TASK_QUEUE']:
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
        user = User.query.filter_by(user_id=user_id).first()
        if not user:
            abort(404)
        user.set_password(form.password.data)
        db.session.add(user)
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

        if not user:
            abort(404)

        return Keypair.query.filter_by(user_id=user.id).order_by(desc("id")).all()


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


class ActivationView(restful.Resource):
    def post(self, token_id):
        form = ActivationForm()
        if not form.validate_on_submit():
            return form.errors, 422

        token = ActivationToken.query.filter_by(token=token_id).first()
        if not token:
            return abort(410)

        user = User.query.filter_by(id=token.user_id).first()
        if not user:
            return abort(410)

        user.set_password(form.password.data)
        user.is_active = True

        db.session.add(user)
        db.session.delete(token)
        db.session.commit()


class ActivationList(restful.Resource):
    def post(self):
        form = PasswordResetRequestForm()
        if not form.validate_on_submit():
            return form.errors, 422

        user = User.query.filter_by(email=form.email.data).first()
        if not user:
            abort(404)

        token = ActivationToken(user)

        db.session.add(token)
        db.session.commit()
        if not app.config['SKIP_TASK_QUEUE']:
            send_mails.delay([(user.email, token.token)])


instance_fields = {
    'id': fields.String(attribute='visual_id'),
    'name': fields.String,
    'provisioned_at': fields.DateTime,
    'lifetime_left': fields.Integer,
    'max_lifetime': fields.Integer,
    'state': fields.String,
    'error_msg': fields.String,
    'user_id': fields.String,
    'blueprint_id': fields.String,
    'can_update_connectivity': fields.Boolean(default=False),
    'public_ip': fields.String,
    'logs': fields.Raw,
}


class InstanceList(restful.Resource):
    @auth.login_required
    @marshal_with(instance_fields)
    def get(self):
        user = g.user
        if user.is_admin:
            instances = Instance.query.filter(Instance.state != 'deleted').all()
        else:
            instances = Instance.query.filter_by(user_id=user.id). \
                filter((Instance.state != 'deleted')).all()

        for instance in instances:
            if user.is_admin:
                owner = User.query.filter_by(id=instance.user_id).first()
                instance.user_id = owner.visual_id
            else:
                instance.user_id = user.visual_id

            instance.logs = InstanceLogs.get_logfile_urls(instance.visual_id)

            blueprint = Blueprint.query.filter_by(id=instance.blueprint_id).first()

            if not blueprint:
                logging.warn("instance %s has a reference to non-existing blueprint" % instance.visual_id)
                continue

            instance.blueprint_id = blueprint.visual_id
            age = 0
            if instance.provisioned_at:
                age = (datetime.datetime.utcnow() - instance.provisioned_at).total_seconds()
            instance.lifetime_left = max(blueprint.max_lifetime - age, 0)
            instance.max_lifetime = blueprint.max_lifetime

        return instances

    @auth.login_required
    def post(self):
        user = g.user

        form = InstanceForm()
        if not form.validate_on_submit():
            logging.warn("validation error on user login")
            return form.errors, 422

        blueprint_id = form.blueprint.data

        blueprint = Blueprint.query.filter_by(visual_id=blueprint_id).filter_by(is_enabled=True).first()
        if not blueprint:
            abort(404)

        blueprints_for_user = Instance.query.filter_by(blueprint_id=blueprint_id). \
            filter_by(user_id=user.id).filter(Instance.state != 'deleted').all()
        if blueprints_for_user and len(blueprints_for_user) >= USER_INSTANCE_LIMIT:
            abort(409)

        instance = Instance(blueprint, user)

        # decide on a name that is not used currently
        all_instances = Instance.query.all()
        existing_names = [x.name for x in all_instances]
        # Note: the potential race is solved by unique constraint in database
        while True:
            c_name = names.get_first_name().lower()
            if c_name not in existing_names:
                instance.name = c_name
                break
        token = SystemToken('provisioning')
        db.session.add(instance)
        db.session.add(token)
        db.session.commit()

        if not app.config['SKIP_TASK_QUEUE']:
            run_provisioning.delay(token.token, instance.visual_id)


class InstanceView(restful.Resource):
    parser = reqparse.RequestParser()
    parser.add_argument('state', type=str)
    parser.add_argument('public_ip', type=str)
    parser.add_argument('error_msg', type=str)
    parser.add_argument('client_ip', type=str)

    @auth.login_required
    @marshal_with(instance_fields)
    def get(self, instance_id):
        user = g.user
        query = Instance.query.filter_by(visual_id=instance_id)
        if not user.is_admin:
            query = query.filter_by(user_id=user.id)
        instance = query.first()
        if not instance:
            abort(404)

        if user.is_admin:
            owner = User.query.filter_by(id=instance.user_id).first()
            instance.user_id = owner.visual_id
        else:
            instance.user_id = user.visual_id

        blueprint = Blueprint.query.filter_by(id=instance.blueprint_id).first()
        instance.blueprint_id = blueprint.visual_id

        instance.logs = InstanceLogs.get_logfile_urls(instance.visual_id)

        if 'allow_update_client_connectivity' in blueprint.config:
            instance.can_update_connectivity = True

        age = 0
        if instance.provisioned_at:
            age = (datetime.datetime.utcnow() - instance.provisioned_at).total_seconds()
        instance.lifetime_left = max(blueprint.max_lifetime - age, 0)
        instance.max_lifetime = blueprint.max_lifetime

        return instance

    @auth.login_required
    def delete(self, instance_id):
        user = g.user
        query = Instance.query.filter_by(visual_id=instance_id)
        if not user.is_admin:
            query = query.filter_by(user_id=user.id)
        instance = query.first()
        if not instance:
            abort(404)
        instance.state = 'deleting'
        token = SystemToken('provisioning')
        db.session.add(token)
        db.session.commit()
        if not app.config['SKIP_TASK_QUEUE']:
            run_deprovisioning.delay(token.token, instance.visual_id)

    @auth.login_required
    def patch(self, instance_id):
        user = g.user
        args = self.parser.parse_args()
        query = Instance.query.filter_by(visual_id=instance_id)
        if not user.is_admin:
            query = query.filter_by(user_id=user.id)
        instance = query.first()
        if not instance:
            abort(404)

        # TODO: add a model for state transitions
        if args.get('state'):
            if args['state'] == 'deleting':
                if instance.state in ['starting', 'running', 'failed']:
                    instance.state = args['state']
                    instance.error_msg = ''
                    self.delete(instance_id)
            else:
                instance.state = args['state']
                if instance.state == 'running' and user.is_admin:
                    if not instance.provisioned_at:
                        instance.provisioned_at = datetime.datetime.utcnow()

            db.session.commit()

        if args.get('error_msg'):
            instance.error_msg = args['error_msg']
            db.session.commit()

        if args.get('public_ip') and user.is_admin:
            instance.public_ip = args['public_ip']
            db.session.commit()

        if args['client_ip']:
            instance.client_ip = request.remote_addr
            db.session.commit()


class InstanceLogs(restful.Resource):
    parser = reqparse.RequestParser()
    parser.add_argument('type', type=str)
    parser.add_argument('text', type=str)

    @staticmethod
    def get_base_dir_and_filename(instance_id, log_type, create_missing_filename=False):
        log_dir = '/webapps/pouta_blueprints/provisioning_logs/%s' % instance_id

        if not app.config['WRITE_PROVISIONING_LOGS']:
            return None, None

        # make sure the directory for this instance exists
        if not os.path.isdir(log_dir):
            os.mkdir(log_dir, 0o755)

        # check if we already have a file with the correct extension
        log_file_name = None
        for filename in os.listdir(log_dir):
            if filename.endswith('.' + log_type + '.txt'):
                log_file_name = filename
        if not log_file_name and create_missing_filename:
            log_file_name = '%s.%s.txt' % (uuid.uuid4().hex, log_type)

        return log_dir, log_file_name

    @staticmethod
    def get_logfile_urls(instance_id):
        res = []
        for log_type in ['provisioning', 'deprovisioning']:
            log_dir, log_file_name = InstanceLogs.get_base_dir_and_filename(instance_id, log_type)
            if log_file_name:
                res.append({'url': '/provisioning_logs/%s/%s' % (instance_id, log_file_name), 'type': log_type})
        return res

    @auth.login_required
    @requires_admin
    def patch(self, instance_id):
        args = self.parser.parse_args()
        instance = Instance.query.filter_by(visual_id=instance_id).first()
        if not instance:
            abort(404)

        log_type = args['type']
        if not log_type:
            abort(403)

        if log_type in ('provisioning', 'deprovisioning'):
            log_dir, log_file_name = self.get_base_dir_and_filename(
                instance_id, log_type, create_missing_filename=True)

            with open('%s/%s' % (log_dir, log_file_name), 'a') as logfile:
                logfile.write(args['text'])
        else:
            abort(403)

        return 'ok'


blueprint_fields = {
    'id': fields.String(attribute='visual_id'),
    'max_lifetime': fields.Integer,
    'name': fields.String,
    'is_enabled': fields.Boolean,
    'plugin': fields.String,
    'config': fields.Raw,
    'schema': fields.Raw,
    'form': fields.Raw
}


class BlueprintList(restful.Resource):
    @auth.login_required
    @marshal_with(blueprint_fields)
    def get(self):
        query = Blueprint.query
        if not g.user.is_admin:
            query = query.filter_by(is_enabled=True)

        results = []
        for blueprint in query.all():
            plugin = Plugin.query.filter_by(visual_id=blueprint.plugin).first()
            blueprint.schema = plugin.schema
            blueprint.form = plugin.form
            results.append(blueprint)
        return results

    @auth.login_required
    @requires_admin
    def post(self):
        form = BlueprintForm()
        if not form.validate_on_submit():
            logging.warn("validation error on create blueprint")
            return form.errors, 422

        blueprint = Blueprint()
        blueprint.name = form.name.data
        blueprint.plugin = form.plugin.data
        blueprint.config = form.config.data

        if 'maximum_lifetime' in form.config.data:
            try:
                blueprint.max_lifetime = int(form.config.data['maximum_lifetime'])
            except:
                pass

        db.session.add(blueprint)
        db.session.commit()


class BlueprintView(restful.Resource):
    @auth.login_required
    @marshal_with(blueprint_fields)
    def get(self, blueprint_id):
        return Blueprint.query.filter_by(visual_id=blueprint_id).first()

    @auth.login_required
    @requires_admin
    def put(self, blueprint_id):
        form = BlueprintForm()
        if not form.validate_on_submit():
            logging.warn("validation error on update blueprint config")
            return form.errors, 422

        blueprint = Blueprint.query.filter_by(visual_id=blueprint_id).first()
        if not blueprint:
            abort(404)
        blueprint.name = form.name.data
        blueprint.config = form.config.data
        if 'maximum_lifetime' in blueprint.config:
            try:
                blueprint.max_lifetime = int(blueprint.config['maximum_lifetime'])
            except:
                pass

        blueprint.plugin = form.plugin.data
        blueprint.is_enabled = form.is_enabled.data

        db.session.add(blueprint)
        db.session.commit()


plugin_fields = {
    'id': fields.String(attribute='visual_id'),
    'name': fields.String,
    'schema': fields.Raw,
    'form': fields.Raw,
    'model': fields.Raw,
}


class PluginView(restful.Resource):
    @auth.login_required
    @requires_admin
    @marshal_with(plugin_fields)
    def get(self, plugin_id):
        plugin = Plugin.query.filter_by(visual_id=plugin_id).first()
        if not plugin:
            abort(404)
        return plugin


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
            logging.warn("validation error on update blueprint config")
            return form.errors, 422

        plugin = Plugin.query.filter_by(name=form.plugin.data).first()
        if not plugin:
            plugin = Plugin()
            plugin.name = form.plugin.data

        plugin.schema = json.loads(form.schema.data)
        plugin.form = json.loads(form.form.data)
        plugin.model = json.loads(form.model.data)

        db.session.add(plugin)
        db.session.commit()


def setup_resource_urls(api_service):
    api_root = '/api/v1'
    api_service.add_resource(FirstUserView, api_root + '/initialize')
    api_service.add_resource(UserList, api_root + '/users', methods=['GET', 'POST', 'PATCH'])
    api_service.add_resource(UserView, api_root + '/users/<string:user_id>')
    api_service.add_resource(KeypairList, api_root + '/users/<string:user_id>/keypairs')
    api_service.add_resource(CreateKeyPair, api_root + '/users/<string:user_id>/keypairs/create')
    api_service.add_resource(UploadKeyPair, api_root + '/users/<string:user_id>/keypairs/upload')
    api_service.add_resource(SessionView, api_root + '/sessions')
    api_service.add_resource(ActivationList, api_root + '/activations')
    api_service.add_resource(ActivationView, api_root + '/activations/<string:token_id>')
    api_service.add_resource(BlueprintList, api_root + '/blueprints')
    api_service.add_resource(BlueprintView, api_root + '/blueprints/<string:blueprint_id>')
    api_service.add_resource(InstanceList, api_root + '/instances')
    api_service.add_resource(
        InstanceView,
        api_root + '/instances/<string:instance_id>',
        methods=['GET', 'POST', 'DELETE', 'PATCH'])
    api_service.add_resource(
        InstanceLogs,
        api_root + '/instances/<string:instance_id>/logs',
        methods=['GET', 'PATCH'])
    api_service.add_resource(PluginList, api_root + '/plugins')
    api_service.add_resource(PluginView, api_root + '/plugins/<string:plugin_id>')
