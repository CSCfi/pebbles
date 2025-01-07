import json
import time
from datetime import timezone, datetime

from dateutil.relativedelta import relativedelta
from sqlalchemy import select

from pebbles.forms import WS_TYPE_LONG_RUNNING, WS_TYPE_FIXED_TIME
from pebbles.models import PEBBLES_TAINT_KEY, Task
from pebbles.models import User, Workspace, WorkspaceMembership
from pebbles.models import db
from tests.conftest import PrimaryData, RequestMaker


def test_get_workspaces(rmaker: RequestMaker, pri_data: PrimaryData):
    # Anonymous
    response = rmaker.make_request(path='/api/v1/workspaces')
    assert response.status_code == 401

    # Authenticated User
    response = rmaker.make_authenticated_user_request(path='/api/v1/workspaces')
    assert response.status_code == 200
    assert len(response.json) == 1

    # Authenticated User: get one
    response = rmaker.make_authenticated_user_request(path='/api/v1/workspaces/%s' % pri_data.known_workspace_id)
    assert response.status_code == 200

    # Authenticated Workspace Owner
    response = rmaker.make_authenticated_workspace_owner_request(path='/api/v1/workspaces')
    assert response.status_code == 200
    assert len(response.json) == 2

    # Authenticated Workspace Owner: get one
    response = rmaker.make_authenticated_workspace_owner_request(path='/api/v1/workspaces/%s' %
                                                                      pri_data.known_workspace_id)
    assert response.status_code == 200

    # Admin
    response = rmaker.make_authenticated_admin_request(path='/api/v1/workspaces')
    assert response.status_code == 200
    assert len(response.json) == 8

    # Admin: get one
    response = rmaker.make_authenticated_admin_request(path='/api/v1/workspaces/%s' % pri_data.known_workspace_id)
    assert response.status_code == 200

    # Admin: filter based on workspace membership expiry policy
    response = rmaker.make_authenticated_admin_request(
        path='/api/v1/workspaces?membership_expiry_policy_kind=%s' % Workspace.MEP_ACTIVITY_TIMEOUT)
    assert response.status_code == 200
    assert len(response.json) == 1
    response = rmaker.make_authenticated_admin_request(
        path='/api/v1/workspaces?membership_expiry_policy_kind=%s' % Workspace.MEP_PERSISTENT)
    assert response.status_code == 200
    assert len(response.json) == 7
    response = rmaker.make_authenticated_admin_request(
        path='/api/v1/workspaces?membership_expiry_policy_kind=%s' % 'does_not_exist')
    assert response.status_code == 200
    assert len(response.json) == 0


def test_get_workspace_view(rmaker: RequestMaker, pri_data: PrimaryData):
    # Anonymous
    response = rmaker.make_request(path='/api/v1/workspaces/%s' % pri_data.known_workspace_id)
    assert response.status_code == 401

    # Authenticated User, positive
    response = rmaker.make_authenticated_user_request(path='/api/v1/workspaces/%s' % pri_data.known_workspace_id)
    assert response.status_code == 200

    # Authenticated User, who does not have access to workspace 2
    response = rmaker.make_authenticated_user_request(path='/api/v1/workspaces/%s' % pri_data.known_workspace_id_2)
    assert response.status_code == 403

    # Authenticated Workspace Owner
    response = rmaker.make_authenticated_workspace_owner_request(path='/api/v1/workspaces/%s' %
                                                                      pri_data.known_workspace_id)
    assert response.status_code == 200

    # Admin
    response = rmaker.make_authenticated_admin_request(path='/api/v1/workspaces/%s' % pri_data.known_workspace_id)
    assert response.status_code == 200


def test_get_workspace_list_vs_view(rmaker: RequestMaker, pri_data: PrimaryData):
    # Authenticated User, positive
    response = rmaker.make_authenticated_user_request(path='/api/v1/workspaces')
    assert response.status_code == 200
    # check that individual application fetch matches the list output
    for w1 in response.json:
        w2 = rmaker.make_authenticated_user_request(path=f'/api/v1/workspaces/{w1["id"]}').json
        assert w1 == w2

    # Authenticated Workspace Owner
    response = rmaker.make_authenticated_workspace_owner_request(path='/api/v1/workspaces')
    assert response.status_code == 200
    # check that individual application fetch matches the list output
    for w1 in response.json:
        w2 = rmaker.make_authenticated_workspace_owner_request(path=f'/api/v1/workspaces/{w1["id"]}').json
        assert w1 == w2

    # Admin
    response = rmaker.make_authenticated_admin_request(path='/api/v1/workspaces')
    assert response.status_code == 200
    # check that individual application fetch matches the list output
    for w1 in response.json:
        w2 = rmaker.make_authenticated_admin_request(path=f'/api/v1/workspaces/{w1["id"]}').json
        assert w1 == w2


def test_workspace_contact(rmaker: RequestMaker, pri_data: PrimaryData):
    data = {
        'name': 'TestWorkspace',
        'description': 'Workspace Details',
        'contact': 'email@email.com',
    }

    resp = rmaker.make_authenticated_workspace_owner_request(
        method='POST',
        path='/api/v1/workspaces',
        data=json.dumps(data))
    assert resp.status_code == 200
    assert resp.json['contact'] == 'email@email.com'


def test_create_workspace(rmaker: RequestMaker, pri_data: PrimaryData):
    data = {
        'name': 'TestWorkspace',
        'description': 'Workspace Details',
        'workspace_type': WS_TYPE_FIXED_TIME,
        'expiry_ts': int((datetime.now() + relativedelta(months=+3)).timestamp()),
    }
    data_2 = {
        'name': 'TestWorkspace2',
        'description': 'Workspace Details',
    }
    data_3 = {
        'name': 'TestWorkspace',
        'description': 'Workspace Details',
        'workspace_type': WS_TYPE_LONG_RUNNING,
        'user_config': {
        },
    }
    data_4 = {
        'name': 'TestWorkspace4',
        'description': 'Workspace Details',
    }

    # Anonymous
    resp = rmaker.make_request(
        method='POST',
        path='/api/v1/workspaces',
        data=json.dumps(data))
    assert resp.status_code == 401
    # Authenticated User
    resp = rmaker.make_authenticated_user_request(
        method='POST',
        path='/api/v1/workspaces',
        data=json.dumps(data))
    assert resp.status_code == 403

    # increase workspace quota to 4 for owner 1
    resp = rmaker.make_authenticated_admin_request(
        method='PATCH',
        path='/api/v1/users/%s' % pri_data.known_workspace_owner_id,
        data=json.dumps(dict(workspace_quota=4))
    )
    assert resp.status_code == 200

    # Workspace Owner
    resp = rmaker.make_authenticated_workspace_owner_request(
        method='POST',
        path='/api/v1/workspaces',
        data=json.dumps(data))
    assert resp.status_code == 200
    # also check expiry time
    assert int(resp.json['expiry_ts']) == data['expiry_ts']
    # and membership expiry policy kind
    assert resp.json['membership_expiry_policy']['kind'] == Workspace.MEP_PERSISTENT

    resp = rmaker.make_authenticated_workspace_owner_request(
        method='POST',
        path='/api/v1/workspaces',
        data=json.dumps(data_2))
    assert resp.status_code == 200

    resp = rmaker.make_authenticated_workspace_owner_request(
        method='POST',
        path='/api/v1/workspaces',
        data=json.dumps(data_3))
    assert resp.status_code == 200
    assert resp.json['membership_expiry_policy']['kind'] == Workspace.MEP_ACTIVITY_TIMEOUT
    assert resp.json['membership_expiry_policy']['timeout_days'] == 90
    assert resp.json['config']['allow_expiry_extension']
    assert db.session.scalar(
        select(Workspace).where(Workspace.id == resp.json['id'])
    ).config['allow_expiry_extension']

    resp = rmaker.make_authenticated_workspace_owner_request(
        method='POST',
        path='/api/v1/workspaces',
        data=json.dumps(data_4))
    assert resp.status_code == 422

    # Admin
    resp = rmaker.make_authenticated_admin_request(
        method='POST',
        path='/api/v1/workspaces',
        data=json.dumps(data))
    assert resp.status_code == 200


