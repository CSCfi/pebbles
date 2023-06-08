import flask_restful as restful

from pebbles.app import app
from pebbles.views.alerts import alerts, AlertList, AlertView, SystemStatus, AlertReset
from pebbles.views.application_categories import ApplicationCategoryList
from pebbles.views.application_sessions import application_sessions, ApplicationSessionList, ApplicationSessionView, \
    ApplicationSessionLogs
from pebbles.views.application_templates import ApplicationTemplateList, ApplicationTemplateView, \
    ApplicationTemplateCopy
from pebbles.views.application_templates import application_templates
from pebbles.views.applications import applications, ApplicationList, ApplicationView, ApplicationCopy, \
    ApplicationAttributeLimits
from pebbles.views.clusters import clusters, ClusterList
from pebbles.views.helps import helps, HelpsList
from pebbles.views.locks import locks, LockView, LockList
from pebbles.views.messages import MessageList, MessageView
from pebbles.views.public_config import variables, PublicConfigList
from pebbles.views.service_announcements import ServiceAnnouncementList, ServiceAnnouncementListPublic, \
    ServiceAnnouncementListAdmin, ServiceAnnouncementViewAdmin
from pebbles.views.sessions import sessions, SessionView
from pebbles.views.tasks import TaskList, TaskView
from pebbles.views.users import users, UserList, UserView, UserWorkspaceMembershipList
from pebbles.views.workspaces import WorkspaceClearMembers, WorkspaceTransferOwnership, join_workspace, \
    WorkspaceAccounting, WorkspaceMemoryLimitGiB, WorkspaceModifyUserFolderSize, WorkspaceModifyCluster, \
    WorkspaceClearExpiredMembers, WorkspaceModifyMembershipExpiryPolicy, WorkspaceModifyMembershipJoinPolicy
from pebbles.views.workspaces import WorkspaceList, WorkspaceView, JoinWorkspace, WorkspaceExit, WorkspaceMemberList
from pebbles.views.workspaces import workspaces

api = restful.Api(app)
api_root = '/api/v1'
api.add_resource(UserList, api_root + '/users', methods=['GET', 'POST'])
api.add_resource(UserView, api_root + '/users/<string:user_id>', methods=['GET', 'DELETE', 'PATCH'])
api.add_resource(UserWorkspaceMembershipList, api_root + '/users/<string:user_id>/workspace_memberships')
api.add_resource(WorkspaceList, api_root + '/workspaces')
api.add_resource(WorkspaceView, api_root + '/workspaces/<string:workspace_id>')
api.add_resource(
    WorkspaceMemberList,
    api_root + '/workspaces/<string:workspace_id>/members',
    methods=['GET', 'PATCH'])
api.add_resource(
    WorkspaceTransferOwnership, api_root + '/workspaces/<string:workspace_id>/transfer_ownership',
    methods=['PATCH'])
api.add_resource(WorkspaceClearMembers, api_root + '/workspaces/<string:workspace_id>/clear_members')
api.add_resource(WorkspaceClearExpiredMembers, api_root + '/workspaces/<string:workspace_id>/clear_expired_members')
api.add_resource(WorkspaceExit, api_root + '/workspaces/<string:workspace_id>/exit')
api.add_resource(WorkspaceAccounting, api_root + '/workspaces/<string:workspace_id>/accounting')
api.add_resource(WorkspaceMemoryLimitGiB, api_root + '/workspaces/<string:workspace_id>/memory_limit_gib')
api.add_resource(WorkspaceModifyUserFolderSize,
                 api_root + '/workspaces/<string:workspace_id>/user_work_folder_size_gib')
api.add_resource(WorkspaceModifyCluster, api_root + '/workspaces/<string:workspace_id>/cluster')
api.add_resource(WorkspaceModifyMembershipExpiryPolicy,
                 api_root + '/workspaces/<string:workspace_id>/membership_expiry_policy')
api.add_resource(WorkspaceModifyMembershipJoinPolicy,
                 api_root + '/workspaces/<string:workspace_id>/membership_join_policy')
api.add_resource(JoinWorkspace, api_root + '/join_workspace/<string:join_code>')
api.add_resource(MessageList, api_root + '/messages')
api.add_resource(MessageView, api_root + '/messages/<string:message_id>')
api.add_resource(ServiceAnnouncementList, api_root + '/service_announcements')
api.add_resource(ServiceAnnouncementListPublic, api_root + '/service_announcements_public')
api.add_resource(ServiceAnnouncementListAdmin, api_root + '/service_announcements_admin')
api.add_resource(ServiceAnnouncementViewAdmin,
                 api_root + '/service_announcements_admin/<string:service_announcement_id>')
api.add_resource(SessionView, api_root + '/sessions')
api.add_resource(ApplicationTemplateList, api_root + '/application_templates')
api.add_resource(ApplicationTemplateView, api_root + '/application_templates/<string:template_id>')
api.add_resource(ApplicationTemplateCopy, api_root + '/application_templates/template_copy/<string:template_id>')
api.add_resource(ApplicationList, api_root + '/applications')
api.add_resource(ApplicationView, api_root + '/applications/<string:application_id>')
api.add_resource(ApplicationCopy, api_root + '/applications/<string:application_id>/copy')
api.add_resource(ApplicationAttributeLimits, api_root + '/applications/<string:application_id>/attribute_limits')
api.add_resource(ApplicationSessionList, api_root + '/application_sessions')
api.add_resource(
    ApplicationSessionView,
    api_root + '/application_sessions/<string:application_session_id>',
    methods=['GET', 'POST', 'DELETE', 'PATCH'])
api.add_resource(
    ApplicationSessionLogs,
    api_root + '/application_sessions/<string:application_session_id>/logs',
    methods=['GET', 'PATCH', 'DELETE'])
api.add_resource(ClusterList, api_root + '/clusters')
api.add_resource(PublicConfigList, api_root + '/config')
api.add_resource(LockList, api_root + '/locks')
api.add_resource(LockView, api_root + '/locks/<string:lock_id>')
api.add_resource(ApplicationCategoryList, api_root + '/application_categories')
api.add_resource(HelpsList, api_root + '/help')
api.add_resource(AlertList, api_root + '/alerts')
api.add_resource(AlertView, api_root + '/alerts/<string:id>')
api.add_resource(AlertReset, api_root + '/alert_reset/<string:target>/<string:source>')
api.add_resource(SystemStatus, api_root + '/status')
api.add_resource(TaskList, api_root + '/tasks')
api.add_resource(
    TaskView,
    api_root + '/tasks/<string:task_id>',
    methods=['GET', 'POST', 'PATCH']
)

app.register_blueprint(application_templates)
app.register_blueprint(applications)
app.register_blueprint(clusters)
app.register_blueprint(users)
app.register_blueprint(workspaces)
app.register_blueprint(join_workspace)
app.register_blueprint(application_sessions)
app.register_blueprint(sessions)
app.register_blueprint(variables)
app.register_blueprint(locks)
app.register_blueprint(helps)
app.register_blueprint(alerts)

from pebbles.views.sso import oauth2_login

app.add_url_rule('/oauth2', oauth2_login)
