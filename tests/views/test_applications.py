import json
import uuid

from pebbles.models import Application
from tests.conftest import PrimaryData, RequestMaker


def test_get_applications(rmaker: RequestMaker, pri_data: PrimaryData):
    # Test listing applications
    # We test role dependent marshaling logic with checking the presence of 'template_id' and 'workspace_pseudonym'
    # attributes.

    # Anonymous
    response = rmaker.make_request(path='/api/v1/applications')
    assert response.status_code == 401

    # Authenticated User for Workspace 1
    response = rmaker.make_authenticated_user_request(path='/api/v1/applications')
    assert response.status_code == 200
    assert len(response.json) == 4
    response = rmaker.make_authenticated_user_request(
        path='/api/v1/applications?workspace_id=%s' % pri_data.known_workspace_id)
    assert response.status_code == 200
    assert len(response.json) == 3
    assert len([app for app in response.json if app.get('template_id')]) == 0
    assert len([app for app in response.json if app.get('attribute_limits')]) == 0

    # Authenticated Workspace Owner for Workspace 1(with 4 apps), user is also an unprivileged member for Workspace 2
    response = rmaker.make_authenticated_workspace_owner_request(path='/api/v1/applications')
    assert response.status_code == 200
    assert len(response.json) == 6
    assert len([app for app in response.json if app.get('template_id')]) == 4
    assert len([app for app in response.json if app.get('attribute_limits')]) == 4
    assert len([app for app in response.json if app.get('workspace_pseudonym')]) == 0

    response = rmaker.make_authenticated_workspace_owner_request(
        path='/api/v1/applications?workspace_id=%s' % pri_data.known_workspace_id)
    assert response.status_code == 200
    assert len(response.json) == 4
    assert len([app for app in response.json if app.get('template_id')]) == 4
    assert len([app for app in response.json if app.get('workspace_pseudonym')]) == 0

    # Admin
    response = rmaker.make_authenticated_admin_request(path='/api/v1/applications')
    assert response.status_code == 200
    assert len(response.json) == 10
    response = rmaker.make_authenticated_admin_request(
        path='/api/v1/applications?workspace_id=%s' % pri_data.known_workspace_id)
    assert response.status_code == 200
    assert len(response.json) == 4
    assert len([app for app in response.json if app.get('workspace_pseudonym')]) == 4

    response = rmaker.make_authenticated_admin_request(path='/api/v1/applications?show_all=true')
    assert response.status_code == 200
    assert len(response.json) == 12
    assert len([app for app in response.json if app.get('workspace_pseudonym')]) == 12


def test_get_application(rmaker: RequestMaker, pri_data: PrimaryData):
    # Test getting a single application
    # We test role dependent marshaling logic with checking the presence of 'template_id' and 'workspace_pseudonym'
    # attributes.

    # Anonymous
    response = rmaker.make_request(path='/api/v1/applications/%s' % pri_data.known_application_id)
    assert response.status_code == 401

    # Authenticated
    response = rmaker.make_authenticated_user_request(path='/api/v1/applications/%s' % pri_data.known_application_id)
    assert response.status_code == 200
    assert response.json.get('id')
    assert not response.json.get('template_id')

    # Authenticated Workspace Owner for Workspace 1(with 4 apps) and Normal User for Workspace 2
    response = rmaker.make_authenticated_workspace_owner_request(
        path='/api/v1/applications/%s' % pri_data.known_application_id
    )
    assert response.status_code == 200
    assert response.json.get('id')
    assert response.json.get('template_id')
    response = rmaker.make_authenticated_workspace_owner_request(
        path='/api/v1/applications/%s' % pri_data.known_application_id_g2
    )
    assert response.status_code == 200
    assert response.json.get('id')
    assert not response.json.get('template_id')

    # Admin
    response = rmaker.make_authenticated_admin_request(path='/api/v1/applications/%s' % pri_data.known_application_id)
    assert response.status_code == 200
    assert response.json.get('workspace_pseudonym')

    # non-existing application
    # Anonymous
    response = rmaker.make_request(path='/api/v1/applications/%s' % uuid.uuid4().hex)
    assert response.status_code == 401
    # Authenticated
    response = rmaker.make_authenticated_user_request(path='/api/v1/applications/%s' % uuid.uuid4().hex)
    assert response.status_code == 404
    # Admin
    response = rmaker.make_authenticated_admin_request(path='/api/v1/applications/%s' % uuid.uuid4().hex)
    assert response.status_code == 404