def test_create_workspace_invalid_data(rmaker: RequestMaker, pri_data: PrimaryData):
    # Invalid name, description, workspace_type
    invalid_data = [
        dict(name='', description='Workspace Details'),
        dict(name='test', description='Workspace Details', workspace_type='foo'),
    ]
    for inv in invalid_data:
        invalid_response = rmaker.make_authenticated_workspace_owner_request(
            method='POST',
            path='/api/v1/workspaces',
            data=json.dumps(inv))
        assert invalid_response.status_code == 422

    # Try to create system level workspaces
    invalid_system_data = [
        dict(name='System.Workspace', description='Workspace Details', ),
        dict(name='system workspace', description='Workspace Details', ),
        dict(name='systematic progress', description='Workspace Details', )
    ]
    for inv in invalid_system_data:
        invalid_response = rmaker.make_authenticated_workspace_owner_request(
            method='POST',
            path='/api/v1/workspaces',
            data=json.dumps(inv))
        assert invalid_response.status_code == 422

        invalid_response = rmaker.make_authenticated_admin_request(
            method='POST',
            path='/api/v1/workspaces',
            data=json.dumps(inv))
        assert invalid_response.status_code == 422

    invalid_expiry_tss = [
        0,
        -1,
        "foo",
        int(datetime.now(timezone.utc).timestamp()),
        int((datetime.now(timezone.utc) + relativedelta(months=+8)).timestamp()),
    ]

    for invalid_expiry_ts in invalid_expiry_tss:
        invalid_response = rmaker.make_authenticated_workspace_owner_request(
            method='POST',
            path='/api/v1/workspaces',
            data=json.dumps(dict(
                name='workspace',
                description='descr',
                expiry_ts=invalid_expiry_ts,
            ))
        )
        assert invalid_response.status_code == 422


def test_modify_workspace(rmaker: RequestMaker, pri_data: PrimaryData):
    w = db.session.scalar(select(Workspace).where(Workspace.id == pri_data.known_workspace_id))
    db.session.expunge(w)

    # Anonymous
    resp = rmaker.make_request(
        method='PUT',
        path='/api/v1/workspaces/%s' % pri_data.known_workspace_id,
        data=json.dumps(dict(name='namey name', description='descy desc')))
    assert resp.status_code == 401

    # Authenticated User
    resp = rmaker.make_authenticated_user_request(
        method='PUT',
        path='/api/v1/workspaces/%s' % pri_data.known_workspace_id,
        data=json.dumps(dict(name='namey name', description='descy desc')))
    assert resp.status_code == 403

    # Another owner, manager in this workspace
    resp = rmaker.make_authenticated_workspace_owner2_request(
        method='PUT',
        path='/api/v1/workspaces/%s' % pri_data.known_workspace_id,
        data=json.dumps(dict(name='namey name', description='descy desc')))
    assert resp.status_code == 403

    # Non-existing workspace
    resp = rmaker.make_authenticated_workspace_owner_request(
        method='PUT',
        path='/api/v1/workspaces/%s' % 'foobar',
        data=json.dumps(dict(name='namey name', description='descy desc')))
    assert resp.status_code == 404

    # update name and description
    resp = rmaker.make_authenticated_workspace_owner_request(
        method='PUT',
        path='/api/v1/workspaces/%s' % pri_data.known_workspace_id,
        data=json.dumps(dict(name='namey name', description='descy desc',
                             contact='email@email.com')))
    assert resp.status_code == 200
    assert resp.json.get('name') == 'namey name'
    assert resp.json.get('description') == 'descy desc'
    assert resp.json.get('contact') == 'email@email.com'

    # update only name
    resp = rmaker.make_authenticated_workspace_owner_request(
        method='PUT',
        path='/api/v1/workspaces/%s' % pri_data.known_workspace_id,
        data=json.dumps(dict(name='test1')))
    assert resp.status_code == 200
    assert resp.json.get('name') == 'test1'
    assert resp.json.get('description') == 'descy desc'
    assert resp.json.get('contact') == 'email@email.com'


def test_workspace_returns(rmaker: RequestMaker, pri_data: PrimaryData):
    # Admin: test get returns owner_ext_id right
    get_response = rmaker.make_authenticated_admin_request(path='/api/v1/workspaces/%s' % pri_data.known_workspace_id)
    assert get_response.status_code == 200
    assert get_response.json['owner_ext_id'] == "workspace_owner@example.org"

    # Admin: test PUT returns owner_ext_id right
    response = rmaker.make_authenticated_admin_request(
        method='PUT',
        path='/api/v1/workspaces/%s' % pri_data.known_workspace_id,
        data=json.dumps(dict(name='test1')))
    assert response.status_code == 200
    assert response.json['owner_ext_id'] == get_response.json['owner_ext_id']

    # Admin: test PATCH returns owner_ext_id right
    response = rmaker.make_authenticated_admin_request(
        method='PATCH',
        path='/api/v1/workspaces/%s' % pri_data.known_workspace_id,
        data=json.dumps(dict(status='deleted'))
    )
    assert response.status_code == 200
    assert response.json['owner_ext_id'] == get_response.json['owner_ext_id']

    # Admin: test DELETE returns owner_ext_id right
    response = rmaker.make_authenticated_admin_request(
        method='DELETE',
        path='/api/v1/workspaces/%s' % pri_data.known_workspace_id_2
    )
    assert response.status_code == 200
    # Test with ws2, ws1 got deleted
    assert response.json['owner_ext_id'] == "workspace_owner2@example.org"


def test_modify_workspace_expiry_date(rmaker: RequestMaker, pri_data: PrimaryData):
    # try to modify expiry date for workspace that does not have 'allow_expiry_extension' set
    resp = rmaker.make_authenticated_workspace_owner_request(
        method='PUT',
        path='/api/v1/workspaces/%s' % pri_data.known_workspace_id,
        data=json.dumps(dict(
            name='test1',
            expiry_ts=int(time.time()) + 86400 * 365
        ))
    )
    assert resp.status_code == 422

    w = db.session.scalar(select(Workspace).where(Workspace.id == pri_data.known_workspace_id))
    w.config |= dict(allow_expiry_extension=True)
    db.session.commit()
    new_expiry_ts = int(time.time()) + 86400 * 365
    resp = rmaker.make_authenticated_workspace_owner_request(
        method='PUT',
        path='/api/v1/workspaces/%s' % pri_data.known_workspace_id,
        data=json.dumps(dict(
            name='test1',
            expiry_ts=new_expiry_ts
        ))
    )
    assert resp.status_code == 200
    assert resp.json.get('expiry_ts') == new_expiry_ts

    invalid_expiry_dates = [
        -1,
        int(time.time() - 10),
        int(time.time() + 86400 * 31 * 14),
    ]
    for invalid_expiry_date in invalid_expiry_dates:
        resp = rmaker.make_authenticated_workspace_owner_request(
            method='PUT',
            path='/api/v1/workspaces/%s' % pri_data.known_workspace_id,
            data=json.dumps(dict(expiry_ts=invalid_expiry_date))
        )
        assert resp.status_code == 422


