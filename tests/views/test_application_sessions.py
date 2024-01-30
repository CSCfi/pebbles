import datetime
import json
import time

from sqlalchemy import select

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

    # but we should be able to launch a smaller application. This also tests that custom memory_gib set in config
    # overrides the base_config memory_gib
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


def test_get_application_session_list_vs_view(rmaker: RequestMaker, pri_data: PrimaryData):
    response = rmaker.make_authenticated_admin_request(path='/api/v1/application_sessions')
    assert response.status_code == 200
    # check that individual application fetch matches the list output
    for s1 in response.json:
        s2 = rmaker.make_authenticated_admin_request(path=f'/api/v1/application_sessions/{s1["id"]}').json
        assert s1 == s2


def test_get_application_sessions_limit(rmaker: RequestMaker, pri_data: PrimaryData):
    # First, test_get_application_sessions() duplicated with additional limit=10 parameter

    # Anonymous
    resp = rmaker.make_request(path='/api/v1/application_sessions?limit=10')
    assert resp.status_code == 401

    # Authenticated
    resp = rmaker.make_authenticated_user_request(path='/api/v1/application_sessions?limit=10')
    assert resp.status_code == 200
    assert len(resp.json) == 2

    # Workspace Manager (His own session + other sessions from his managed workspaces)
    resp = rmaker.make_authenticated_workspace_owner_request(path='/api/v1/application_sessions?limit=10')
    assert resp.status_code == 200
    assert len(resp.json) == 3

    # Admin
    resp = rmaker.make_authenticated_admin_request(path='/api/v1/application_sessions?limit=10')
    assert resp.status_code == 200
    assert len(resp.json) == 4

    # Then, test actual limits

    # simple limit
    resp = rmaker.make_authenticated_admin_request(path='/api/v1/application_sessions?limit=3')
    assert resp.status_code == 200
    assert len(resp.json) == 3

    # setup one highest priority session (to_be_deleted), check that it is returned as the only one
    s2 = db.session.scalar(
        select(ApplicationSession).where(ApplicationSession.id == pri_data.known_application_session_id_2)
    )
    s2.to_be_deleted = True
    db.session.commit()
    resp = rmaker.make_authenticated_admin_request(path='/api/v1/application_sessions?limit=1')
    assert resp.status_code == 200
    assert len(resp.json) == 1
    assert resp.json[0]['id'] == pri_data.known_application_session_id_2

    # setup second high priority session (to_be_deleted), check that both are first
    s1 = db.session.scalar(
        select(ApplicationSession).where(ApplicationSession.id == pri_data.known_application_session_id)
    )
    s1.to_be_deleted = True
    db.session.commit()
    resp = rmaker.make_authenticated_admin_request(path='/api/v1/application_sessions?limit=3')
    assert resp.status_code == 200
    assert len(resp.json) == 3
    assert set([resp.json[0]['id'], resp.json[1]['id']]) == \
           set([pri_data.known_application_session_id, pri_data.known_application_session_id_2])

    # QUEUEING, PROVISIONING, STARTING should come right after to_be_deleted
    s7 = ApplicationSession(
        Application.query.filter_by(id=pri_data.known_application_id).first(),
        User.query.filter_by(ext_id="user@example.org").first())
    s7.name = 'pb-s7'
    s7.provisioned_at = datetime.datetime.strptime("2023-12-19T13:00:00", "%Y-%m-%dT%H:%M:%S")
    db.session.add(s7)
    for state in [
        ApplicationSession.STATE_QUEUEING, ApplicationSession.STATE_PROVISIONING, ApplicationSession.STATE_STARTING
    ]:
        s7.state = state
        db.session.commit()
        resp = rmaker.make_authenticated_admin_request(path='/api/v1/application_sessions?limit=5')
        assert resp.status_code == 200
        assert len(resp.json) == 5
        assert set([resp.json[0]['id'], resp.json[1]['id']]) == \
               set([pri_data.known_application_session_id, pri_data.known_application_session_id_2])
        assert resp.json[2]['id'] == s7.id, f'state {state} did not get sorted as second priority'


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


def test_patch_application_session_state(rmaker: RequestMaker, pri_data: PrimaryData):
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


def test_patch_application_session_log_fetch_pending(rmaker: RequestMaker, pri_data: PrimaryData):
    # Anonymous
    response = rmaker.make_request(
        method='PATCH',
        path='/api/v1/application_sessions/%s' % pri_data.known_application_session_id,
        data=json.dumps(dict(log_fetch_pending=True))
    )
    assert response.status_code == 401

    # Authenticated
    response = rmaker.make_authenticated_user_request(
        method='PATCH',
        path='/api/v1/application_sessions/%s' % pri_data.known_application_session_id,
        data=json.dumps(dict(log_fetch_pending=True))
    )
    assert response.status_code == 403

    # Owner, but not manager in this workspace
    response = rmaker.make_authenticated_workspace_owner_request(
        method='PATCH',
        path='/api/v1/application_sessions/%s' % pri_data.known_application_session_id_5,
        data=json.dumps(dict(log_fetch_pending=True))
    )
    assert response.status_code == 404

    # owner2 is manager in this workspace
    response = rmaker.make_authenticated_workspace_owner2_request(
        method='PATCH',
        path='/api/v1/application_sessions/%s' % pri_data.known_application_session_id,
        data=json.dumps(dict(log_fetch_pending=True))
    )
    assert response.status_code == 200

    # Owner
    response = rmaker.make_authenticated_workspace_owner_request(
        method='PATCH',
        path='/api/v1/application_sessions/%s' % pri_data.known_application_session_id,
        data=json.dumps(dict(log_fetch_pending=True))
    )
    assert response.status_code == 200

    # Admin
    response = rmaker.make_authenticated_admin_request(
        method='PATCH',
        path='/api/v1/application_sessions/%s' % pri_data.known_application_session_id,
        data=json.dumps(dict(log_fetch_pending=True))
    )
    assert response.status_code == 200


