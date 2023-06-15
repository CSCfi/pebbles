import json
import time

from pebbles.models import User, Application, ApplicationSession, ApplicationSessionLog
from pebbles.models import db
from tests.conftest import PrimaryData, RequestMaker


def test_anonymous_create_application_session(rmaker: RequestMaker, pri_data: PrimaryData):
    data = {'application_id': pri_data.known_application_id}
    response = rmaker.make_request(
        method='POST',
        path='/api/v1/application_sessions',
        data=json.dumps(data))
    assert response.status_code == 401


def test_user_create_application_session(rmaker: RequestMaker, pri_data: PrimaryData):
    # User is not a part of the workspace (Workspace2)
    data = {'application_id': pri_data.known_application_id_g2}
    response = rmaker.make_authenticated_user_request(
        method='POST',
        path='/api/v1/application_sessions',
        data=json.dumps(data))
    assert response.status_code == 404

    # User is a part of the workspace (Workspace1), but already has 2 non-deleted sessions
    data = {'application_id': pri_data.known_application_id_empty}
    response = rmaker.make_authenticated_user_request(
        method='POST',
        path='/api/v1/application_sessions',
        data=json.dumps(data))
    assert response.status_code == 409

    # User-2 is a part of the workspace (Workspace1), no sessions previously
    data = {'application_id': pri_data.known_application_id_empty}
    response = rmaker.make_authenticated_user_2_request(
        method='POST',
        path='/api/v1/application_sessions',
        data=json.dumps(data))
    assert response.status_code == 200


def test_user_create_application_session_application_disabled(rmaker: RequestMaker, pri_data: PrimaryData):
    response = rmaker.make_authenticated_user_request(
        method='POST',
        path='/api/v1/application_sessions',
        data=json.dumps({'application_id': pri_data.known_application_id_disabled}),
    )
    assert response.status_code == 404


def test_user_create_application_session_application_deleted(rmaker: RequestMaker, pri_data: PrimaryData):
    response = rmaker.make_authenticated_user_request(
        method='POST',
        path='/api/v1/application_sessions',
        data=json.dumps({'application_id': pri_data.known_application_id_deleted}),
    )
    assert response.status_code == 404


def test_user_create_application_session_application_archived(rmaker: RequestMaker, pri_data: PrimaryData):
    response = rmaker.make_authenticated_user_request(
        method='POST',
        path='/api/v1/application_sessions',
        data=json.dumps({'application_id': pri_data.known_application_id_archived}),
    )
    assert response.status_code == 404


def test_create_application_session_memory_limit(rmaker: RequestMaker, pri_data: PrimaryData):
    # first launch by user-2 should work
    data = {'application_id': pri_data.known_application_id_mem_limit_test_1}
    response = rmaker.make_authenticated_user_2_request(
        method='POST',
        path='/api/v1/application_sessions',
        data=json.dumps(data))
    assert response.status_code == 200

    # next launch by user-2 should fail, because we would be over memory limit
    data = {'application_id': pri_data.known_application_id_mem_limit_test_2}
    response = rmaker.make_authenticated_user_2_request(
        method='POST',
        path='/api/v1/application_sessions',
        data=json.dumps(data))
    assert response.status_code == 409, 'session launch should be rejected'

    # but we should be able to launch a smaller application
    data = {'application_id': pri_data.known_application_id_mem_limit_test_3}
    response = rmaker.make_authenticated_user_2_request(
        method='POST',
        path='/api/v1/application_sessions',
        data=json.dumps(data))
    assert response.status_code == 200

    # even admin cannot launch a session
    data = {'application_id': pri_data.known_application_id_mem_limit_test_2}
    response = rmaker.make_authenticated_admin_request(
        method='POST',
        path='/api/v1/application_sessions',
        data=json.dumps(data))
    assert response.status_code == 409, 'session launch should be rejected'


def test_owner_create_application_session_application_disabled(rmaker: RequestMaker, pri_data: PrimaryData):
    # Use Application in ws2 that is owned by owner2 and has owner1 as user

    # first, disable known_application_id_g2
    resp = rmaker.make_authenticated_workspace_owner2_request(
        path='/api/v1/applications/%s' % pri_data.known_application_id_g2
    )
    data = resp.json
    data['is_enabled'] = False
    put_response = rmaker.make_authenticated_workspace_owner2_request(
        method='PUT',
        path='/api/v1/applications/%s' % pri_data.known_application_id_g2,
        data=json.dumps(data))
    assert put_response.status_code == 200

    # 'owner2' should be able to launch an application session
    response = rmaker.make_authenticated_workspace_owner2_request(
        method='POST',
        path='/api/v1/application_sessions',
        data=json.dumps({'application_id': pri_data.known_application_id_g2}),
    )
    assert response.status_code == 200

    # 'owner' has a user role in this ws2, so this should be denied
    response = rmaker.make_authenticated_workspace_owner_request(
        method='POST',
        path='/api/v1/application_sessions',
        data=json.dumps({'application_id': pri_data.known_application_id_g2}),
    )
    assert response.status_code == 404


