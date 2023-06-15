import json

from tests.conftest import PrimaryData, RequestMaker


def test_get_tasks_access(rmaker: RequestMaker, pri_data: PrimaryData):
    response = rmaker.make_request(
        path='/api/v1/tasks'
    )
    assert response.status_code == 401

    response = rmaker.make_authenticated_user_request(
        path='/api/v1/tasks'
    )
    assert response.status_code == 403

    response = rmaker.make_authenticated_workspace_owner_request(
        path='/api/v1/tasks'
    )
    assert response.status_code == 403


def test_tasks_admin(rmaker: RequestMaker, pri_data: PrimaryData):
    task1 = dict(
        kind='workspace_backup',
        data=[dict(some_key='value1')]
    )
    task2 = dict(
        kind='workspace_backup',
        data=[dict(some_key='value2')]
    )

    # add tasks
    t1_response = rmaker.make_authenticated_admin_request(
        method='POST',
        path='/api/v1/tasks',
        data=json.dumps(task1)
    )
    assert t1_response.status_code == 200

    t2_response = rmaker.make_authenticated_admin_request(
        method='POST',
        path='/api/v1/tasks',
        data=json.dumps(task2)
    )
    assert t2_response.status_code == 200

    # query a single task
    response = rmaker.make_authenticated_admin_request(
        path='/api/v1/tasks/%s' % t1_response.json.get('id'),
    )
    assert response.status_code == 200
    assert response.json['kind'] == 'workspace_backup'
    assert response.json['data'][0]['some_key'] == 'value1'

    # query list
    response = rmaker.make_authenticated_admin_request(
        path='/api/v1/tasks',
    )
    assert response.status_code == 200
    assert len(response.json) == 2

    # update task 1 state to processing
    response = rmaker.make_authenticated_admin_request(
        method='PATCH',
        path='/api/v1/tasks/%s' % t1_response.json.get('id'),
        data=json.dumps(dict(state='processing'))
    )
    assert response.status_code == 200

    # query list of all unfinished tasks
    response = rmaker.make_authenticated_admin_request(
        path='/api/v1/tasks?unfinished=1',
    )
    assert response.status_code == 200
    assert len(response.json) == 2

    # update task 1 state to finished
    response = rmaker.make_authenticated_admin_request(
        method='PATCH',
        path='/api/v1/tasks/%s' % t1_response.json.get('id'),
        data=json.dumps(dict(state='finished'))
    )
    assert response.status_code == 200

    # query list of all unfinished tasks
    response = rmaker.make_authenticated_admin_request(
        path='/api/v1/tasks?unfinished=1',
    )
    assert response.status_code == 200
    assert len(response.json) == 1

    # query list of all finished tasks
    response = rmaker.make_authenticated_admin_request(
        path='/api/v1/tasks?state=finished',
    )
    assert response.status_code == 200
    assert len(response.json) == 1

    # invalid data
    task1['kind'] = 'foo'
    response = rmaker.make_authenticated_admin_request(
        method='POST',
        path='/api/v1/tasks',
        data=json.dumps(task1)
    )
    assert response.status_code == 422

    # missing data
    task1['kind'] = None
    response = rmaker.make_authenticated_admin_request(
        method='POST',
        path='/api/v1/tasks',
        data=json.dumps(task1)
    )
    assert response.status_code == 422

    # try patching with invalid state
    response = rmaker.make_authenticated_admin_request(
        method='PATCH',
        path='/api/v1/tasks/%s' % t1_response.json.get('id'),
        data=json.dumps(dict(state='asdfasdf'))
    )
    assert response.status_code == 422