def test_modify_workspace_rename_to_system(rmaker: RequestMaker, pri_data: PrimaryData):
    invalid_data_system = dict(name='System.TestWorkspaceModify', description='Cannot rename to System.*')

    # should not be able to rename to System.*, even as an admin
    resp = rmaker.make_authenticated_workspace_owner_request(
        method='PUT',
        path='/api/v1/workspaces/%s' % pri_data.known_workspace_id,
        data=json.dumps(invalid_data_system))
    assert resp.status_code == 422
    resp = rmaker.make_authenticated_admin_request(
        method='PUT',
        path='/api/v1/workspaces/%s' % pri_data.known_workspace_id,
        data=json.dumps(invalid_data_system))
    assert resp.status_code == 422


def test_modify_workspace_invalid_data(rmaker: RequestMaker, pri_data: PrimaryData):
    invalid_data = [
        dict(name='x' * 65, description='asdfasdfasdfasdf'),
        dict(expiry_ts='foo'),
    ]

    for data in invalid_data:
        resp = rmaker.make_authenticated_workspace_owner_request(
            method='PUT',
            path='/api/v1/workspaces/%s' % pri_data.known_workspace_id,
            data=json.dumps(data))
        assert resp.status_code == 422
        resp = rmaker.make_authenticated_admin_request(
            method='PUT',
            path='/api/v1/workspaces/%s' % pri_data.known_workspace_id,
            data=json.dumps(data))
        assert resp.status_code == 422


def test_archive_workspace(rmaker: RequestMaker, pri_data: PrimaryData):
    # Anonymous
    response = rmaker.make_request(
        method='PATCH',
        data=dict(status=Workspace.STATUS_ARCHIVED),
        path='/api/v1/workspaces/%s' % pri_data.known_workspace_id
    )
    assert response.status_code == 401
    # Authenticated
    response = rmaker.make_authenticated_user_request(
        method='PATCH',
        data=json.dumps(dict(status=Workspace.STATUS_ARCHIVED)),
        path='/api/v1/workspaces/%s' % pri_data.known_workspace_id
    )
    assert response.status_code == 403
    # Owner should be able to archive
    response = rmaker.make_authenticated_workspace_owner_request(
        method='PATCH',
        data=json.dumps(dict(status=Workspace.STATUS_ARCHIVED)),
        path='/api/v1/workspaces/%s' % pri_data.known_workspace_id
    )
    assert response.status_code == 200
    workspace = Workspace.query.filter_by(id=pri_data.known_workspace_id).first()
    assert Workspace.STATUS_ARCHIVED == workspace.status

    # Even admin cannot archive System.default
    invalid_response = rmaker.make_authenticated_admin_request(
        method='PATCH',
        data=json.dumps(dict(status=Workspace.STATUS_ARCHIVED)),
        path='/api/v1/workspaces/%s' % pri_data.system_default_workspace_id
    )
    assert invalid_response.status_code == 422  # Cannot archive default system workspace
    # Admin
    response = rmaker.make_authenticated_admin_request(
        method='PATCH',
        data=json.dumps(dict(status=Workspace.STATUS_ARCHIVED)),
        path='/api/v1/workspaces/%s' % pri_data.known_workspace_id_2
    )
    assert response.status_code == 200
    workspace = Workspace.query.filter_by(id=pri_data.known_workspace_id_2).first()
    assert Workspace.STATUS_ARCHIVED == workspace.status


def test_delete_workspace(rmaker: RequestMaker, pri_data: PrimaryData):
    owner_1 = User.query.filter_by(id=pri_data.known_workspace_owner_id).first()
    name = 'WorkspaceToBeDeleted'
    ws = Workspace(name)
    ws.owner_id = owner_1.id
    ws.memberships.append(WorkspaceMembership(user=owner_1, is_manager=True, is_owner=True))
    db.session.add(ws)
    db.session.commit()

    # Anonymous
    response = rmaker.make_request(
        method='DELETE',
        path='/api/v1/workspaces/%s' % ws.id
    )
    assert response.status_code == 401

    # Authenticated
    response = rmaker.make_authenticated_user_request(
        method='DELETE',
        path='/api/v1/workspaces/%s' % ws.id
    )
    assert response.status_code == 403

    # Owner, but not the owner of the workspace
    response = rmaker.make_authenticated_workspace_owner_request(
        method='DELETE',
        path='/api/v1/workspaces/%s' % pri_data.known_workspace_id_3
    )
    assert response.status_code == 403

    # Admin
    invalid_response = rmaker.make_authenticated_admin_request(
        method='DELETE',
        path='/api/v1/workspaces/%s' % pri_data.system_default_workspace_id
    )
    assert invalid_response.status_code == 422  # Cannot delete default system workspace
    response = rmaker.make_authenticated_admin_request(
        method='DELETE',
        path='/api/v1/workspaces/%s' % ws.id
    )
    assert response.status_code == 200
    workspace = Workspace.query.filter_by(id=ws.id).first()
    assert Workspace.STATUS_DELETED == workspace.status

    # owner of the workspace with application sessions, check that application sessions are set to be deleted as well
    response = rmaker.make_authenticated_workspace_owner_request(
        method='DELETE',
        path='/api/v1/workspaces/%s' % pri_data.known_workspace_id
    )
    assert response.status_code == 200
    for application in Workspace.query.filter_by(id=pri_data.known_workspace_id).first().applications:
        for application_session in application.application_sessions:
            assert application_session.to_be_deleted


def test_join_workspace(rmaker: RequestMaker, pri_data: PrimaryData):
    # Anonymous
    response = rmaker.make_request(
        method='PUT',
        path='/api/v1/join_workspace/%s' % pri_data.known_workspace_join_id)
    assert response.status_code == 401
    # Authenticated User
    response = rmaker.make_authenticated_user_request(
        method='PUT',
        path='/api/v1/join_workspace/%s' % pri_data.known_workspace_join_id)
    assert response.status_code == 200
    # Workspace Owner
    response = rmaker.make_authenticated_workspace_owner_request(
        method='PUT',
        path='/api/v1/join_workspace/%s' % pri_data.known_workspace_join_id)
    assert response.status_code == 200


