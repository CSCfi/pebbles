import json

from tests.conftest import PrimaryData, RequestMaker


def test_get_alerts_access(rmaker: RequestMaker, pri_data: PrimaryData):
    response = rmaker.make_request(
        path='/api/v1/alerts'
    )
    assert response.status_code == 401

    response = rmaker.make_authenticated_user_request(
        path='/api/v1/alerts'
    )
    assert response.status_code == 403

    response = rmaker.make_authenticated_workspace_owner_request(
        path='/api/v1/alerts'
    )
    assert response.status_code == 403


def test_alerts_admin(rmaker: RequestMaker, pri_data: PrimaryData):
    alert1 = dict(
        target='cluster-1',
        source='prometheus',
        status='firing',
        data=dict()
    )
    alert2 = dict(
        target='cluster-2',
        source='prometheus',
        status='ok',
        data=dict(name='alert2')
    )
    alert3 = dict(
        target='cluster-1',
        source='prometheus',
        status='firing',
        data=dict(name='alert3')
    )
    # add alerts
    response = rmaker.make_authenticated_admin_request(
        method='POST',
        path='/api/v1/alerts',
        data=json.dumps([alert1, alert2, alert3])
    )
    assert response.status_code == 200
    alert1['id'] = response.json[0].get('id')
    alert2['id'] = response.json[1].get('id')
    alert3['id'] = response.json[2].get('id')

    # query a single alert
    response = rmaker.make_authenticated_admin_request(
        path='/api/v1/alerts/%s' % (alert1['id']),
    )
    assert response.status_code == 200
    assert response.json['target'] == 'cluster-1'
    assert response.json['source'] == 'prometheus'

    # query list
    response = rmaker.make_authenticated_admin_request(
        path='/api/v1/alerts',
    )
    assert response.status_code == 200
    assert len(response.json) == 3

    # modify alert
    alert1['status'] = 'ok'
    response = rmaker.make_authenticated_admin_request(
        method='POST',
        path='/api/v1/alerts',
        data=json.dumps([alert1])
    )
    assert response.status_code == 200
    response = rmaker.make_authenticated_admin_request(
        path='/api/v1/alerts/%s' % (alert1['id']),
    )
    assert response.status_code == 200
    assert response.json['target'] == 'cluster-1'
    assert response.json['source'] == 'prometheus'
    assert response.json['status'] == 'ok'

    # invalid data
    alert1['target'] = None
    response = rmaker.make_authenticated_admin_request(
        method='POST',
        path='/api/v1/alerts',
        data=json.dumps([alert1])
    )
    assert response.status_code == 422

    # post alert_reset for cluster-1, archiving alert-3
    response = rmaker.make_authenticated_admin_request(
        method='POST',
        path='/api/v1/alert_reset/cluster-1/prometheus',
    )
    assert response.status_code == 200

    # query non-archived alerts
    response = rmaker.make_authenticated_admin_request(
        path='/api/v1/alerts',
    )
    assert response.status_code == 200
    assert len(response.json) == 2

    # include archived alerts
    response = rmaker.make_authenticated_admin_request(
        path='/api/v1/alerts?include_archived=1',
    )
    assert response.status_code == 200
    assert len(response.json) == 3