def test_get_application_sessions(rmaker: RequestMaker, pri_data: PrimaryData):
    # Anonymous
    response = rmaker.make_request(path='/api/v1/application_sessions')
    assert response.status_code == 401
    # Authenticated
    response = rmaker.make_authenticated_user_request(path='/api/v1/application_sessions')
    assert response.status_code == 200
    assert len(response.json) == 2
    # Workspace Manager (His own session + other sessions from his managed workspaces)
    response = rmaker.make_authenticated_workspace_owner_request(path='/api/v1/application_sessions')
    assert response.status_code == 200
    assert len(response.json) == 3
    # Admin
    response = rmaker.make_authenticated_admin_request(path='/api/v1/application_sessions')
    assert response.status_code == 200
    assert len(response.json) == 4


def test_get_application_session(rmaker: RequestMaker, pri_data: PrimaryData):
    # Anonymous
    response = rmaker.make_request(path='/api/v1/application_sessions/%s' % pri_data.known_application_session_id)
    assert response.status_code == 401

    # Authenticated, someone else's application session
    response = rmaker.make_authenticated_user_request(
        method='GET',
        path='/api/v1/application_sessions/%s' % pri_data.known_application_session_id_4
    )
    assert response.status_code == 404

    # Authenticated
    response = rmaker.make_authenticated_user_request(
        method='GET',
        path='/api/v1/application_sessions/%s' % pri_data.known_application_session_id
    )
    assert response.status_code == 200

    # Admin
    response = rmaker.make_authenticated_admin_request(
        method='GET',
        path='/api/v1/application_sessions/%s' % pri_data.known_application_session_id
    )
    assert response.status_code == 200


def test_patch_application_session(rmaker: RequestMaker, pri_data: PrimaryData):
    # Anonymous
    response = rmaker.make_request(
        method='PATCH',
        path='/api/v1/application_sessions/%s' % pri_data.known_application_session_id,
        data=json.dumps(dict(state='deleting'))
    )
    assert response.status_code == 401

    # Authenticated
    response = rmaker.make_authenticated_user_request(
        method='PATCH',
        path='/api/v1/application_sessions/%s' % pri_data.known_application_session_id,
        data=json.dumps(dict(state='deleting'))
    )
    assert response.status_code == 403

    # Owner
    response = rmaker.make_authenticated_workspace_owner_request(
        method='PATCH',
        path='/api/v1/application_sessions/%s' % pri_data.known_application_session_id,
        data=json.dumps(dict(state='deleting'))
    )
    assert response.status_code == 403

    # Admin, invalid state
    response = rmaker.make_authenticated_admin_request(
        method='PATCH',
        path='/api/v1/application_sessions/%s' % pri_data.known_application_session_id,
        data=json.dumps(dict(state='bogus'))
    )
    assert response.status_code == 422

    # Admin, check that changing state to 'deleted' cleans logs. ApplicationSession 2 with logs.
    assert len(ApplicationSessionLog.query.filter_by(
        application_session_id=pri_data.known_application_session_id_2).all()) == 1
    response = rmaker.make_authenticated_admin_request(
        method='PATCH',
        path='/api/v1/application_sessions/%s' % pri_data.known_application_session_id_2,
        data=json.dumps(dict(state='deleted'))
    )
    assert response.status_code == 200
    assert len(ApplicationSessionLog.query.filter_by(
        application_session_id=pri_data.known_application_session_id_2).all()) == 0