def test_delete_application_session(rmaker: RequestMaker, pri_data: PrimaryData):
    application = Application.query.filter_by(id=pri_data.known_application_id).first()
    user = User.query.filter_by(id=pri_data.known_user_id).first()
    s1 = ApplicationSession(application, user)
    db.session.add(s1)
    db.session.commit()
    # Anonymous
    response = rmaker.make_request(
        method='DELETE',
        path='/api/v1/application_sessions/%s' % s1.id
    )
    assert response.status_code == 401
    # Authenticated User of the application session
    response = rmaker.make_authenticated_user_request(
        method='DELETE',
        path='/api/v1/application_sessions/%s' % s1.id
    )
    assert response.status_code == 202

    s2 = ApplicationSession(application, user)
    db.session.add(s2)
    db.session.commit()
    # Authenticated Workspace Owner of the application session
    response = rmaker.make_authenticated_workspace_owner_request(
        method='DELETE',
        path='/api/v1/application_sessions/%s' % s2.id
    )
    assert response.status_code == 202

    s3 = ApplicationSession(application, user)
    db.session.add(s3)
    db.session.commit()
    # Authenticated Workspace Manager of the application session
    response = rmaker.make_authenticated_workspace_owner2_request(
        method='DELETE',
        path='/api/v1/application_sessions/%s' % s3.id
    )
    assert response.status_code == 202

    s4 = ApplicationSession(application, user)
    db.session.add(s4)
    db.session.commit()
    # Admin
    response = rmaker.make_authenticated_admin_request(
        method='DELETE',
        path='/api/v1/application_sessions/%s' % s4.id
    )
    assert response.status_code == 202

    application2 = Application.query.filter_by(id=pri_data.known_application_id_g2).first()
    user2 = User.query.filter_by(id=pri_data.known_workspace_owner_id_2).first()
    s5 = ApplicationSession(application2, user2)
    db.session.add(s5)
    db.session.commit()
    # User is not part of the workspace
    response = rmaker.make_authenticated_user_request(
        method='DELETE',
        path='/api/v1/application_sessions/%s' % s5.id
    )
    assert response.status_code == 404
    # Owner 1 is just a normal user in this workspace who didn't spawn the application session
    response = rmaker.make_authenticated_workspace_owner_request(
        method='DELETE',
        path='/api/v1/application_sessions/%s' % s5.id
    )
    assert response.status_code == 404
    # Authenticated Workspace Owner of the workspace
    response = rmaker.make_authenticated_workspace_owner2_request(
        method='DELETE',
        path='/api/v1/application_sessions/%s' % s5.id
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


def test_application_session_provisioning_config(rmaker: RequestMaker, pri_data: PrimaryData):
    # Authenticated User, should not see provisioning_config
    response = rmaker.make_authenticated_user_request(
        method='GET',
        path='/api/v1/application_sessions/%s' % pri_data.known_application_session_id)
    assert "provisioning_config" not in response.json

    # Authenticated Owner, should not see provisioning_config
    response = rmaker.make_authenticated_workspace_owner_request(
        method='GET',
        path='/api/v1/application_sessions/%s' % pri_data.known_application_session_id)
    assert "provisioning_config" not in response.json

    # Authenticated Admin, should see provisioning_config
    response = rmaker.make_authenticated_admin_request(
        method='GET',
        path='/api/v1/application_sessions/%s' % pri_data.known_application_session_id)
    assert "provisioning_config" in response.json


def test_application_session_info(rmaker: RequestMaker, pri_data: PrimaryData):
    # Authenticated User
    response = rmaker.make_authenticated_user_request(
        method='GET',
        path='/api/v1/application_sessions/%s' % pri_data.known_application_session_id)
    assert response.json.get('info') == dict(container_image='registry.example.org/pebbles/image1')

    # Authenticated Owner
    response = rmaker.make_authenticated_workspace_owner_request(
        method='GET',
        path='/api/v1/application_sessions/%s' % pri_data.known_application_session_id)
    assert response.json.get('info') == dict(container_image='registry.example.org/pebbles/image1')

    # Authenticated Admin
    response = rmaker.make_authenticated_admin_request(
        method='GET',
        path='/api/v1/application_sessions/%s' % pri_data.known_application_session_id)
    assert response.json.get('info') == dict(container_image='registry.example.org/pebbles/image1')
