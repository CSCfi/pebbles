import json

from tests.conftest import PrimaryData, RequestMaker


def test_anonymous_get_messages(rmaker: RequestMaker):
    response = rmaker.make_request(
        path='/api/v1/messages'
    )
    assert response.status_code == 401


def test_user_get_messages(rmaker: RequestMaker):
    response = rmaker.make_authenticated_user_request(
        path='/api/v1/messages'
    )
    assert response.status_code == 200
    assert len(response.json) == 2


def test_anonymous_post_message(rmaker: RequestMaker):
    response = rmaker.make_request(
        method='POST',
        path='/api/v1/messages',
        data=json.dumps({'subject': 'test subject', 'message': 'test message'})
    )
    assert response.status_code == 401


def test_user_post_message(rmaker: RequestMaker):
    response = rmaker.make_authenticated_user_request(
        method='POST',
        path='/api/v1/messages',
        data=json.dumps({'subject': 'test subject', 'message': 'test message'})
    )
    assert response.status_code == 403


def test_admin_post_message(rmaker: RequestMaker):
    response = rmaker.make_authenticated_admin_request(
        method='POST',
        path='/api/v1/messages',
        data=json.dumps({'subject': 'test subject', 'message': 'test message'})
    )
    assert response.status_code == 200
    response = rmaker.make_authenticated_user_request(
        path='/api/v1/messages'
    )
    assert response.status_code == 200
    assert len(response.json) == 3


def test_user_mark_message_as_seen(rmaker: RequestMaker, pri_data: PrimaryData):
    response = rmaker.make_authenticated_user_request(
        method='PATCH',
        path='/api/v1/messages/%s' % pri_data.known_message_id,
        data=json.dumps({'send_mail': False})
    )
    assert response.status_code == 200

    response = rmaker.make_authenticated_user_request(
        path='/api/v1/messages?show_unread=1'
    )
    assert response.status_code == 200
    assert len(response.json) == 1

    response = rmaker.make_authenticated_user_request(
        method='PATCH',
        path='/api/v1/messages/%s' % pri_data.known_message2_id,
        data=json.dumps({'send_mail': False})
    )
    assert response.status_code == 200

    response = rmaker.make_authenticated_user_request(
        path='/api/v1/messages?show_unread=1'
    )
    assert response.status_code == 200
    assert len(response.json) == 0


def test_admin_update_message(rmaker: RequestMaker, pri_data: PrimaryData):
    subject_topic = 'NotificationABC'
    response = rmaker.make_authenticated_admin_request(
        method='PUT',
        path='/api/v1/messages/%s' % pri_data.known_message_id,
        data=json.dumps({'subject': subject_topic, 'message': 'XXX'}))
    assert response.status_code == 200

    response = rmaker.make_authenticated_admin_request(
        path='/api/v1/messages/%s' % pri_data.known_message_id)
    assert response.status_code == 200
    assert response.json['subject'] == subject_topic