def test_join_workspace_taint(rmaker: RequestMaker, pri_data: PrimaryData):
    # workspace for low trust tainted users
    ws = Workspace('Low Trust Workspace')
    db.session.add(ws)

    # user with low trust taint
    u = User.query.filter_by(ext_id=pri_data.known_user_ext_id).first()
    u.annotations = [dict(key=PEBBLES_TAINT_KEY, value='low_trust')]
    db.session.commit()

    # no tolerations, user cannot join
    response = rmaker.make_authenticated_user_request(
        method='PUT',
        path='/api/v1/join_workspace/%s' % ws.join_code)
    assert response.status_code == 422

    # workspace tolerates 'low_trust' taint, joining should work
    ws.membership_join_policy = dict(tolerations=['low_trust'])
    db.session.commit()
    response = rmaker.make_authenticated_user_request(
        method='PUT',
        path='/api/v1/join_workspace/%s' % ws.join_code)
    assert response.status_code == 200

    # delete membership, assign two taints and a different annotation
    WorkspaceMembership.query.filter_by(user_id=u.id, workspace_id=ws.id).delete()
    u.annotations = [
        dict(key=PEBBLES_TAINT_KEY, value='low_trust'),
        dict(key=PEBBLES_TAINT_KEY, value='another_taint'),
        dict(key='some_key', value='some_value'),
    ]
    db.session.commit()

    # second taint is not tolerated
    response = rmaker.make_authenticated_user_request(
        method='PUT',
        path='/api/v1/join_workspace/%s' % ws.join_code)
    assert response.status_code == 422

    # both taints tolerated
    ws.membership_join_policy = dict(tolerations=['low_trust', 'another_taint'])
    db.session.commit()
    response = rmaker.make_authenticated_user_request(
        method='PUT',
        path='/api/v1/join_workspace/%s' % ws.join_code)
    assert response.status_code == 200


def test_join_workspace_invalid(rmaker: RequestMaker, pri_data: PrimaryData):
    ws = Workspace('InvalidTestWorkspace')
    ws.owner_id = pri_data.known_workspace_owner_id
    u = User.query.filter_by(id=pri_data.known_user_id).first()
    wsu_obj = WorkspaceMembership()
    wsu_obj.user = u
    wsu_obj.workspace = ws

    ws.memberships.append(wsu_obj)
    db.session.add(ws)
    db.session.commit()
    # Authenticated User
    invalid_response = rmaker.make_authenticated_user_request(
        method='PUT',
        path='/api/v1/join_workspace/')
    assert invalid_response.status_code == 405  # Not allowed without joining code

    # Authenticated User Bogus Code
    invalid_response = rmaker.make_authenticated_user_request(
        method='PUT',
        path='/api/v1/join_workspace/%s' % 'bogusx10')
    assert invalid_response.status_code == 422
    # Workspace Owner Bogus Code
    invalid_response = rmaker.make_authenticated_workspace_owner_request(
        method='PUT',
        path='/api/v1/join_workspace/%s' % 'bogusx10')
    assert invalid_response.status_code == 422
    # Authenticated User - Trying to Join the same workspace again
    response = rmaker.make_authenticated_user_request(
        method='PUT',
        path='/api/v1/join_workspace/%s' % ws.join_code)
    assert response.status_code == 422


def test_join_workspace_banned_user(rmaker: RequestMaker, pri_data: PrimaryData):
    # Authenticated User
    banned_response = rmaker.make_authenticated_user_request(
        method='PUT',
        path='/api/v1/join_workspace/%s' % pri_data.known_banned_workspace_join_id)
    assert banned_response.status_code == 403

    # Authenticated Workspace Owner
    banned_response = rmaker.make_authenticated_workspace_owner_request(
        method='PUT',
        path='/api/v1/join_workspace/%s' % pri_data.known_banned_workspace_join_id)
    assert banned_response.status_code == 403


def test_exit_workspace(rmaker: RequestMaker, pri_data: PrimaryData):
    ws = Workspace('TestWorkspaceExit')
    ws.owner_id = pri_data.known_workspace_owner_id_2
    u = User.query.filter_by(id=pri_data.known_user_id).first()
    wsu_obj = WorkspaceMembership(workspace=ws, user=u)
    db.session.add(wsu_obj)
    ws.memberships.append(wsu_obj)
    u_extra = User.query.filter_by(id=pri_data.known_workspace_owner_id).first()  # extra user
    wsu_extra_obj = WorkspaceMembership(workspace=ws, user=u_extra)
    db.session.add(wsu_extra_obj)
    ws.memberships.append(wsu_extra_obj)

    db.session.add(ws)
    db.session.commit()
    # Anonymous
    response = rmaker.make_request(
        method='PUT',
        path='/api/v1/workspaces/%s/exit' % ws.id)
    assert response.status_code == 401
    # Authenticated User of the workspace
    response = rmaker.make_authenticated_user_request(
        method='PUT',
        path='/api/v1/workspaces/%s/exit' % ws.id)
    assert response.status_code == 200
    # self.assertEqual(len(g.users.all()), 1)
    # Workspace Owner who is just a user of the workspace
    response = rmaker.make_authenticated_workspace_owner_request(
        method='PUT',
        path='/api/v1/workspaces/%s/exit' % ws.id)
    assert response.status_code == 200
    # self.assertEqual(len(g.users.all()), 0)


def test_exit_workspace_invalid(rmaker: RequestMaker, pri_data: PrimaryData):
    ws = Workspace('InvalidTestWorkspaceExit')
    u = User.query.filter_by(id=pri_data.known_workspace_owner_id).first()
    wsu_obj = WorkspaceMembership(workspace=ws, user=u, is_manager=True, is_owner=True)
    ws.memberships.append(wsu_obj)
    db.session.add(ws)
    db.session.commit()
    # Authenticated User
    invalid_response = rmaker.make_authenticated_user_request(
        method='PUT',
        path='/api/v1/workspaces/exit/')
    assert invalid_response.status_code == 405  # can't put to workspaces
    # Authenticated User Bogus workspace id
    invalid_response = rmaker.make_authenticated_user_request(
        method='PUT',
        path='/api/v1/workspaces/%s/exit' % 'bogusx10')
    assert invalid_response.status_code == 404
    # Workspace Owner Bogus workspace id
    invalid_response = rmaker.make_authenticated_workspace_owner_request(
        method='PUT',
        path='/api/v1/workspaces/%s/exit' % 'bogusx10')
    assert invalid_response.status_code == 404
    # Authenticated User - Trying to exit a workspace without
    response = rmaker.make_authenticated_user_request(
        method='PUT',
        path='/api/v1/workspaces/%s/exit' % ws.id)
    assert response.status_code == 403
    # Workspace Owner of the workspace
    response = rmaker.make_authenticated_workspace_owner_request(
        method='PUT',
        path='/api/v1/workspaces/%s/exit' % ws.id)
    assert response.status_code == 422  # owner of the workspace cannot exit the workspace