def test_delete_application_session(rmaker: RequestMaker, pri_data: PrimaryData):
    application = Application.query.filter_by(id=pri_data.known_application_id).first()
    user = User.query.filter_by(id=pri_data.known_user_id).first()
    i1 = ApplicationSession(application, user)
    db.session.add(i1)
    db.session.commit()
    # Anonymous
    response = rmaker.make_request(
        method='DELETE',
        path='/api/v1/application_sessions/%s' % i1.id
    )
    assert response.status_code == 401
    # Authenticated User of the application session
    response = rmaker.make_authenticated_user_request(
        method='DELETE',
        path='/api/v1/application_sessions/%s' % i1.id
    )
    assert response.status_code == 202

    i2 = ApplicationSession(application, user)
    db.session.add(i2)
    db.session.commit()
    # Authenticated Workspace Owner of the application session
    response = rmaker.make_authenticated_workspace_owner_request(
        method='DELETE',
        path='/api/v1/application_sessions/%s' % i2.id
    )
    assert response.status_code == 202

    i3 = ApplicationSession(application, user)
    db.session.add(i3)
    db.session.commit()
    # Authenticated Workspace Manager of the application session
    response = rmaker.make_authenticated_workspace_owner2_request(
        method='DELETE',
        path='/api/v1/application_sessions/%s' % i3.id
    )
    assert response.status_code == 202

    i4 = ApplicationSession(application, user)
    db.session.add(i4)
    db.session.commit()
    # Admin
    response = rmaker.make_authenticated_admin_request(
        method='DELETE',
        path='/api/v1/application_sessions/%s' % i4.id
    )
    assert response.status_code == 202

    environment2 = Application.query.filter_by(id=pri_data.known_application_id_g2).first()
    user2 = User.query.filter_by(id=pri_data.known_workspace_owner_id_2).first()
    i5 = ApplicationSession(environment2, user2)
    db.session.add(i5)
    db.session.commit()
    # User is not part of the workspace
    response = rmaker.make_authenticated_user_request(
        method='DELETE',
        path='/api/v1/application_sessions/%s' % i5.id
    )
    assert response.status_code == 404
    # Is just a Normal user of the workspace who didn't spawn the application session
    response = rmaker.make_authenticated_workspace_owner_request(
        method='DELETE',
        path='/api/v1/application_sessions/%s' % i5.id
    )
    assert response.status_code == 403
    # Authenticated Workspace Owner of the workspace
    response = rmaker.make_authenticated_workspace_owner2_request(
        method='DELETE',
        path='/api/v1/application_sessions/%s' % i5.id
    )
    assert response.status_code == 202


def test_application_session_logs(rmaker: RequestMaker, pri_data: PrimaryData):
    epoch_time = time.time()
    log_record = {
        'log_level': 'INFO',
        'log_type': 'provisioning',
        'timestamp': epoch_time,
        'message': 'log testing'
    }
    response_patch = rmaker.make_authenticated_admin_request(
        method='PATCH',
        path='/api/v1/application_sessions/%s/logs' % pri_data.known_application_session_id,
        data=json.dumps({'log_record': log_record})
    )
    assert response_patch.status_code == 200

    response_get = rmaker.make_authenticated_user_request(
        method='GET',
        path='/api/v1/application_sessions/%s/logs' % pri_data.known_application_session_id,
        data=json.dumps({'log_type': 'provisioning'})
    )
    assert response_get.status_code == 200
    assert response_get.json[0]['timestamp'] == epoch_time

    # delete logs as normal user
    response_delete = rmaker.make_authenticated_user_request(
        method='DELETE',
        path='/api/v1/application_sessions/%s/logs' % pri_data.known_application_session_id
    )
    assert response_delete.status_code == 403

    # delete logs as admin
    response_delete = rmaker.make_authenticated_admin_request(
        method='DELETE',
        path='/api/v1/application_sessions/%s/logs' % pri_data.known_application_session_id
    )
    assert response_delete.status_code == 200

    # check that logs are empty
    response_get = rmaker.make_authenticated_user_request(
        method='GET',
        path='/api/v1/application_sessions/%s/logs' % pri_data.known_application_session_id,
        data=json.dumps({'log_type': 'provisioning'})
    )
    assert response_get.status_code == 200
    assert len(response_get.json) == 0

    # test patching running logs - should be replaced, not appended
    log_record['log_type'] = 'running'
    response_patch = rmaker.make_authenticated_admin_request(
        method='PATCH',
        path='/api/v1/application_sessions/%s/logs' % pri_data.known_application_session_id,
        data=json.dumps({'log_record': log_record})
    )
    assert response_patch.status_code == 200
    log_record['message'] = 'patched running logs'
    response_patch = rmaker.make_authenticated_admin_request(
        method='PATCH',
        path='/api/v1/application_sessions/%s/logs' % pri_data.known_application_session_id,
        data=json.dumps({'log_record': log_record})
    )
    assert response_patch.status_code == 200
    response_get = rmaker.make_authenticated_user_request(
        method='GET',
        path='/api/v1/application_sessions/%s/logs' % pri_data.known_application_session_id,
        data=json.dumps({})
    )
    assert response_get.status_code == 200
    assert len(response_get.json) == 1
    assert 'patched running logs' == response_get.json[0]['message']
