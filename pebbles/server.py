import flask_restful as restful

from pebbles.app import app
from pebbles.views.alerts import alerts, AlertList, AlertView, SystemStatus
from pebbles.views.clusters import clusters, ClusterList
from pebbles.views.environment_categories import EnvironmentCategoryList
from pebbles.views.environment_sessions import environment_sessions, EnvironmentSessionList, EnvironmentSessionView, \
    EnvironmentSessionLogs
from pebbles.views.environment_templates import EnvironmentTemplateList, EnvironmentTemplateView, \
    EnvironmentTemplateCopy
from pebbles.views.environment_templates import environment_templates
from pebbles.views.environments import environments, EnvironmentList, EnvironmentView, EnvironmentCopy
from pebbles.views.helps import helps, HelpsList
from pebbles.views.import_export import import_export, ImportExportEnvironmentTemplates, ImportExportEnvironments
from pebbles.views.locks import locks, LockView, LockList
from pebbles.views.messages import MessageList, MessageView
from pebbles.views.sessions import sessions, SessionView
from pebbles.views.users import users, UserList, UserView, UserWorkspaceAssociationList
from pebbles.views.variables import variables, PublicVariableList
from pebbles.views.workspaces import WorkspaceClearMembers, join_workspace
from pebbles.views.workspaces import WorkspaceList, WorkspaceView, JoinWorkspace, WorkspaceExit, WorkspaceMemberList
from pebbles.views.workspaces import workspaces

api = restful.Api(app)
api_root = '/api/v1'
api.add_resource(UserList, api_root + '/users')
api.add_resource(UserView, api_root + '/users/<string:user_id>', methods=['GET', 'DELETE', 'PATCH'])
api.add_resource(UserWorkspaceAssociationList, api_root + '/users/<string:user_id>/workspace_associations')
api.add_resource(WorkspaceList, api_root + '/workspaces')
api.add_resource(WorkspaceView, api_root + '/workspaces/<string:workspace_id>')
api.add_resource(
    WorkspaceMemberList,
    api_root + '/workspaces/<string:workspace_id>/members',
    methods=['GET', 'PATCH'])
api.add_resource(WorkspaceClearMembers, api_root + '/workspaces/<string:workspace_id>/clear_members')
api.add_resource(WorkspaceExit, api_root + '/workspaces/<string:workspace_id>/exit')
api.add_resource(JoinWorkspace, api_root + '/join_workspace/<string:join_code>')
api.add_resource(MessageList, api_root + '/messages')
api.add_resource(MessageView, api_root + '/messages/<string:message_id>')
api.add_resource(SessionView, api_root + '/sessions')
api.add_resource(EnvironmentTemplateList, api_root + '/environment_templates')
api.add_resource(EnvironmentTemplateView, api_root + '/environment_templates/<string:template_id>')
api.add_resource(EnvironmentTemplateCopy, api_root + '/environment_templates/template_copy/<string:template_id>')
api.add_resource(EnvironmentList, api_root + '/environments')
api.add_resource(EnvironmentView, api_root + '/environments/<string:environment_id>')
api.add_resource(EnvironmentCopy, api_root + '/environments/environment_copy/<string:environment_id>')
api.add_resource(EnvironmentSessionList, api_root + '/environment_sessions')
api.add_resource(
    EnvironmentSessionView,
    api_root + '/environment_sessions/<string:environment_session_id>',
    methods=['GET', 'POST', 'DELETE', 'PATCH'])
api.add_resource(
    EnvironmentSessionLogs,
    api_root + '/environment_sessions/<string:environment_session_id>/logs',
    methods=['GET', 'PATCH', 'DELETE'])
api.add_resource(ClusterList, api_root + '/clusters')
api.add_resource(PublicVariableList, api_root + '/config')
api.add_resource(LockList, api_root + '/locks')
api.add_resource(LockView, api_root + '/locks/<string:lock_id>')
api.add_resource(ImportExportEnvironmentTemplates, api_root + '/import_export/environment_templates')
api.add_resource(ImportExportEnvironments, api_root + '/import_export/environments')
api.add_resource(EnvironmentCategoryList, api_root + '/environment_categories')
api.add_resource(HelpsList, api_root + '/help')
api.add_resource(AlertList, api_root + '/alerts')
api.add_resource(AlertView, api_root + '/alerts/<string:target>/<string:source>')
api.add_resource(SystemStatus, api_root + '/status')

app.register_blueprint(environment_templates)
app.register_blueprint(environments)
app.register_blueprint(clusters)
app.register_blueprint(users)
app.register_blueprint(workspaces)
app.register_blueprint(join_workspace)
app.register_blueprint(environment_sessions)
app.register_blueprint(sessions)
app.register_blueprint(variables)
app.register_blueprint(locks)
app.register_blueprint(import_export)
app.register_blueprint(helps)
app.register_blueprint(alerts)

from pebbles.views.sso import oauth2_login

app.add_url_rule('/oauth2', oauth2_login)
