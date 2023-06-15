import json

from pebbles.models import User
from pebbles.models import db
from tests.conftest import PrimaryData, RequestMaker


def test_get_user(rmaker: RequestMaker, pri_data: PrimaryData):
    # Anonymous
    response = rmaker.make_request(path='/api/v1/users/%s' % pri_data.known_user_id)
    assert response.status_code == 401

    # Authenticated, get user data for self
    response = rmaker.make_authenticated_user_request(path='/api/v1/users/%s' % pri_data.known_user_id)
    assert response.status_code == 200
    assert pri_data.known_user_ext_id == response.json['ext_id']

    # Authenticated, get user data for another user
    response = rmaker.make_authenticated_user_request(path='/api/v1/users/%s' % pri_data.known_workspace_owner_id)
    assert response.status_code == 403

    # Workspace owner, get user data for another user in workspace
    response = rmaker.make_authenticated_workspace_owner_request(path='/api/v1/users/%s' % pri_data.known_user_id)
    assert response.status_code == 403

    # Admin
    response = rmaker.make_authenticated_admin_request(path='/api/v1/users/%s' % pri_data.known_user_id)
    assert response.status_code == 200
    assert pri_data.known_user_ext_id == response.json['ext_id']

    # Admin, deleted user
    response = rmaker.make_authenticated_admin_request(path='/api/v1/users/%s' % pri_data.known_deleted_user_id)
    assert response.status_code == 404

    # Admin, non-existent id
    response = rmaker.make_authenticated_admin_request(path='/api/v1/users/%s' % 'no-such-id')
    assert response.status_code == 404


def test_get_users(rmaker: RequestMaker, pri_data: PrimaryData):
    # Anonymous
    response = rmaker.make_request(path='/api/v1/users')
    assert response.status_code == 401
    # Authenticated
    response = rmaker.make_authenticated_user_request(path='/api/v1/users')
    assert response.status_code == 403
    # Admin
    response = rmaker.make_authenticated_admin_request(path='/api/v1/users')
    assert response.status_code == 200


def test_delete_user(rmaker: RequestMaker, pri_data: PrimaryData):
    ext_id = "test@example.org"
    u = User(ext_id, "testuser", is_admin=False)
    # Anonymous
    db.session.add(u)
    db.session.commit()

    response = rmaker.make_request(
        method='DELETE',
        path='/api/v1/users/%s' % u.id
    )
    assert response.status_code == 401
    # Authenticated
    response = rmaker.make_authenticated_user_request(
        method='DELETE',
        path='/api/v1/users/%s' % u.id
    )
    assert response.status_code == 403
    # Admin
    response = rmaker.make_authenticated_admin_request(
        method='DELETE',
        path='/api/v1/users/%s' % u.id
    )
    assert response.status_code == 200
    user = User.query.filter_by(id=u.id).first()
    assert (user.ext_id != ext_id)


def test_block_user(rmaker: RequestMaker, pri_data: PrimaryData):
    ext_id = "test@example.org"
    u = User(ext_id, "testuser", is_admin=False)
    db.session.add(u)
    db.session.commit()
    # Anonymous
    response = rmaker.make_request(
        method='PATCH',
        path='/api/v1/users/%s' % u.id,
        data=json.dumps({'is_blocked': True})
    )
    assert response.status_code == 401
    # Authenticated
    response = rmaker.make_authenticated_user_request(
        method='PATCH',
        path='/api/v1/users/%s' % u.id,
        data=json.dumps({'is_blocked': True})
    )
    assert response.status_code == 403
    response = rmaker.make_authenticated_user_request(
        method='PATCH',
        path='/api/v1/users/%s' % u.id,
        data=json.dumps({'is_blocked': True})
    )
    assert response.status_code == 403
    # Admin
    # Block
    response = rmaker.make_authenticated_admin_request(
        method='PATCH',
        path='/api/v1/users/%s' % u.id,
        data=json.dumps({'is_blocked': True})
    )
    assert response.status_code == 200
    user = User.query.filter_by(id=u.id).first()
    assert (user.is_blocked)
    # Unblock
    response = rmaker.make_authenticated_admin_request(
        method='PATCH',
        path='/api/v1/users/%s' % u.id,
        data=json.dumps({'is_blocked': False})
    )
    assert response.status_code == 200
    user = User.query.filter_by(id=u.id).first()
    assert not user.is_blocked


