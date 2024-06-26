import logging
import os as os

import flask_restful as restful
from flask import Flask
from flask_bcrypt import Bcrypt
from flask_migrate import Migrate
from flask_sqlalchemy import SQLAlchemy

from pebbles.config import TestConfig, RuntimeConfig
from pebbles.utils import init_logging

db = SQLAlchemy()
migrate = Migrate()
bcrypt = Bcrypt()


def create_app(test_config=None):
    app = Flask(__name__, static_url_path='')
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

    # initialize migrations with Alembic
    migrate.init_app(app, db)

    if 'REMOTE_DEBUG_SERVER' in os.environ:
        print('trying to connect to remote debug server at %s ' % os.environ['REMOTE_DEBUG_SERVER'])
        import pydevd_pycharm

        pydevd_pycharm.settrace(
            host=os.environ['REMOTE_DEBUG_SERVER'],
            port=os.environ.get('REMOTE_DEBUG_PORT', 12345),
            stdoutToServer=True,
            stderrToServer=True,
            suspend=False
        )
        print('API: connected to remote debug server at %s ' % os.environ['REMOTE_DEBUG_SERVER'])

    # unit tests need a config with tweaked default values and no environment variable resolving - unit tests can be run
    # in a container that has environment set up for real

    if test_config:
        app_config = test_config
    elif os.environ.get('UNITTEST') == '1':
        app_config = TestConfig()
    else:
        app_config = RuntimeConfig()

    # set up logging
    init_logging(app_config, 'api')

    # configure flask
    app.config.from_object(app_config)

    # insert database password to SQLALCHEMY_DATABASE_URI from a separate source
    if app.config['DATABASE_PASSWORD']:
        app.config['SQLALCHEMY_DATABASE_URI'] = (app.config['SQLALCHEMY_DATABASE_URI']
                                                 .replace('__PASSWORD__', app.config['DATABASE_PASSWORD']))

    bcrypt.init_app(app)
    db.init_app(app)

    # Enable debugging SQLAlchemy queries. Level must be set as an integer, take a look at logging constants for values.
    # https://docs.python.org/3.9/library/logging.html#logging-levels
    # Hint: logging.INFO (=20) gives you SQL output for each query
    if 'SQLALCHEMY_LOGGING_LEVEL' in os.environ:
        logging.getLogger("sqlalchemy.engine").setLevel(int(os.environ.get('SQLALCHEMY_LOGGING_LEVEL')))

    # setup API endpoints
    init_api(app)

    @app.after_request
    def add_headers(r):
        r.headers['X-Content-Type-Options'] = 'nosniff'
        r.headers['X-XSS-Protection'] = '1; mode=block'
        r.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
        r.headers['Pragma'] = 'no-cache'
        r.headers['Expires'] = '0'
        r.headers['Strict-Transport-Security'] = 'max-age=31536000'
        # does not work without unsafe-inline / unsafe-eval
        csp_list = [
            "img-src 'self' data:",
            "script-src 'self' 'unsafe-inline' 'unsafe-eval'",
            "style-src 'self' 'unsafe-inline'",
            "default-src 'self'",
        ]
        r.headers['Content-Security-Policy'] = '; '.join(csp_list)

        # Sometimes we need to allow additional domains in CORS during UI development.
        # Do not set this in production.
        if 'DISABLE_CORS' in os.environ and os.environ['DISABLE_CORS']:
            r.headers['Access-Control-Allow-Origin'] = '*'
            r.headers['Access-Control-Allow-Headers'] = '*, Authorization'
            r.headers['Access-Control-Allow-Methods'] = '*'

        return r

    return app


def init_api(app: Flask):
    from pebbles.views.alerts import AlertList, AlertView, SystemStatus, AlertReset
    from pebbles.views.app_version import AppVersionList
    from pebbles.views.application_categories import ApplicationCategoryList
    from pebbles.views.application_sessions import ApplicationSessionList, ApplicationSessionView, \
        ApplicationSessionLogs
    from pebbles.views.application_templates import ApplicationTemplateList, ApplicationTemplateView, \
        ApplicationTemplateCopy
    from pebbles.views.applications import ApplicationList, ApplicationView, ApplicationCopy, \
        ApplicationAttributeLimits
    from pebbles.views.clusters import ClusterList
    from pebbles.views.helps import HelpsList
    from pebbles.views.locks import LockView, LockList
    from pebbles.views.messages import MessageList, MessageView
    from pebbles.views.public_config import PublicConfigList, PublicStructuredConfigList
    from pebbles.views.service_announcements import ServiceAnnouncementList, ServiceAnnouncementListPublic, \
        ServiceAnnouncementListAdmin, ServiceAnnouncementViewAdmin
    from pebbles.views.sessions import SessionView
    from pebbles.views.tasks import TaskList, TaskView, TaskAddResults
    from pebbles.views.users import UserList, UserView, UserWorkspaceMembershipList
    from pebbles.views.workspaces import (
        WorkspaceClearMembers, WorkspaceTransferOwnership, WorkspaceAccounting,
        WorkspaceMemoryLimitGiB, WorkspaceModifyUserFolderSize,
        WorkspaceModifyCluster,
        WorkspaceClearExpiredMembers, WorkspaceModifyMembershipExpiryPolicy,
        WorkspaceModifyMembershipJoinPolicy,
        WorkspaceCreateVolumeTasks, WorkspaceModifyExpiryTs
    )
    from pebbles.views.workspaces import WorkspaceList, WorkspaceView, JoinWorkspace, WorkspaceExit, WorkspaceMemberList
    from pebbles.views.sso import oauth2_login

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
    api.add_resource(WorkspaceModifyExpiryTs, api_root + '/workspaces/<string:workspace_id>/expiry_ts')
    api.add_resource(WorkspaceCreateVolumeTasks,
                     api_root + '/workspaces/<string:workspace_id>/create_volume_tasks')
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
    api.add_resource(PublicStructuredConfigList, api_root + '/structured_config')
    api.add_resource(AppVersionList, api_root + '/version')
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
    api.add_resource(
        TaskAddResults,
        api_root + '/tasks/<string:task_id>/results',
        methods=['PUT']
    )

    # Setup route for readiness/liveness probe check
    @app.route('/healthz')
    def healthz():
        return 'ok'

    @app.route('/favicon.ico')
    def favicon():
        return app.send_static_file('favicon.ico')

    @app.route('/oauth2')
    def oauth2():
        return oauth2_login()