def test_get_application_archived(rmaker: RequestMaker, pri_data: PrimaryData):
    # Anonymous
    response = rmaker.make_request(path='/api/v1/applications/%s?show_all=1' % pri_data.known_application_id_archived)
    assert response.status_code == 401
    # Authenticated, user not in workspace
    response = rmaker.make_authenticated_user_request(
        path='/api/v1/applications/%s?show_all=1' % pri_data.known_application_id_archived)
    assert response.status_code == 404
    # Authenticated, user is workspace owner
    response = rmaker.make_authenticated_workspace_owner2_request(
        path='/api/v1/applications/%s?show_all=1' % pri_data.known_application_id_archived)
    assert response.status_code == 404
    # Admin
    response = rmaker.make_authenticated_admin_request(
        path='/api/v1/applications/%s?show_all=1' % pri_data.known_application_id_archived)
    assert response.status_code == 200
    # Admin without show_all
    response = rmaker.make_authenticated_admin_request(
        path='/api/v1/applications/%s' % pri_data.known_application_id_archived)
    assert response.status_code == 404


def test_get_application_labels(rmaker: RequestMaker, pri_data: PrimaryData):
    # Authenticated
    response = rmaker.make_authenticated_user_request(path='/api/v1/applications/%s' % pri_data.known_application_id)
    assert response.status_code == 200
    labels = response.json['labels']
    expected_labels = ['label1', 'label with space', 'label2']
    assert labels == expected_labels, 'label array matches'


def test_create_application(rmaker: RequestMaker, pri_data: PrimaryData):
    # Anonymous
    data = dict(name='test_application_1', config='', template_id=pri_data.known_template_id,
                workspace_id=pri_data.known_workspace_id)
    response = rmaker.make_request(
        method='POST',
        path='/api/v1/applications',
        data=json.dumps(data))
    assert response.status_code == 401
    # Authenticated
    data = dict(name='test_application_1', config='', template_id=pri_data.known_template_id,
                workspace_id=pri_data.known_workspace_id)
    response = rmaker.make_authenticated_user_request(
        method='POST',
        path='/api/v1/applications',
        data=json.dumps(data))
    assert response.status_code == 403
    # Workspace Owner 1
    data = dict(name='test_application_1', maximum_lifetime=3600, config={'foo': 'bar'},
                template_id=pri_data.known_template_id, workspace_id=pri_data.known_workspace_id)
    data_2 = dict(name='test_application_2', maximum_lifetime=3600, config={'foo': 'bar'},
                  template_id=pri_data.known_template_id, workspace_id=pri_data.known_workspace_id)
    response = rmaker.make_authenticated_workspace_owner_request(
        method='POST',
        path='/api/v1/applications',
        data=json.dumps(data))
    assert response.status_code == 200
    # Workspace Owner 2 (extra owner added to workspace 1)
    response = rmaker.make_authenticated_workspace_owner2_request(
        method='POST',
        path='/api/v1/applications',
        data=json.dumps(data))
    assert response.status_code == 200
    # check if possible to create more applications than quota in the workspace
    response = rmaker.make_authenticated_workspace_owner2_request(
        method='POST',
        path='/api/v1/applications',
        data=json.dumps(data_2))
    assert response.status_code == 422
    # Admin ignores quota
    data = dict(name='test_application_1', maximum_lifetime=3600, config={'foo': 'bar'},
                template_id=pri_data.known_template_id, workspace_id=pri_data.known_workspace_id)
    response = rmaker.make_authenticated_admin_request(
        method='POST',
        path='/api/v1/applications',
        data=json.dumps(data))
    assert response.status_code == 200


