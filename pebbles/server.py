import flask_restful as restful

from pebbles.app import app
from pebbles.views.activations import activations, ActivationList, ActivationView
from pebbles.views.environment_templates import EnvironmentTemplateList, EnvironmentTemplateView, EnvironmentTemplateCopy
from pebbles.views.environment_templates import environment_templates
from pebbles.views.environments import environments, EnvironmentList, EnvironmentView, EnvironmentCopy
from pebbles.views.export_stats import export_stats, ExportStatistics
from pebbles.views.workspaces import ClearUsersFromWorkspace
from pebbles.views.workspaces import WorkspaceList, WorkspaceView, WorkspaceJoin, WorkspaceListExit, WorkspaceExit, WorkspaceUsersList
from pebbles.views.workspaces import workspaces
from pebbles.views.import_export import import_export, ImportExportEnvironmentTemplates, ImportExportEnvironments
from pebbles.views.instances import instances, InstanceList, InstanceView, InstanceLogs
from pebbles.views.locks import locks, LockView, LockList
from pebbles.views.myip import myip, WhatIsMyIp
from pebbles.views.namespaced_keyvalues import namespaced_keyvalues, NamespacedKeyValueList, NamespacedKeyValueView
from pebbles.views.notifications import NotificationList, NotificationView
from pebbles.views.plugins import plugins, PluginList, PluginView
from pebbles.views.quota import quota, Quota, UserQuota
from pebbles.views.sessions import sessions, SessionView
from pebbles.views.stats import stats, StatsList
from pebbles.views.users import users, UserList, UserView, UserActivationUrl, UserBlacklist, UserWorkspaceOwner
from pebbles.views.variables import variables, PublicVariableList

api = restful.Api(app)
api_root = '/api/v1'
api.add_resource(UserList, api_root + '/users', methods=['GET', 'POST', 'PATCH'])
api.add_resource(UserView, api_root + '/users/<string:user_id>')
api.add_resource(UserActivationUrl, api_root + '/users/<string:user_id>/user_activation_url')
api.add_resource(UserBlacklist, api_root + '/users/<string:user_id>/user_blacklist')
api.add_resource(UserWorkspaceOwner, api_root + '/users/<string:user_id>/user_workspace_owner')
api.add_resource(WorkspaceList, api_root + '/workspaces')
api.add_resource(WorkspaceView, api_root + '/workspaces/<string:workspace_id>')
api.add_resource(WorkspaceJoin, api_root + '/workspaces/workspace_join/<string:join_code>')
api.add_resource(WorkspaceListExit, api_root + '/workspaces/workspace_list_exit')
api.add_resource(WorkspaceExit, api_root + '/workspaces/workspace_exit/<string:workspace_id>')
api.add_resource(WorkspaceUsersList, api_root + '/workspaces/<string:workspace_id>/users')
api.add_resource(ClearUsersFromWorkspace, api_root + '/workspaces/clear_users_from_workspace')
api.add_resource(NotificationList, api_root + '/notifications')
api.add_resource(NotificationView, api_root + '/notifications/<string:notification_id>')
api.add_resource(SessionView, api_root + '/sessions')
api.add_resource(ActivationList, api_root + '/activations')
api.add_resource(ActivationView, api_root + '/activations/<string:token_id>')
api.add_resource(EnvironmentTemplateList, api_root + '/environment_templates')
api.add_resource(EnvironmentTemplateView, api_root + '/environment_templates/<string:template_id>')
api.add_resource(EnvironmentTemplateCopy, api_root + '/environment_templates/template_copy/<string:template_id>')
api.add_resource(EnvironmentList, api_root + '/environments')
api.add_resource(EnvironmentView, api_root + '/environments/<string:environment_id>')
api.add_resource(EnvironmentCopy, api_root + '/environments/environment_copy/<string:environment_id>')
api.add_resource(InstanceList, api_root + '/instances')
api.add_resource(
    InstanceView,
    api_root + '/instances/<string:instance_id>',
    methods=['GET', 'POST', 'PUT', 'DELETE', 'PATCH'])
api.add_resource(
    InstanceLogs,
    api_root + '/instances/<string:instance_id>/logs',
    methods=['GET', 'PATCH', 'DELETE'])
api.add_resource(PluginList, api_root + '/plugins')
api.add_resource(PluginView, api_root + '/plugins/<string:plugin_id>')
api.add_resource(PublicVariableList, api_root + '/config')
api.add_resource(WhatIsMyIp, api_root + '/what_is_my_ip')
api.add_resource(Quota, api_root + '/quota')
api.add_resource(UserQuota, api_root + '/quota/<string:user_id>')
api.add_resource(LockList, api_root + '/locks')
api.add_resource(LockView, api_root + '/locks/<string:lock_id>')
api.add_resource(ImportExportEnvironmentTemplates, api_root + '/import_export/environment_templates')
api.add_resource(ImportExportEnvironments, api_root + '/import_export/environments')
api.add_resource(StatsList, api_root + '/stats')
api.add_resource(ExportStatistics, api_root + '/export_stats/export_statistics')
api.add_resource(NamespacedKeyValueList, api_root + '/namespaced_keyvalues')
api.add_resource(NamespacedKeyValueView, api_root + '/namespaced_keyvalues/<string:namespace>/<string:key>')

app.register_blueprint(environment_templates)
app.register_blueprint(environments)
app.register_blueprint(plugins)
app.register_blueprint(users)
app.register_blueprint(workspaces)
app.register_blueprint(instances)
app.register_blueprint(activations)
app.register_blueprint(myip)
app.register_blueprint(sessions)
app.register_blueprint(variables)
app.register_blueprint(quota)
app.register_blueprint(locks)
app.register_blueprint(import_export)
app.register_blueprint(stats)
app.register_blueprint(export_stats)
app.register_blueprint(namespaced_keyvalues)

from pebbles.views.sso import oauth2_login
app.add_url_rule('/oauth2', oauth2_login)
