from flask.ext import restful
from pouta_blueprints.app import app
from pouta_blueprints.views.blueprints import blueprints, BlueprintList, BlueprintView
from pouta_blueprints.views.plugins import plugins, PluginList, PluginView
from pouta_blueprints.views.users import users, UserList, UserView, KeypairList, CreateKeyPair, UploadKeyPair
from pouta_blueprints.views.instances import instances, InstanceList, InstanceView, InstanceLogs
from pouta_blueprints.views.activations import activations, ActivationList, ActivationView
from pouta_blueprints.views.firstuser import firstuser, FirstUserView
from pouta_blueprints.views.myip import myip, WhatIsMyIp
from pouta_blueprints.views.sessions import sessions, SessionView
from pouta_blueprints.models import db

db.init_app(app)
with app.app_context():
    db.create_all()

api = restful.Api(app)
api_root = '/api/v1'
api.add_resource(FirstUserView, api_root + '/initialize')
api.add_resource(UserList, api_root + '/users', methods=['GET', 'POST', 'PATCH'])
api.add_resource(UserView, api_root + '/users/<string:user_id>')
api.add_resource(KeypairList, api_root + '/users/<string:user_id>/keypairs')
api.add_resource(CreateKeyPair, api_root + '/users/<string:user_id>/keypairs/create')
api.add_resource(UploadKeyPair, api_root + '/users/<string:user_id>/keypairs/upload')
api.add_resource(SessionView, api_root + '/sessions')
api.add_resource(ActivationList, api_root + '/activations')
api.add_resource(ActivationView, api_root + '/activations/<string:token_id>')
api.add_resource(BlueprintList, api_root + '/blueprints')
api.add_resource(BlueprintView, api_root + '/blueprints/<string:blueprint_id>')
api.add_resource(InstanceList, api_root + '/instances')
api.add_resource(
    InstanceView,
    api_root + '/instances/<string:instance_id>',
    methods=['GET', 'POST', 'DELETE', 'PATCH'])
api.add_resource(
    InstanceLogs,
    api_root + '/instances/<string:instance_id>/logs',
    methods=['GET', 'PATCH'])
api.add_resource(PluginList, api_root + '/plugins')
api.add_resource(PluginView, api_root + '/plugins/<string:plugin_id>')
api.add_resource(WhatIsMyIp, api_root + '/what_is_my_ip', methods=['GET'])

app.register_blueprint(blueprints)
app.register_blueprint(plugins)
app.register_blueprint(users)
app.register_blueprint(instances)
app.register_blueprint(activations)
app.register_blueprint(firstuser)
app.register_blueprint(myip)
app.register_blueprint(sessions)