def test_get_workspace_members(rmaker: RequestMaker, pri_data: PrimaryData):
    # Anonymous
    response = rmaker.make_request(
        method='GET',
        path='/api/v1/workspaces/%s/members' % pri_data.known_workspace_id
    )
    assert response.status_code == 401

    # Authenticated User, not a manager
    response = rmaker.make_authenticated_user_request(
        method='GET',
        path='/api/v1/workspaces/%s/members' % pri_data.known_workspace_id)
    assert response.status_code == 403

    response = rmaker.make_authenticated_user_request(
        method='GET',
        path='/api/v1/workspaces/%s/members?member_count=true' % pri_data.known_workspace_id)
    assert response.status_code == 403

    # Authenticated Workspace Owner , who does not own the workspace
    response = rmaker.make_authenticated_workspace_owner_request(
        method='GET',
        path='/api/v1/workspaces/%s/members' % pri_data.known_workspace_id_2,
        data=json.dumps({})
    )
    assert response.status_code == 403

    response = rmaker.make_authenticated_workspace_owner_request(
        method='GET',
        path='/api/v1/workspaces/%s/members?member_count=true' % pri_data.known_workspace_id_2,
        data=json.dumps({})
    )
    assert response.status_code == 403

    # Authenticated Workspace Owner (owners are managers, too)
    response = rmaker.make_authenticated_workspace_owner_request(
        method='GET',
        path='/api/v1/workspaces/%s/members' % pri_data.known_workspace_id,
        data=json.dumps({})
    )
    assert response.status_code == 200
    # 1 normal user + 1 manager + 1 workspace owner
    assert len([
        member for member in response.json
        if member['user_id'] == pri_data.known_workspace_owner_id and member['is_owner']]) == 1
    assert len([member for member in response.json if member['is_manager']]) == 2
    assert len([member for member in response.json if not (member['is_manager'] or member['is_owner'])]) == 2
    assert len([member for member in response.json if member['is_banned']]) == 0

    response = rmaker.make_authenticated_workspace_owner_request(
        method='GET',
        path='/api/v1/workspaces/%s/members?member_count=true' % pri_data.known_workspace_id)
    assert response.json == 4

    # Admins
    response = rmaker.make_authenticated_admin_request(
        method='GET',
        path='/api/v1/workspaces/%s/members' % pri_data.known_workspace_id,
        data=json.dumps({})
    )
    assert response.status_code == 200

    # 2 normal users + 1 manager + 1 workspace owner
    assert len([
        member for member in response.json
        if member['user_id'] == pri_data.known_workspace_owner_id and member['is_owner']]) == 1
    assert len([member for member in response.json if member['is_manager']]) == 2
    assert len([member for member in response.json if not (member['is_manager'] or member['is_owner'])]) == 2
    assert len([member for member in response.json if member['is_banned']]) == 0

    response = rmaker.make_authenticated_admin_request(
        method='GET',
        path='/api/v1/workspaces/%s/members?member_count=true' % pri_data.known_workspace_id)
    assert response.json == 4


def test_promote_and_demote_workspace_members(rmaker: RequestMaker, pri_data: PrimaryData):
    # Anonymous
    response = rmaker.make_request(
        method='PATCH',
        data=json.dumps(dict(user_id=pri_data.known_user_id, operation='promote')),
        path='/api/v1/workspaces/%s/members' % pri_data.known_workspace_id
    )
    assert response.status_code == 401

    # Authenticated
    response = rmaker.make_authenticated_user_request(
        method='PATCH',
        data=json.dumps(dict(user_id=pri_data.known_user_id, operation='promote')),
        path='/api/v1/workspaces/%s/members' % pri_data.known_workspace_id
    )
    assert response.status_code == 403

    # Manager should be able to promote and demote
    response = rmaker.make_authenticated_workspace_owner2_request(
        method='PATCH',
        data=json.dumps(dict(user_id=pri_data.known_user_id, operation='promote')),
        path='/api/v1/workspaces/%s/members' % pri_data.known_workspace_id
    )
    assert response.status_code == 200
    response = rmaker.make_authenticated_workspace_owner2_request(
        method='PATCH',
        data=json.dumps(dict(user_id=pri_data.known_user_id, operation='demote')),
        path='/api/v1/workspaces/%s/members' % pri_data.known_workspace_id
    )
    assert response.status_code == 200

    # Manager should not be able to demote owner
    response = rmaker.make_authenticated_workspace_owner2_request(
        method='PATCH',
        data=json.dumps(dict(user_id=pri_data.known_workspace_owner_id, operation='demote')),
        path='/api/v1/workspaces/%s/members' % pri_data.known_workspace_id
    )
    assert response.status_code == 403


def test_transfer_ownership_workspace(rmaker: RequestMaker, pri_data: PrimaryData):
    ws = Workspace('TestWorkspaceTransferOwnership')
    ws.id = 'TestWorkspaceId'
    ws.cluster = 'dummy_cluster_1'

    u1 = User.query.filter_by(id=pri_data.known_user_id).first()
    wsu1_obj = WorkspaceMembership(user=u1, workspace=ws)
    db.session.add(wsu1_obj)
    ws.memberships.append(wsu1_obj)
    u2 = User.query.filter_by(id=pri_data.known_workspace_owner_id_2).first()
    wsu2_obj = WorkspaceMembership(user=u2, workspace=ws)
    db.session.add(wsu2_obj)
    ws.memberships.append(wsu2_obj)
    u3 = User.query.filter_by(id=pri_data.known_workspace_owner_id).first()
    wsu3_obj = WorkspaceMembership(user=u3, workspace=ws, is_manager=True, is_owner=True)
    db.session.add(wsu3_obj)
    ws.memberships.append(wsu3_obj)
    db.session.add(ws)
    db.session.commit()

    # Anonymous
    response = rmaker.make_request(
        method='PATCH',
        data=json.dumps(dict(new_owner_id=pri_data.known_user_id)),
        path='/api/v1/workspaces/%s/transfer_ownership' % ws.id
    )
    assert response.status_code == 401

    # Authenticated user request
    response = rmaker.make_authenticated_user_request(
        method='PATCH',
        data=json.dumps(dict(new_owner_id=u1.id)),
        path='/api/v1/workspaces/%s/transfer_ownership' % ws.id
    )
    assert response.status_code == 403

    # new_owner_to_be is a member of workspace but not owner
    response = rmaker.make_authenticated_workspace_owner_request(
        method='PATCH',
        data=json.dumps(dict(new_owner_id=u1.id)),
        path='/api/v1/workspaces/%s/transfer_ownership' % ws.id
    )
    assert response.status_code == 403

    # new_owner_to_be not a member of workspace
    response = rmaker.make_authenticated_workspace_owner_request(
        method='PATCH',
        data=json.dumps(dict(new_owner_id=pri_data.known_user_2_ext_id)),
        path='/api/v1/workspaces/%s/transfer_ownership' % ws.id
    )
    assert response.status_code == 403

    # new_owner_to_be member of workspace and owner
    response = rmaker.make_authenticated_workspace_owner_request(
        method='PATCH',
        data=json.dumps(dict(new_owner_id=u2.id)),
        path='/api/v1/workspaces/%s/transfer_ownership' % ws.id
    )
    assert response.status_code == 200

    # old owner tries to add new_owner again
    response = rmaker.make_authenticated_workspace_owner_request(
        method='PATCH',
        data=json.dumps(dict(new_owner_id=u2.id)),
        path='/api/v1/workspaces/%s/transfer_ownership' % ws.id
    )
    assert response.status_code == 403