def test_get_user_workspace_memberships(rmaker: RequestMaker, pri_data: PrimaryData):
    # Anonymous
    response = rmaker.make_request(
        path='/api/v1/users/%s/workspace_memberships' % pri_data.known_user_id
    )
    assert response.status_code == 401

    # Authenticated but different user
    response = rmaker.make_authenticated_user_request(
        path='/api/v1/users/%s/workspace_memberships' % pri_data.known_workspace_owner_id
    )
    assert response.status_code == 403

    # Authenticated
    response = rmaker.make_authenticated_user_request(
        path='/api/v1/users/%s/workspace_memberships' % pri_data.known_user_id
    )
    assert response.status_code == 200
    # System.default, one WS membership, one ban
    assert len(response.json) == 3

    # Owner should not be able to query user
    response = rmaker.make_authenticated_workspace_owner_request(
        path='/api/v1/users/%s/workspace_memberships' % pri_data.known_user_id
    )
    assert response.status_code == 403

    # Admin
    response = rmaker.make_authenticated_admin_request(
        path='/api/v1/users/%s/workspace_memberships' % pri_data.known_user_id
    )
    assert response.status_code == 200


def test_post_user_access(rmaker: RequestMaker, pri_data: PrimaryData):
    userdata = dict(ext_id='user3@example.org', email_id='u3@example.org', lifetime_in_days=5, is_admin=False)
    # Anonymous
    response = rmaker.make_request(
        method='POST',
        path='/api/v1/users',
        data=json.dumps(userdata)
    )
    assert response.status_code == 401
    # Authenticated User
    response = rmaker.make_authenticated_user_request(
        method='POST',
        path='/api/v1/users',
        data=json.dumps(userdata)
    )
    assert response.status_code == 403
    # Owner
    response = rmaker.make_authenticated_workspace_owner_request(
        method='POST',
        path='/api/v1/users',
        data=json.dumps(userdata)
    )
    assert response.status_code == 403
    # Admin
    response = rmaker.make_authenticated_admin_request(
        method='POST',
        path='/api/v1/users',
        data=json.dumps(userdata)
    )
    assert response.status_code == 200


def test_post_user_admin(rmaker: RequestMaker, pri_data: PrimaryData):
    def check_user_matches_post_data(post_data):
        user = rmaker.make_authenticated_admin_request(path='/api/v1/users/%s' % response.json['id']).json
        for key in [x for x in userdata.keys() if x != 'lifetime_in_days']:
            assert user[key] == post_data[key], key
        if 'lifetime_in_days' in post_data:
            assert user['expiry_ts'] - user['joining_ts'] == post_data['lifetime_in_days'] * 86400

    # Post a user, fetch user from API and check that data matches
    userdata = dict(ext_id='user3@example.org', email_id='u3@example.org', is_admin=False, lifetime_in_days=7)
    response = rmaker.make_authenticated_admin_request(
        method='POST',
        path='/api/v1/users',
        data=json.dumps(userdata)
    )
    assert response.status_code == 200
    check_user_matches_post_data(userdata)
    # Test for existing ext_id, should fail
    userdata = dict(ext_id='user3@example.org', email_id='u3@example.org', is_admin=False, lifetime_in_days=7)
    response = rmaker.make_authenticated_admin_request(
        method='POST',
        path='/api/v1/users',
        data=json.dumps(userdata)
    )
    assert response.status_code == 409
    # Setting lifetime to invalid value
    userdata = dict(ext_id='user4@example.org', lifetime_in_days=0.2)
    response = rmaker.make_authenticated_admin_request(
        method='POST',
        path='/api/v1/users',
        data=json.dumps(userdata)
    )
    assert response.status_code == 400
    #  No lifetime limit
    userdata = dict(ext_id='admin5@example.org', is_admin=True)
    response = rmaker.make_authenticated_admin_request(
        method='POST',
        path='/api/v1/users',
        data=json.dumps(userdata)
    )
    assert response.status_code == 200
    check_user_matches_post_data(userdata)
    # Not setting ext_id should fail
    userdata = dict(email_id='u6@example.org', is_admin=False, lifetime_in_days=7)
    response = rmaker.make_authenticated_admin_request(
        method='POST',
        path='/api/v1/users',
        data=json.dumps(userdata)
    )
    assert response.status_code == 400


def test_user_workspace_quota(rmaker: RequestMaker, pri_data: PrimaryData):
    # Anonymous
    response = rmaker.make_request(
        method='PATCH',
        path='/api/v1/users/%s' % pri_data.known_user_id,
        data=json.dumps(dict(workspace_quota=1))
    )
    assert response.status_code == 401

    # Authenticated
    response = rmaker.make_authenticated_user_request(
        method='PATCH',
        path='/api/v1/users/%s' % pri_data.known_user_id,
        data=json.dumps(dict(workspace_quota=1))
    )
    assert response.status_code == 403

    # Admin
    response = rmaker.make_authenticated_admin_request(
        method='PATCH',
        path='/api/v1/users/%s' % pri_data.known_user_id,
        data=json.dumps(dict(workspace_quota=1))
    )
    assert response.status_code == 200

    # invalid inputs
    for invalid_input in [-1, 1000 * 1000, 'foo']:
        response = rmaker.make_authenticated_admin_request(
            method='PATCH',
            path='/api/v1/users/%s' % pri_data.known_user_id,
            data=json.dumps(dict(workspace_quota=invalid_input))
        )
        assert (response.status_code in [400, 422])