def test_delete_application(rmaker: RequestMaker, pri_data: PrimaryData):
    # Anonymous
    response = rmaker.make_request(
        method='DELETE',
        path='/api/v1/applications/%s' % pri_data.known_application_id
    )
    assert response.status_code == 401

    # Authenticated
    response = rmaker.make_authenticated_user_request(
        method='DELETE',
        path='/api/v1/applications/%s' % pri_data.known_application_id
    )
    assert response.status_code == 403

    # Workspace Owner 1, an application in some other workspace
    response = rmaker.make_authenticated_workspace_owner_request(
        method='DELETE',
        path='/api/v1/applications/%s' % pri_data.known_application_id_g2
    )
    assert response.status_code == 403

    # Workspace Owner 1
    response = rmaker.make_authenticated_workspace_owner_request(
        method='DELETE',
        path='/api/v1/applications/%s' % pri_data.known_application_id
    )
    assert response.status_code == 200

    # Workspace Owner 2 (extra owner added to workspace 1)
    response = rmaker.make_authenticated_workspace_owner2_request(
        method='DELETE',
        path='/api/v1/applications/%s' % pri_data.known_application_id_2
    )
    assert response.status_code == 200

    # Admin
    response = rmaker.make_authenticated_admin_request(
        method='DELETE',
        path='/api/v1/applications/%s' % 'idontexist'
    )
    assert response.status_code == 404
    response = rmaker.make_authenticated_admin_request(
        method='DELETE',
        path='/api/v1/applications/%s' % pri_data.known_application_id_g2
    )
    assert response.status_code == 200


def test_modify_application_activate(rmaker: RequestMaker, pri_data: PrimaryData):
    data = {
        'name': 'test_application_activate',
        'maximum_lifetime': 3600,
        'config': {
            "maximum_lifetime": 0
        },
        'template_id': pri_data.known_template_id,
        'workspace_id': pri_data.known_workspace_id
    }

    # Authenticated Normal User
    put_response = rmaker.make_authenticated_user_request(
        method='PUT',
        path='/api/v1/applications/%s' % pri_data.known_application_id_disabled,
        data=json.dumps(data))
    assert put_response.status_code == 403
    # Workspace owner not an owner of the application workspace 2
    put_response = rmaker.make_authenticated_workspace_owner_request(
        method='PUT',
        path='/api/v1/applications/%s' % pri_data.known_application_id_disabled_2,
        data=json.dumps(data))
    assert put_response.status_code == 403
    # Workspace Owner is an owner of the application workspace 1
    put_response = rmaker.make_authenticated_workspace_owner_request(
        method='PUT',
        path='/api/v1/applications/%s' % pri_data.known_application_id_disabled,
        data=json.dumps(data))
    assert put_response.status_code == 200
    # Workspace owner 2 is part of the application workspace 1 as an additional owner
    put_response = rmaker.make_authenticated_workspace_owner2_request(
        method='PUT',
        path='/api/v1/applications/%s' % pri_data.known_application_id_disabled,
        data=json.dumps(data))
    assert put_response.status_code == 200
    # Workspace owner 2 owner of the application workspace 2
    put_response = rmaker.make_authenticated_workspace_owner2_request(
        method='PUT',
        path='/api/v1/applications/%s' % pri_data.known_application_id_disabled,
        data=json.dumps(data))
    assert put_response.status_code == 200
    # Admin
    put_response = rmaker.make_authenticated_admin_request(
        method='PUT',
        path='/api/v1/applications/%s' % pri_data.known_application_id_disabled,
        data=json.dumps(data))
    assert put_response.status_code == 200

    application = Application.query.filter_by(id=pri_data.known_application_id_disabled).first()
    assert not application.is_enabled