def test_clear_members_from_workspace(rmaker: RequestMaker, pri_data: PrimaryData):
    name = 'WorkspaceToBeCleared'
    ws = Workspace(name)
    u1 = User.query.filter_by(id=pri_data.known_user_id).first()
    wsu1_obj = WorkspaceMembership(user=u1, workspace=ws)
    db.session.add(wsu1_obj)
    ws.memberships.append(wsu1_obj)
    u2 = User.query.filter_by(id=pri_data.known_workspace_owner_id_2).first()
    wsu2_obj = WorkspaceMembership(user=u2, workspace=ws, is_manager=True, is_owner=False)
    db.session.add(wsu2_obj)
    ws.memberships.append(wsu2_obj)
    u3 = User.query.filter_by(id=pri_data.known_workspace_owner_id).first()
    wsu3_obj = WorkspaceMembership(user=u3, workspace=ws, is_manager=True, is_owner=True)
    db.session.add(wsu3_obj)
    ws.memberships.append(wsu3_obj)
    db.session.add(ws)
    db.session.commit()
    # Anonymous
    response = rmaker.make_request(
        method='POST',
        path='/api/v1/workspaces/%s/clear_members' % ws.id,
        data=json.dumps({})
    )
    assert response.status_code == 401

    # Authenticated user
    response = rmaker.make_authenticated_user_request(
        method='POST',
        path='/api/v1/workspaces/%s/clear_members' % ws.id,
        data=json.dumps({})
    )
    assert response.status_code == 403

    # Authenticated workspace owner
    response = rmaker.make_authenticated_workspace_owner_request(
        method='POST',
        path='/api/v1/workspaces/%s/clear_members' % ws.id,
        data=json.dumps({})
    )
    assert response.status_code == 200

    # Authenticated workspace owner, invalid workspace id
    invalid_response = rmaker.make_authenticated_workspace_owner_request(
        method='POST',
        path='/api/v1/workspaces/%s/clear_members' % 'does-not-exist',
        data=json.dumps({})
    )
    assert invalid_response.status_code == 404

    # Authenticated workspace manager
    response = rmaker.make_authenticated_workspace_owner2_request(
        method='POST',
        path='/api/v1/workspaces/%s/clear_members' % ws.id,
        data=json.dumps({})
    )
    assert response.status_code == 403

    # Admin, system.default workspace
    invalid_response = rmaker.make_authenticated_admin_request(
        method='POST',
        path='/api/v1/workspaces/%s/clear_members' % pri_data.system_default_workspace_id,
        data=json.dumps({})
    )
    assert invalid_response.status_code == 422

    # Admin
    response = rmaker.make_authenticated_admin_request(
        method='POST',
        path='/api/v1/workspaces/%s/clear_members' % ws.id,
        data=json.dumps({})
    )
    assert response.status_code == 200


def test_clear_expired_members_from_workspace(rmaker: RequestMaker, pri_data: PrimaryData):
    ws = Workspace(name='WorkspaceToBeCleared')
    ws.membership_expiry_policy = dict(kind=Workspace.MEP_PERSISTENT)
    u1 = User.query.filter_by(id=pri_data.known_user_id).first()
    wsu1_obj = WorkspaceMembership(user=u1, workspace=ws, is_manager=False, is_owner=False)
    db.session.add(wsu1_obj)
    ws.memberships.append(wsu1_obj)
    uo2 = User.query.filter_by(id=pri_data.known_workspace_owner_id_2).first()
    wsu2_obj = WorkspaceMembership(user=uo2, workspace=ws, is_manager=True, is_owner=False)
    db.session.add(wsu2_obj)
    ws.memberships.append(wsu2_obj)
    uo1 = User.query.filter_by(id=pri_data.known_workspace_owner_id).first()
    wsu3_obj = WorkspaceMembership(user=uo1, workspace=ws, is_manager=True, is_owner=True)
    db.session.add(wsu3_obj)
    ws.memberships.append(wsu3_obj)
    db.session.add(ws)
    db.session.commit()
    # Anonymous
    response = rmaker.make_request(
        method='POST',
        path='/api/v1/workspaces/%s/clear_expired_members' % ws.id,
        data=json.dumps({})
    )
    assert response.status_code == 401
    # Authenticated user
    response = rmaker.make_authenticated_user_request(
        method='POST',
        path='/api/v1/workspaces/%s/clear_expired_members' % ws.id,
        data=json.dumps({})
    )
    assert response.status_code == 403
    # Authenticated workspace owner
    response = rmaker.make_authenticated_workspace_owner_request(
        method='POST',
        path='/api/v1/workspaces/%s/clear_expired_members' % ws.id,
        data=json.dumps({})
    )
    assert response.status_code == 403

    # Authenticated workspace owner, invalid workspace id
    invalid_response = rmaker.make_authenticated_workspace_owner_request(
        method='POST',
        path='/api/v1/workspaces/%s/clear_expired_members' % 'does-not-exist',
        data=json.dumps({})
    )
    assert invalid_response.status_code == 403

    # Authenticated workspace manager
    response = rmaker.make_authenticated_workspace_owner2_request(
        method='POST',
        path='/api/v1/workspaces/%s/clear_expired_members' % ws.id,
        data=json.dumps({})
    )
    assert response.status_code == 403
    # Admin, wrong policy
    invalid_response = rmaker.make_authenticated_admin_request(
        method='POST',
        path='/api/v1/workspaces/%s/clear_expired_members' % ws.id,
        data=json.dumps({})
    )
    assert invalid_response.status_code == 422

    # Assign suitable policy and set last login times
    ws.membership_expiry_policy = dict(kind=Workspace.MEP_ACTIVITY_TIMEOUT, timeout_days=45)
    u1.last_login_ts = time.time() - 44 * 24 * 3600
    uo2.last_login_ts = time.time() - 100 * 24 * 3600
    uo1.last_login_ts = time.time() - 100 * 24 * 3600
    db.session.commit()

    # u1 has not expired yet, owners and managers should not be removed
    response = rmaker.make_authenticated_admin_request(
        method='POST',
        path='/api/v1/workspaces/%s/clear_expired_members' % ws.id,
        data=json.dumps({})
    )
    assert response.status_code == 200
    assert response.json.get('num_deleted') == 0

    # u1 has expired, owners and managers should not be removed
    u1.last_login_ts = time.time() - 46 * 24 * 3600
    db.session.commit()
    response = rmaker.make_authenticated_admin_request(
        method='POST',
        path='/api/v1/workspaces/%s/clear_expired_members' % ws.id,
        data=json.dumps({})
    )
    assert response.status_code == 200
    assert response.json.get('num_deleted') == 1


def test_clear_expired_members_from_workspace_no_login(rmaker: RequestMaker, pri_data: PrimaryData):
    ws = Workspace(name='WorkspaceToBeCleared')
    ws.membership_expiry_policy = dict(kind=Workspace.MEP_ACTIVITY_TIMEOUT, timeout_days=60)

    # add a user mimicking a guest user that has never logged in
    ug = User("guest@local", "guest")
    ug.joining_ts = time.time() - 59 * 24 * 3600
    wsm = WorkspaceMembership(user=ug, workspace=ws, is_manager=False, is_owner=False)
    ws.memberships.append(wsm)
    db.session.add(ws)
    db.session.commit()

    # The user is not old enough to be deleted
    response = rmaker.make_authenticated_admin_request(
        method='POST',
        path='/api/v1/workspaces/%s/clear_expired_members' % ws.id,
        data=json.dumps({})
    )
    assert response.status_code == 200
    assert response.json.get('num_deleted') == 0

    # change the policy so that the user is older than the limit
    ws.membership_expiry_policy = dict(kind=Workspace.MEP_ACTIVITY_TIMEOUT, timeout_days=45)
    db.session.commit()
    response = rmaker.make_authenticated_admin_request(
        method='POST',
        path='/api/v1/workspaces/%s/clear_expired_members' % ws.id,
        data=json.dumps({})
    )
    assert response.status_code == 200
    assert response.json.get('num_deleted') == 1


