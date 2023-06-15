import json
import uuid

from pebbles.models import ApplicationTemplate
from pebbles.models import db
from tests.conftest import PrimaryData, RequestMaker


def test_get_application_templates(rmaker: RequestMaker, pri_data: PrimaryData):
    # Anonymous
    response = rmaker.make_request(path='/api/v1/application_templates')
    assert response.status_code == 401
    # Authenticated User
    response = rmaker.make_authenticated_user_request(path='/api/v1/application_templates')
    assert response.status_code == 403
    # Authenticated Workspace Owner
    response = rmaker.make_authenticated_workspace_owner_request(path='/api/v1/application_templates')
    assert response.status_code == 200
    assert len(response.json) == 1
    # Admin
    response = rmaker.make_authenticated_admin_request(path='/api/v1/application_templates')
    assert response.status_code == 200
    assert len(response.json) == 2


def test_get_application_template(rmaker: RequestMaker, pri_data: PrimaryData):
    # Existing application
    # Anonymous
    response = rmaker.make_request(path='/api/v1/application_templates/%s' % pri_data.known_template_id)
    assert response.status_code == 401
    # Authenticated User
    response = rmaker.make_authenticated_user_request(
        path='/api/v1/application_templates/%s' % pri_data.known_template_id)
    assert response.status_code == 403
    # Workspace Owner
    response = rmaker.make_authenticated_workspace_owner_request(
        path='/api/v1/application_templates/%s' % pri_data.known_template_id)
    assert response.status_code == 200
    # Admin
    response = rmaker.make_authenticated_admin_request(
        path='/api/v1/application_templates/%s' % pri_data.known_template_id)
    assert response.status_code == 200

    # non-existing application
    # Anonymous
    response = rmaker.make_request(path='/api/v1/application_templates/%s' % uuid.uuid4().hex)
    assert response.status_code == 401
    # Authenticated User
    response = rmaker.make_authenticated_user_request(path='/api/v1/application_templates/%s' % uuid.uuid4().hex)
    assert response.status_code == 403
    # Workspace Owner
    response = rmaker.make_authenticated_workspace_owner_request(
        path='/api/v1/application_templates/%s' % uuid.uuid4().hex)
    assert response.status_code == 404
    # Admin
    response = rmaker.make_authenticated_admin_request(path='/api/v1/application_templates/%s' % uuid.uuid4().hex)
    assert response.status_code == 404


def test_create_application_template(rmaker: RequestMaker, pri_data: PrimaryData):
    # Anonymous
    data = {'name': 'test_application_template_1', 'base_config': ''}
    response = rmaker.make_request(
        method='POST',
        path='/api/v1/application_templates',
        data=json.dumps(data))
    assert response.status_code == 401
    # Authenticated User
    data = {'name': 'test_application_template_1', 'base_config': ''}
    response = rmaker.make_authenticated_user_request(
        method='POST',
        path='/api/v1/application_templates',
        data=json.dumps(data))
    assert response.status_code == 403
    # Authenticated Workspace Owner
    data = {'name': 'test_application_template_1', 'base_config': ''}
    response = rmaker.make_authenticated_workspace_owner_request(
        method='POST',
        path='/api/v1/application_templates',
        data=json.dumps(data))
    assert response.status_code == 403
    # Admin
    data = {'name': 'test_application_template_1', 'base_config': {'foo': 'bar'}}
    response = rmaker.make_authenticated_admin_request(
        method='POST',
        path='/api/v1/application_templates',
        data=json.dumps(data))
    assert response.status_code == 200
    # Admin
    data = {
        'name': 'test_application_template_2',
        'base_config': {'foo': 'bar', 'maximum_lifetime': 3600},
        'attribute_limits': dict(attribute_limits=[dict(name='maximum_lifetime', min=0, max=43200)])
    }
    response = rmaker.make_authenticated_admin_request(
        method='POST',
        path='/api/v1/application_templates',
        data=json.dumps(data))
    assert response.status_code == 200


def test_modify_application_template(rmaker: RequestMaker, pri_data: PrimaryData):
    t = ApplicationTemplate()
    t.name = 'TestTemplate'
    t.base_config = {'memory_limit': '512m', 'maximum_lifetime': 3600}
    t.attribute_limits = [dict(name='maximum_lifetime', min=0, max=43200)]
    t.is_enabled = True
    db.session.add(t)
    db.session.commit()

    # Anonymous
    data = {'name': 'test_application_template_1', 'base_config': ''}
    response = rmaker.make_request(
        method='PUT',
        path='/api/v1/application_templates/%s' % t.id,
        data=json.dumps(data))
    assert response.status_code == 401
    # Authenticated User
    data = {'name': 'test_application_template_1', 'base_config': ''}
    response = rmaker.make_authenticated_user_request(
        method='PUT',
        path='/api/v1/application_templates/%s' % t.id,
        data=json.dumps(data))
    assert response.status_code == 403
    # Authenticated Workspace Owner
    data = {'name': 'test_application_template_1', 'base_config': ''}
    response = rmaker.make_authenticated_workspace_owner_request(
        method='PUT',
        path='/api/v1/application_templates/%s' % t.id,
        data=json.dumps(data))
    assert response.status_code == 403
    # Admin
    data = {'name': 'test_application_template_1', 'base_config': {'foo': 'bar'}}
    response = rmaker.make_authenticated_admin_request(
        method='PUT',
        path='/api/v1/application_templates/%s' % t.id,
        data=json.dumps(data))
    assert response.status_code == 200
    # Admin
    data = {
        'name': 'test_application_template_2',
        'base_config': {'foo': 'bar', 'maximum_lifetime': 3600},
        'attribute_limits': dict(attribute_limits=[dict(name='maximum_lifetime', min=0, max=43200)]),
    }
    response = rmaker.make_authenticated_admin_request(
        method='PUT',
        path='/api/v1/application_templates/%s' % t.id,
        data=json.dumps(data))
    assert response.status_code == 200


def test_copy_application_template(rmaker: RequestMaker, pri_data: PrimaryData):
    # Authenticated User
    response = rmaker.make_authenticated_user_request(
        method='PUT',
        path='/api/v1/application_templates/template_copy/%s' % pri_data.known_template_id)
    assert response.status_code == 403
    # Authenticated Workspace Owner
    response = rmaker.make_authenticated_workspace_owner_request(
        method='PUT',
        path='/api/v1/application_templates/template_copy/%s' % pri_data.known_template_id)
    assert response.status_code == 403
    # Admin
    response = rmaker.make_authenticated_admin_request(
        method='PUT',
        path='/api/v1/application_templates/template_copy/%s' % pri_data.known_template_id)
    assert response.status_code == 200
