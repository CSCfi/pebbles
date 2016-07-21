import logging
import uuid

from flask import render_template
from flask.ext import restful
try:
    from flask_sso import SSO
except:
    logging.info("flask_sso library is not installed, Shibboleth authentication will not work")

from pouta_blueprints.app import app
from pouta_blueprints.models import db, User

from pouta_blueprints.views.commons import create_user
from pouta_blueprints.views.blueprints import blueprints, BlueprintList, BlueprintView
from pouta_blueprints.views.plugins import plugins, PluginList, PluginView
from pouta_blueprints.views.users import users, UserList, UserView, UserActivationUrl, UserBlacklist, KeypairList, CreateKeyPair, UploadKeyPair
from pouta_blueprints.views.groups import groups, GroupList, GroupView, GroupJoin
from pouta_blueprints.views.notifications import NotificationList, NotificationView
from pouta_blueprints.views.instances import instances, InstanceList, InstanceView, InstanceLogs
from pouta_blueprints.views.activations import activations, ActivationList, ActivationView
from pouta_blueprints.views.firstuser import firstuser, FirstUserView
from pouta_blueprints.views.myip import myip, WhatIsMyIp
from pouta_blueprints.views.quota import quota, Quota, UserQuota
from pouta_blueprints.views.sessions import sessions, SessionView
from pouta_blueprints.views.variables import variables, VariableList, VariableView, PublicVariableList
from pouta_blueprints.views.locks import locks, LockView
from pouta_blueprints.views.stats import stats, StatsList
from pouta_blueprints.views.import_export import import_export, ImportExportBlueprints

api = restful.Api(app)
api_root = '/api/v1'
api.add_resource(FirstUserView, api_root + '/initialize')
api.add_resource(UserList, api_root + '/users', methods=['GET', 'POST', 'PATCH'])
api.add_resource(UserView, api_root + '/users/<string:user_id>')
api.add_resource(UserActivationUrl, api_root + '/users/<string:user_id>/user_activation_url')
api.add_resource(UserBlacklist, api_root + '/users/<string:user_id>/user_blacklist')
api.add_resource(KeypairList, api_root + '/users/<string:user_id>/keypairs')
api.add_resource(CreateKeyPair, api_root + '/users/<string:user_id>/keypairs/create')
api.add_resource(UploadKeyPair, api_root + '/users/<string:user_id>/keypairs/upload')
api.add_resource(GroupList, api_root + '/groups')
api.add_resource(GroupView, api_root + '/groups/<string:group_id>')
api.add_resource(GroupJoin, api_root + '/groups/<string:join_code>')
api.add_resource(NotificationList, api_root + '/notifications')
api.add_resource(NotificationView, api_root + '/notifications/<string:notification_id>')
api.add_resource(SessionView, api_root + '/sessions')
api.add_resource(ActivationList, api_root + '/activations')
api.add_resource(ActivationView, api_root + '/activations/<string:token_id>')
api.add_resource(BlueprintList, api_root + '/blueprints')
api.add_resource(BlueprintView, api_root + '/blueprints/<string:blueprint_id>')
api.add_resource(InstanceList, api_root + '/instances')
api.add_resource(
    InstanceView,
    api_root + '/instances/<string:instance_id>',
    methods=['GET', 'POST', 'PUT', 'DELETE', 'PATCH'])
api.add_resource(
    InstanceLogs,
    api_root + '/instances/<string:instance_id>/logs',
    methods=['GET', 'PATCH'])
api.add_resource(PluginList, api_root + '/plugins')
api.add_resource(PluginView, api_root + '/plugins/<string:plugin_id>')
api.add_resource(VariableList, api_root + '/variables')
api.add_resource(VariableView, api_root + '/variables/<string:variable_id>')
api.add_resource(PublicVariableList, api_root + '/config')
api.add_resource(WhatIsMyIp, api_root + '/what_is_my_ip')
api.add_resource(Quota, api_root + '/quota')
api.add_resource(UserQuota, api_root + '/quota/<string:user_id>')
api.add_resource(LockView, api_root + '/locks/<string:lock_id>')
api.add_resource(StatsList, api_root + '/stats')
api.add_resource(ImportExportBlueprints, api_root + '/import_export/blueprints')

app.register_blueprint(blueprints)
app.register_blueprint(plugins)
app.register_blueprint(users)
app.register_blueprint(groups)
app.register_blueprint(instances)
app.register_blueprint(activations)
app.register_blueprint(firstuser)
app.register_blueprint(myip)
app.register_blueprint(sessions)
app.register_blueprint(variables)
app.register_blueprint(quota)
app.register_blueprint(locks)
app.register_blueprint(import_export)
app.register_blueprint(stats)

if app.config['ENABLE_SHIBBOLETH_LOGIN']:
    sso = SSO(app=app)

    @sso.login_handler
    def login(user_info):
        eppn = user_info['eppn']
        user = User.query.filter_by(email=eppn).first()
        if not user:
            user = create_user(eppn, password=uuid.uuid4().hex)
        if not user.is_active:
            user.is_active = True
            db.session.commit()
        if user.is_blocked:
            error_description = 'You have been blocked, contact your administrator'
            return render_template('error.html', error_title='User Blocked', error_description=error_description)

        token = user.generate_auth_token(app.config['SECRET_KEY'])
        return render_template(
            'login.html', token=token, username=eppn, is_admin=user.is_admin, userid=user.id)

    @sso.login_error_handler
    def login_error(user_info):
        error_title = 'unknown error'
        error_description = ''
        if not user_info.get('eppn'):
            error_title = 'Login not available'
            error_description = (
                'Your home organization did not return us your login attributes which prevents '
                'you from logging in. Waiting a bit might resolve this.')

        return render_template('error.html', error_title=error_title, error_description=error_description)