def test_update_membership_expiry_policy(rmaker: RequestMaker, pri_data: PrimaryData):
    ws = Workspace.query.filter_by(id=pri_data.known_workspace_id).first()
    valid_mep = dict(kind=Workspace.MEP_PERSISTENT)

    # Anonymous
    response = rmaker.make_request(
        method='PUT',
        path='/api/v1/workspaces/%s/membership_expiry_policy' % ws.id,
        data=json.dumps(valid_mep)
    )
    assert response.status_code == 401

    # Authenticated
    response = rmaker.make_authenticated_user_request(
        method='PUT',
        path='/api/v1/workspaces/%s/membership_expiry_policy' % ws.id,
        data=json.dumps(valid_mep)
    )
    assert response.status_code == 403

    # Authenticated workspace owner
    response = rmaker.make_authenticated_workspace_owner_request(
        method='PUT',
        path='/api/v1/workspaces/%s/membership_expiry_policy' % ws.id,
        data=json.dumps(valid_mep)
    )
    assert response.status_code == 403

    # Admin
    response = rmaker.make_authenticated_admin_request(
        method='PUT',
        path='/api/v1/workspaces/%s/membership_expiry_policy' % ws.id,
        data=json.dumps(valid_mep)
    )
    assert response.status_code == 200

    # invalid policy
    response = rmaker.make_authenticated_admin_request(
        method='PUT',
        path='/api/v1/workspaces/%s/membership_expiry_policy' % ws.id,
        data=json.dumps(dict(kind='NoSuchKind'))
    )
    assert response.status_code == 422


def test_update_membership_join_policy(rmaker: RequestMaker, pri_data: PrimaryData):
    ws = Workspace.query.filter_by(id=pri_data.known_workspace_id).first()
    valid_mjp = dict(tolerations=['low_trust'])

    # Anonymous
    response = rmaker.make_request(
        method='PUT',
        path='/api/v1/workspaces/%s/membership_join_policy' % ws.id,
        data=json.dumps(valid_mjp)
    )
    assert response.status_code == 401

    # Authenticated
    response = rmaker.make_authenticated_user_request(
        method='PUT',
        path='/api/v1/workspaces/%s/membership_join_policy' % ws.id,
        data=json.dumps(valid_mjp)
    )
    assert response.status_code == 403

    # Authenticated workspace owner
    response = rmaker.make_authenticated_workspace_owner_request(
        method='PUT',
        path='/api/v1/workspaces/%s/membership_join_policy' % ws.id,
        data=json.dumps(valid_mjp)
    )
    assert response.status_code == 403

    # Admin
    response = rmaker.make_authenticated_admin_request(
        method='PUT',
        path='/api/v1/workspaces/%s/membership_join_policy' % ws.id,
        data=json.dumps(valid_mjp)
    )
    assert response.status_code == 200

    # invalid policies
    invalid_mjps = [
        dict(foo='bar'),
        dict(foo='bar', tolerations=['foo']),
        dict(tolerations='foo'),
        dict(tolerations=dict(hello='sailor')),
    ]
    for mjp in invalid_mjps:
        response = rmaker.make_authenticated_admin_request(
            method='PUT',
            path='/api/v1/workspaces/%s/membership_join_policy' % ws.id,
            data=json.dumps(mjp)
        )
        assert response.status_code == 422, '%s should be invalid join policy' % mjp


def test_workspace_accounting(rmaker: RequestMaker, pri_data: PrimaryData):
    # Anonymous
    response = rmaker.make_request(
        method='GET',
        path='/api/v1/workspaces/%s/accounting' % pri_data.known_workspace_id
    )
    assert response.status_code == 401

    # Authenticated User, not a manager
    response = rmaker.make_authenticated_user_request(
        method='GET',
        path='/api/v1/workspaces/%s/accounting' % pri_data.known_workspace_id)
    assert response.status_code == 403

    # Authenticated Workspace Owner, who does not own the workspace
    response = rmaker.make_authenticated_workspace_owner_request(
        method='GET',
        path='/api/v1/workspaces/%s/accounting' % pri_data.known_workspace_id_2,
        data=json.dumps({})
    )
    assert response.status_code == 403

    # Admins
    response = rmaker.make_authenticated_admin_request(
        method='GET',
        path='/api/v1/workspaces/%s/accounting' % pri_data.known_workspace_id,
        data=json.dumps({})
    )
    assert response.status_code == 200

    # Test total gibs are returned right
    response = rmaker.make_authenticated_admin_request(
        method='GET',
        path='/api/v1/workspaces/%s/accounting' % pri_data.known_workspace_id,
        data=json.dumps({})
    )
    assert response.status_code == 200
    assert response.json['gib_hours'] == 28


def test_workspace_user_folder_size(rmaker: RequestMaker, pri_data: PrimaryData):
    # Anonymous
    response = rmaker.make_request(
        method='PUT',
        path='/api/v1/workspaces/%s/user_work_folder_size_gib' % pri_data.known_workspace_id,
        data=json.dumps(dict(new_size=25)),
    )
    assert response.status_code == 401

    # Authenticated User, not a manager
    response = rmaker.make_authenticated_user_request(
        method='PUT',
        path='/api/v1/workspaces/%s/user_work_folder_size_gib' % pri_data.known_workspace_id,
        data=json.dumps(dict(new_size=25)),
    )
    assert response.status_code == 403

    # Authenticated workspace owner
    response = rmaker.make_authenticated_workspace_owner_request(
        method='PUT',
        path='/api/v1/workspaces/%s/user_work_folder_size_gib' % pri_data.known_workspace_id,
        data=json.dumps(dict(new_size=25)),
    )
    assert response.status_code == 403

    # Admin, legal request
    response_modify_size = rmaker.make_authenticated_admin_request(
        method='PUT',
        path='/api/v1/workspaces/%s/user_work_folder_size_gib' % pri_data.known_workspace_id,
        data=json.dumps(dict(new_size=1276)),
    )
    assert response_modify_size.status_code == 200

    # Test user folder size is returned right
    response = rmaker.make_authenticated_admin_request(
        method='GET',
        path='/api/v1/workspaces/%s' % pri_data.known_workspace_id,
        data=json.dumps({})
    )
    assert response.status_code == 200
    assert response.json['config']['user_work_folder_size_gib'] == 1276


def test_workspace_memory_limit_gib(rmaker: RequestMaker, pri_data: PrimaryData):
    # Anonymous
    response = rmaker.make_request(
        method='PUT',
        path='/api/v1/workspaces/%s/memory_limit_gib' % pri_data.known_workspace_id,
        data=json.dumps(dict(new_limit=25)),
    )
    assert response.status_code == 401

    # Authenticated User, not a manager
    response = rmaker.make_authenticated_user_request(
        method='PUT',
        path='/api/v1/workspaces/%s/memory_limit_gib' % pri_data.known_workspace_id,
        data=json.dumps(dict(new_limit=25)),
    )
    assert response.status_code == 403

    # Authenticated workspace owner
    response = rmaker.make_authenticated_workspace_owner_request(
        method='PUT',
        path='/api/v1/workspaces/%s/memory_limit_gib' % pri_data.known_workspace_id,
        data=json.dumps(dict(new_limit=25)),
    )
    assert response.status_code == 403

    # Admin, legal request
    response = rmaker.make_authenticated_admin_request(
        method='PUT',
        path='/api/v1/workspaces/%s/memory_limit_gib' % pri_data.known_workspace_id,
        data=json.dumps(dict(new_limit=25)),
    )
    assert response.status_code == 200

    # Admin, illegal request. Make sure the limit is not modified
    response = rmaker.make_authenticated_admin_request(
        method='PUT',
        path='/api/v1/workspaces/%s/memory_limit_gib' % pri_data.known_workspace_id,
        data=json.dumps(dict(new_limit=-1)),
    )
    assert response.status_code == 422
    res = rmaker.make_authenticated_admin_request(
        path='/api/v1/workspaces/%s' % pri_data.known_workspace_id,
    )
    assert res.json.get('memory_limit_gib') == 25


