from tests.conftest import PrimaryData, RequestMaker


def test_get_clusters(rmaker: RequestMaker, pri_data: PrimaryData):
    # Anonymous
    response = rmaker.make_request(path='/api/v1/clusters')
    assert response.status_code == 401
    # Authenticated
    response = rmaker.make_authenticated_user_request(path='/api/v1/clusters')
    assert response.status_code == 403
    # Admin
    response = rmaker.make_authenticated_admin_request(path='/api/v1/clusters')
    assert response.status_code == 200