def test_create_application_workspace_owner_invalid_data(rmaker: RequestMaker, pri_data: PrimaryData):
    invalid_form_data = [
        dict(
            name='lifetime too long',
            config=dict(maximum_lifetime=3600 * 14),
            template_id=pri_data.known_template_id,
            workspace_id=pri_data.known_workspace_id
        ),
        dict(
            name='lifetime negative',
            config=dict(maximum_lifetime=-1),
            template_id=pri_data.known_template_id,
            workspace_id=pri_data.known_workspace_id
        ),
        dict(
            name='memory negative',
            config=dict(maximum_lifetime=3600, memory_gib=-1),
            template_id=pri_data.known_template_id,
            workspace_id=pri_data.known_workspace_id
        ),
        dict(
            name='memory too big',
            config=dict(maximum_lifetime=3600, memory_gib=17),
            template_id=pri_data.known_template_id,
            workspace_id=pri_data.known_workspace_id
        ),
    ]
    for data in invalid_form_data:
        response = rmaker.make_authenticated_workspace_owner_request(
            method='POST',
            path='/api/v1/applications',
            data=json.dumps(data))
        assert response.status_code == 422, data['name']

    # Workspace owner is a user but not the owner of the workspace with id : known_workspace_id_2
    invalid_workspace_data = dict(name='test_application_2', maximum_lifetime=3600, config={"name": "foo"},
                                  template_id=pri_data.known_template_id, workspace_id=pri_data.known_workspace_id_2)
    response = rmaker.make_authenticated_workspace_owner_request(
        method='POST',
        path='/api/v1/applications',
        data=json.dumps(invalid_workspace_data))
    assert response.status_code == 403

    put_response = rmaker.make_authenticated_workspace_owner_request(
        method='PUT',
        path='/api/v1/applications/%s' % pri_data.known_application_id_g2,
        data=json.dumps(invalid_workspace_data))
    assert put_response.status_code == 403


def test_create_application_workspace_owner_quota(rmaker: RequestMaker, pri_data: PrimaryData):
    # Workspace Owner 1

    # delete all existing applications, these should no longer be counted towards quota after that
    ws_apps = rmaker.make_authenticated_workspace_owner_request(
        path='/api/v1/applications?workspace_id=%s' % pri_data.known_workspace_id
    )
    for application in ws_apps.json:
        resp = rmaker.make_authenticated_workspace_owner_request(
            method='DELETE',
            path='/api/v1/applications/%s' % application['id']
        )
        assert not 200 != resp.status_code
    ws_apps = rmaker.make_authenticated_workspace_owner_request(
        path='/api/v1/applications?workspace_id=%s' % pri_data.known_workspace_id
    )
    data = dict(name='test_application_1', maximum_lifetime=3600, config={'foo': 'bar'},
                template_id=pri_data.known_template_id, workspace_id=pri_data.known_workspace_id)

    # we should be able to create 6
    for i in range(6):
        response = rmaker.make_authenticated_workspace_owner_request(
            method='POST',
            path='/api/v1/applications',
            data=json.dumps(data))
        assert response.status_code == 200

    # ...and the 7th should fail
    response = rmaker.make_authenticated_workspace_owner_request(
        method='POST',
        path='/api/v1/applications',
        data=json.dumps(data))
    assert response.status_code == 422


def test_copy_applications(rmaker: RequestMaker, pri_data: PrimaryData):
    # Authenticated User
    response = rmaker.make_authenticated_user_request(
        method='PUT',
        path='/api/v1/applications/%s/copy' % pri_data.known_application_id)
    assert response.status_code == 403

    # Authenticated Workspace Owner
    response = rmaker.make_authenticated_workspace_owner_request(
        method='PUT',
        path='/api/v1/applications/%s/copy' % pri_data.known_application_id)
    assert response.status_code == 200

    # Admin
    response = rmaker.make_authenticated_admin_request(
        method='PUT',
        path='/api/v1/applications/%s/copy' % pri_data.known_application_id)
    assert response.status_code == 200

    # Quota is full, owner cannot copy anymore
    response = rmaker.make_authenticated_workspace_owner_request(
        method='PUT',
        path='/api/v1/applications/%s/copy' % pri_data.known_application_id)
    assert response.status_code == 422

    # Admin can still copy
    response = rmaker.make_authenticated_admin_request(
        method='PUT',
        path='/api/v1/applications/%s/copy' % pri_data.known_application_id)
    assert response.status_code == 200