def test_update_workspace_cluster(rmaker: RequestMaker, pri_data: PrimaryData):
    # Anonymous
    response = rmaker.make_request(
        method='PUT',
        path='/api/v1/workspaces/%s/cluster' % pri_data.known_workspace_id,
        data=json.dumps(dict(new_cluster='dummy_cluster_1')),
    )
    assert response.status_code == 401

    # Authenticated User, not a manager
    response = rmaker.make_authenticated_user_request(
        method='PUT',
        path='/api/v1/workspaces/%s/cluster' % pri_data.known_workspace_id,
        data=json.dumps(dict(new_cluster='dummy_cluster_1')),
    )
    assert response.status_code == 403

    # Authenticated workspace owner
    response = rmaker.make_authenticated_workspace_owner_request(
        method='PUT',
        path='/api/v1/workspaces/%s/cluster' % pri_data.known_workspace_id,
        data=json.dumps(dict(new_cluster='dummy_cluster_1')),
    )
    assert response.status_code == 403

    # Admin, legal request
    response = rmaker.make_authenticated_admin_request(
        method='PUT',
        path='/api/v1/workspaces/%s/cluster' % pri_data.known_workspace_id,
        data=json.dumps(dict(new_cluster='dummy_cluster_1')),
    )
    assert response.status_code == 200

    # Admin, illegal request. No such cluster. Make sure the cluster is not modified
    response = rmaker.make_authenticated_admin_request(
        method='PUT',
        path='/api/v1/workspaces/%s/cluster' % pri_data.known_workspace_id,
        data=json.dumps(dict(new_cluster='dummy_cluster_3')),
    )
    assert response.status_code == 422
    res = rmaker.make_authenticated_admin_request(
        path='/api/v1/workspaces/%s' % pri_data.known_workspace_id,
    )
    assert 'dummy_cluster_1' == res.json.get('cluster')


def test_update_workspace_expiry_ts(rmaker: RequestMaker, pri_data: PrimaryData):
    future_ts = int(time.time()) + 3600 * 24 * 30 * 6
    # Anonymous
    response = rmaker.make_request(
        method='PUT',
        path='/api/v1/workspaces/%s/expiry_ts' % pri_data.known_workspace_id,
        data=json.dumps(dict(new_expiry_ts=future_ts)),
    )
    assert response.status_code == 401

    # Authenticated User, not a manager
    response = rmaker.make_authenticated_user_request(
        method='PUT',
        path='/api/v1/workspaces/%s/expiry_ts' % pri_data.known_workspace_id,
        data=json.dumps(dict(new_expiry_ts=future_ts)),
    )
    assert response.status_code == 403

    # Authenticated workspace owner
    response = rmaker.make_authenticated_workspace_owner_request(
        method='PUT',
        path='/api/v1/workspaces/%s/expiry_ts' % pri_data.known_workspace_id,
        data=json.dumps(dict(new_expiry_ts=future_ts)),
    )
    assert response.status_code == 403

    # Admin, legal request
    response = rmaker.make_authenticated_admin_request(
        method='PUT',
        path='/api/v1/workspaces/%s/expiry_ts' % pri_data.known_workspace_id,
        data=json.dumps(dict(new_expiry_ts=future_ts)),
    )
    assert response.status_code == 200

    # Admin, illegal requests.
    illegal_expiry_inputs = ['', 0, -1, '2029-01-01', int(time.time()) - 3600 * 24 * 30]
    for illegal_param in illegal_expiry_inputs:
        response = rmaker.make_authenticated_admin_request(
            method='PUT',
            path='/api/v1/workspaces/%s/expiry_ts' % pri_data.known_workspace_id,
            data=json.dumps(dict(new_expiry_ts=illegal_param)),
        )
        # some are picked by RequestParser (-> 400), some by our logic (-> 422)
        assert response.status_code in (400, 422)


def test_create_volume_tasks(rmaker: RequestMaker, pri_data: PrimaryData):
    # Anonymous
    response = rmaker.make_request(
        method='POST',
        path='/api/v1/workspaces/%s/create_volume_tasks' % pri_data.known_workspace_id,
        data=json.dumps(dict(task_kind='workspace_backup', cluster='dummy_cluster_1')),
    )
    assert response.status_code == 401

    # Authenticated User, not a manager
    response = rmaker.make_authenticated_user_request(
        method='POST',
        path='/api/v1/workspaces/%s/create_volume_tasks' % pri_data.known_workspace_id,
        data=json.dumps(dict(task_kind='workspace_backup', cluster='dummy_cluster_1')),
    )
    assert response.status_code == 403

    # Authenticated workspace owner
    response = rmaker.make_authenticated_workspace_owner_request(
        method='POST',
        path='/api/v1/workspaces/%s/create_volume_tasks' % pri_data.known_workspace_id,
        data=json.dumps(dict(task_kind='workspace_backup', cluster='dummy_cluster_1')),
    )
    assert response.status_code == 403

    # Admin, legal request for backup
    response = rmaker.make_authenticated_admin_request(
        method='POST',
        path='/api/v1/workspaces/%s/create_volume_tasks' % pri_data.known_workspace_id,
        data=json.dumps(dict(task_kind='workspace_volume_backup', cluster='dummy_cluster_1')),
    )
    assert response.status_code == 200
    tasks = db.session.scalars(select(Task).where(Task.kind == 'workspace_volume_backup')).all()
    members = db.session.scalars(
        select(WorkspaceMembership).where(WorkspaceMembership.workspace_id == pri_data.known_workspace_id)
    ).all()
    # one task per workspace member plus one for shared folder
    assert len(tasks) == len(members) + 1

    # Admin, legal request for restore
    response = rmaker.make_authenticated_admin_request(
        method='POST',
        path='/api/v1/workspaces/%s/create_volume_tasks' % pri_data.known_workspace_id,
        data=json.dumps(
            dict(task_kind='workspace_volume_restore', src_cluster='dummy_cluster_1', tgt_cluster='dummy_cluster_2')
        ),
    )
    assert response.status_code == 200
    tasks = db.session.scalars(select(Task).where(Task.kind == 'workspace_volume_restore')).all()
    members = db.session.scalars(
        select(WorkspaceMembership).where(WorkspaceMembership.workspace_id == pri_data.known_workspace_id)
    ).all()
    # one task per workspace member plus one for shared folder
    assert len(tasks) == len(members) + 1

    # Admin, invalid requests
    invalid_data = [
        dict(task_kind='workspace_backup'),
        dict(task_kind='workspace_volume_restore'),
        dict(task_kind='workspace_restore'),
        dict(task_kind='workspace_volume_restore', cluster='dummy_cluster_2'),

    ]
    for data in invalid_data:
        response = rmaker.make_authenticated_admin_request(
            method='POST',
            path='/api/v1/workspaces/%s/create_volume_tasks' % pri_data.known_workspace_id,
            data=json.dumps(data),
        )
        assert response.status_code == 422
