import json

from tests.conftest import PrimaryData, RequestMaker


def test_get_service_announcements_public(rmaker: RequestMaker, pri_data: PrimaryData):
    # anonymous
    response = rmaker.make_request(
        path='/api/v1/service_announcements_public'
    )
    assert response.status_code == 200
    assert len(response.json) == 1

    # user
    response = rmaker.make_authenticated_user_request(
        path='/api/v1/service_announcements_public'
    )
    assert response.status_code == 200
    assert len(response.json) == 1


def test_get_service_announcements(rmaker: RequestMaker, pri_data: PrimaryData):
    # anonymous
    response = rmaker.make_request(
        path='/api/v1/service_announcements'
    )
    assert response.status_code == 401

    # user
    response = rmaker.make_authenticated_user_request(
        path='/api/v1/service_announcements'
    )
    assert response.status_code == 200
    assert len(response.json) == 2

    # workspace-owner
    response = rmaker.make_authenticated_workspace_owner_request(
        path='/api/v1/service_announcements'
    )
    assert response.status_code == 200
    assert len(response.json) == 2

    # admin
    response = rmaker.make_authenticated_admin_request(
        path='/api/v1/service_announcements'
    )
    assert response.status_code == 200
    assert len(response.json) == 2


def test_get_service_announcements_admin(rmaker: RequestMaker, pri_data: PrimaryData):
    # workspace-owner
    response = rmaker.make_authenticated_workspace_owner_request(
        path='/api/v1/service_announcements_admin'
    )
    assert response.status_code == 403

    # admin
    response = rmaker.make_authenticated_admin_request(
        path='/api/v1/service_announcements_admin'
    )
    assert response.status_code == 200
    assert len(response.json) == 4


def test_update_service_announcement_admin(rmaker: RequestMaker, pri_data: PrimaryData):
    new_subject = 'Service AnnouncementABC'

    # workspace-owner
    response = rmaker.make_authenticated_workspace_owner_request(
        method='PUT',
        path='/api/v1/service_announcements_admin/%s' % pri_data.known_announcement_id,
        data=json.dumps(dict(
            subject=new_subject,
            content='XXX',
            level=3,
            targets='applications-header',
            is_enabled=True,
            is_public=True
        ))
    )
    assert response.status_code == 403

    # admin
    response = rmaker.make_authenticated_admin_request(
        method='PUT',
        path='/api/v1/service_announcements_admin/%s' % pri_data.known_announcement_id,
        data=json.dumps(dict(
            subject=new_subject,
            content='XXX',
            level=3,
            targets='applications-header',
            is_enabled=True,
            is_public=True
        ))
    )
    assert response.status_code == 200
    assert response.json['subject'] == new_subject


def test_delete_service_announcement_admin(rmaker: RequestMaker, pri_data: PrimaryData):
    # workspace-owner
    response = rmaker.make_authenticated_workspace_owner_request(
        method='DELETE',
        path='/api/v1/service_announcements_admin/%s' % pri_data.known_announcement_id
    )
    assert response.status_code == 403

    response = rmaker.make_request(
        path='/api/v1/service_announcements_public'
    )
    assert response.status_code == 200
    filtered = list(filter(lambda x: x['id'] == pri_data.known_announcement_id, response.json))
    assert filtered[0]['id'] == pri_data.known_announcement_id

    # admin
    response = rmaker.make_authenticated_admin_request(
        method='DELETE',
        path='/api/v1/service_announcements_admin/%s' % pri_data.known_announcement_id
    )
    assert response.status_code == 200

    response = rmaker.make_request(
        path='/api/v1/service_announcements_public'
    )
    assert response.status_code == 200
    assert len(response.json) == 0


def test_post_service_announcement_admin(rmaker: RequestMaker, pri_data: PrimaryData):
    data = {
        'subject': 'test subject',
        'content': 'test announcement',
        'level': 5,
        'targets': 'welcome-header',
        'is_enabled': True,
        'is_public': True
    }

    # anonymous
    response = rmaker.make_request(
        method='POST',
        path='/api/v1/service_announcements_admin',
        data=json.dumps(data)
    )
    assert response.status_code == 401

    # user
    response = rmaker.make_authenticated_user_request(
        method='POST',
        path='/api/v1/service_announcements_admin',
        data=json.dumps(data)
    )
    assert response.status_code == 403

    # workspace-owner
    response = rmaker.make_authenticated_workspace_owner_request(
        method='POST',
        path='/api/v1/service_announcements_admin',
        data=json.dumps(data)
    )
    assert response.status_code == 403

    # admin
    response = rmaker.make_authenticated_admin_request(
        method='POST',
        path='/api/v1/service_announcements_admin',
        data=json.dumps(data)
    )
    assert response.status_code == 200

    response = rmaker.make_authenticated_user_request(
        path='/api/v1/service_announcements_public'
    )
    assert response.status_code == 200
    assert len(response.json) == 2
