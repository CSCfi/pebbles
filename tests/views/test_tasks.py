import json

from sqlalchemy import select

from pebbles.models import db, Task
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
        kind='workspace_volume_backup',
        data=[dict(some_key='value1')]
    )
    task2 = dict(
        kind='workspace_volume_backup',
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
    assert response.json['kind'] == 'workspace_volume_backup'
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


def test_add_results_to_tasks(rmaker: RequestMaker, pri_data: PrimaryData):
    t1_data = dict(
        kind='workspace_volume_backup',
        data=[dict(some_key='value1')]
    )
    # add task 1
    response = rmaker.make_authenticated_admin_request(
        method='POST',
        path='/api/v1/tasks',
        data=json.dumps(t1_data)
    )
    assert response.status_code == 200
    t1_id = response.json.get('id')

    t2_data = dict(
        kind='workspace_volume_backup',
        data=[dict(some_key='value1')]
    )
    # add task 2
    response = rmaker.make_authenticated_admin_request(
        method='POST',
        path='/api/v1/tasks',
        data=json.dumps(t2_data)
    )
    assert response.status_code == 200
    t2_id = response.json.get('id')

    results_list_t1 = ['some text', 'new text', '...and even more of text']
    results_list_t2 = ['1', '2', '3']

    for i in range(max(len(results_list_t1), len(results_list_t2))):
        # add text to results
        if i < len(results_list_t1):
            response = rmaker.make_authenticated_admin_request(
                method='PUT',
                path='/api/v1/tasks/%s/results' % t1_id,
                data=json.dumps(dict(results=results_list_t1[i]))
            )
            assert response.status_code == 200
        if i < len(results_list_t2):
            response = rmaker.make_authenticated_admin_request(
                method='PUT',
                path='/api/v1/tasks/%s/results' % t2_id,
                data=json.dumps(dict(results=results_list_t2[i]))
            )
            assert response.status_code == 200

    # query tasks from database and check that results were appended correctly
    t1 = db.session.scalar(select(Task).where(Task.id == t1_id))
    assert t1.results == results_list_t1
    t2 = db.session.scalar(select(Task).where(Task.id == t2_id))
    assert t2.results == results_list_t2

    # Add a task, append a multiline result string and check that it is there in the database
    t3_data = dict(
        kind='workspace_volume_backup',
        data=[dict(some_key='value1')]
    )
    response = rmaker.make_authenticated_admin_request(
        method='POST',
        path='/api/v1/tasks',
        data=json.dumps(t3_data)
    )
    assert response.status_code == 200
    t3_id = response.json.get('id')
    response = rmaker.make_authenticated_admin_request(
        method='PUT',
        path='/api/v1/tasks/%s/results' % t3_id,
        data=json.dumps(dict(results='\n'.join(['line1', 'line2'])))
    )
    assert response.status_code == 200
    t3 = db.session.scalar(select(Task).where(Task.id == t3_id))
    assert len(t3.results) == 2
    assert t3.results[0] == 'line1'
    assert t3.results[1] == 'line2'

    # Query task that does not exist
    response = rmaker.make_authenticated_admin_request(
        method='PUT',
        path='/api/v1/tasks/%s/results' % '666',
        data=json.dumps(dict(results=''))
    )
    assert response.status_code == 404