def test_copy_applications_to_another_workspace(rmaker: RequestMaker, pri_data: PrimaryData):
    # Authenticated User
    response = rmaker.make_authenticated_user_request(
        method='PUT',
        path='/api/v1/applications/%s/copy?workspace_id=%s' %
             (pri_data.known_application_id, pri_data.known_workspace_id))
    assert response.status_code == 403

    # Authenticated Workspace Owner to same workspace
    response = rmaker.make_authenticated_workspace_owner_request(
        method='PUT',
        path='/api/v1/applications/%s/copy?workspace_id=%s' %
             (pri_data.known_application_id, pri_data.known_workspace_id))
    assert response.status_code == 200

    # Authenticated Workspace Owner to non-managed workspace
    response = rmaker.make_authenticated_workspace_owner_request(
        method='PUT',
        path='/api/v1/applications/%s/copy?workspace_id=%s' %
             (pri_data.known_application_id, pri_data.known_workspace_id_2))
    assert response.status_code == 403

    # Authenticated Workspace Manager to another managed workspace
    response = rmaker.make_authenticated_workspace_owner2_request(
        method='PUT',
        path='/api/v1/applications/%s/copy?workspace_id=%s' %
             (pri_data.known_application_id, pri_data.known_workspace_id_2))
    assert response.status_code == 200

    # Authenticated user to another workspace with manager role (should fail)
    response = rmaker.make_authenticated_workspace_owner2_request(
        method='PUT',
        path='/api/v1/applications/%s/copy?workspace_id=%s' %
             (pri_data.known_application_public, pri_data.known_workspace_id_2))
    assert response.status_code == 403

    # Admin
    response = rmaker.make_authenticated_admin_request(
        method='PUT',
        path='/api/v1/applications/%s/copy?workspace_id=%s' % (
            pri_data.known_application_id, pri_data.known_workspace_id))
    assert response.status_code == 200


def test_application_attribute_limits(rmaker: RequestMaker, pri_data: PrimaryData):
    data = dict(
        attribute_limits=[
            dict(name="maximum_lifetime", min=0, max=43200),
            dict(name="memory_gib", min=0, max=8)
        ])

    # Authenticated User
    response = rmaker.make_authenticated_user_request(
        method='PUT',
        path='/api/v1/applications/%s/attribute_limits' % pri_data.known_application_id,
        data=json.dumps(data)
    )
    assert response.status_code == 403

    # Authenticated Workspace Owner
    response = rmaker.make_authenticated_workspace_owner_request(
        method='PUT',
        path='/api/v1/applications/%s/attribute_limits' % pri_data.known_application_id,
        data=json.dumps(data)
    )
    assert response.status_code == 403

    # Admin, valid request
    response = rmaker.make_authenticated_admin_request(
        method='PUT',
        path='/api/v1/applications/%s/attribute_limits' % pri_data.known_application_id,
        data=json.dumps(data)
    )
    assert response.status_code == 200

    # Admin, conflict with existing application config. The application has to be modified first,
    # otherwise we'd end up with illegal value in application config.
    data = dict(
        attribute_limits=[
            dict(name="maximum_lifetime", min=0, max=1),
        ])
    response = rmaker.make_authenticated_admin_request(
        method='PUT',
        path='/api/v1/applications/%s/attribute_limits' % pri_data.known_application_id,
        data=json.dumps(data)
    )
    assert response.status_code == 422

    # Admin, invalid format for new attribute limits
    invalid_data = [
        dict(attribute_limits=[dict(name="maximum_lifetime", max=43200)]),
        dict(limits=[dict(name="maximum_lifetime", min=0, max=43200)]),
        dict(attribute_limits="maximum_lifetime=43200"),
        dict(attribute_limits=[dict(name="maximum_lifetime", min=10, max=9)]),
        dict(attribute_limits=[dict(name="maximum_lifetime", min="0", max="10")]),
    ]
    for data in invalid_data:
        response = rmaker.make_authenticated_admin_request(
            method='PUT',
            path='/api/v1/applications/%s/attribute_limits' % pri_data.known_application_id,
            data=json.dumps(data)
        )
        assert response.status_code == 422
