import base64
import json

from sqlalchemy import select

from pebbles.models import User
from pebbles.models import db
from tests.conftest import PrimaryData, RequestMaker


def test_deleted_user_cannot_get_token(rmaker: RequestMaker, pri_data: PrimaryData):
    response = rmaker.make_request(
        method='POST',
        path='/api/v1/sessions',
        data=json.dumps(
            {'ext_id': 'user@example.org', 'password': 'user', 'email_id': None, 'agreement_sign': 'signed'}))
    assert response.status_code == 200

    response = rmaker.make_authenticated_admin_request(
        method='DELETE',
        path='/api/v1/users/%s' % pri_data.known_user_id
    )
    assert response.status_code == 200

    response = rmaker.make_request(
        method='POST',
        path='/api/v1/sessions',
        data=json.dumps(
            {'ext_id': 'user@example.org', 'password': 'user', 'email_id': None, 'agreement_sign': 'signed'}))
    assert response.status_code == 401


def test_deleted_user_cannot_use_token(rmaker: RequestMaker, pri_data: PrimaryData):
    response = rmaker.make_request(
        method='POST',
        path='/api/v1/sessions',
        data=json.dumps({'ext_id': 'user-2@example.org', 'password': 'user-2', 'agreement_sign': 'signed'})
    )
    assert response.status_code == 200

    token = '%s:' % response.json['token']
    token_b64 = base64.b64encode(bytes(token.encode('ascii'))).decode('utf-8')

    headers = {
        'Accept': 'application/json',
        'Authorization': 'Basic %s' % token_b64,
        'token': token_b64
    }
    # Test application session creation works for the user before the test
    response = rmaker.make_request(
        method='POST',
        path='/api/v1/application_sessions',
        data=json.dumps({'application_id': pri_data.known_application_public}),
        headers=headers)
    assert response.status_code == 200

    # Delete user-2 'u6' with admin credentials
    response = rmaker.make_authenticated_admin_request(
        method='DELETE',
        path='/api/v1/users/%s' % 'u6'
    )
    assert response.status_code == 200

    # Test application session creation fails for the user after the deletion
    response = rmaker.make_request(
        method='POST',
        path='/api/v1/application_sessions',
        data=json.dumps({'application_id': pri_data.known_application_public}),
        headers=headers)
    assert response.status_code == 401


def test_expired_user_cannot_login(rmaker: RequestMaker, pri_data: PrimaryData):
    # Test user with expired credentials cannot log in
    response = rmaker.make_request(
        method='POST',
        path='api/v1/sessions',
        data=json.dumps(dict(
            ext_id='expired_user@example.org',
            password='expired_user',
            agreement_sign='signed',
        ))
    )
    assert response.status_code == 403

    # Test user with non-expired credentials can log in
    response = rmaker.make_request(
        method='POST',
        path='api/v1/sessions',
        data=json.dumps(dict(
            ext_id='user@example.org',
            password='user',
            agreement_sign='signed',
        ))
    )
    assert response.status_code == 200
    assert response.json.get('token') is not None


def test_user_must_accept_toc(rmaker: RequestMaker, pri_data: PrimaryData):
    u = db.session.scalar(select(User).where(User.ext_id == 'user@example.org'))
    u.tc_acceptance_date = None
    db.session.commit()

    # Test that we get a reply with no token and terms_agreed set to false
    response = rmaker.make_request(
        method='POST',
        path='api/v1/sessions',
        data=json.dumps(dict(
            ext_id='user@example.org',
            password='user'
        ))
    )
    assert response.status_code == 200
    assert response.json.get('token') is None
    assert response.json.get('terms_agreed') is False

    # Same user, agreeing with wrong response
    response = rmaker.make_request(
        method='POST',
        path='api/v1/sessions',
        data=json.dumps(dict(
            ext_id='user@example.org',
            password='user',
            agreement_sign='allrightokay',
        ))
    )
    assert response.status_code == 403

    # Same user, agreeing to ToC
    response = rmaker.make_request(
        method='POST',
        path='api/v1/sessions',
        data=json.dumps(dict(
            ext_id='user@example.org',
            password='user',
            agreement_sign='signed',
        ))
    )
    assert response.status_code == 200
    assert response.json.get('token') is not None
    u = db.session.scalar(select(User).where(User.ext_id == 'user@example.org'))
    assert u.tc_acceptance_date is not None


def test_login_with_ext_id_delimiter(rmaker: RequestMaker, pri_data: PrimaryData):
    # Test user with expired credentials cannot log in
    response = rmaker.make_request(
        method='POST',
        path='api/v1/sessions',
        data=json.dumps(dict(
            ext_id='prefix/user@example.org',
            password='user',
        ))
    )
    assert response.status_code == 422


def test_login_with_invalid_form_data(rmaker: RequestMaker, pri_data: PrimaryData):
    # Test user with expired credentials cannot log in
    response = rmaker.make_request(
        method='POST',
        path='api/v1/sessions',
        data=json.dumps(dict(
            ext_id='user@example.org',
        ))
    )
    assert response.status_code == 422
