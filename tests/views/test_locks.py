import json

from tests.conftest import PrimaryData, RequestMaker


def test_admin_acquire_lock(rmaker: RequestMaker, pri_data: PrimaryData):
    unique_id = 'abc123'
    response = rmaker.make_authenticated_admin_request(
        method='PUT',
        path='/api/v1/locks/%s' % unique_id,
        data=json.dumps(dict(owner='test'))
    )
    assert response.status_code == 200

    response2 = rmaker.make_authenticated_admin_request(
        method='PUT',
        path='/api/v1/locks/%s' % unique_id,
        data=json.dumps(dict(owner='test'))
    )
    assert response2.status_code == 409

    response3 = rmaker.make_authenticated_admin_request(
        method='DELETE',
        path='/api/v1/locks/%s' % unique_id
    )

    assert response3.status_code == 200

    response4 = rmaker.make_authenticated_admin_request(
        method='DELETE',
        path='/api/v1/locks/%s' % unique_id
    )

    assert response4.status_code == 404

    response = rmaker.make_authenticated_admin_request(
        method='PUT',
        path='/api/v1/locks/%s' % unique_id,
        data=json.dumps(dict(owner='test'))
    )
    assert response.status_code == 200

    # test deleting with an owner filter that does not match
    response = rmaker.make_authenticated_admin_request(
        method='DELETE',
        path='/api/v1/locks/%s?owner=foo' % unique_id
    )
    assert response.status_code == 404

    # test deleting with an owner filter
    response = rmaker.make_authenticated_admin_request(
        method='DELETE',
        path='/api/v1/locks/%s?owner=test' % unique_id
    )
    assert response.status_code == 200
