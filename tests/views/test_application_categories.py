from tests.conftest import PrimaryData, RequestMaker


def test_anonymous_get_application_categories(rmaker: RequestMaker, pri_data: PrimaryData):
    response = rmaker.make_request(
        path='/api/v1/application_categories'
    )
    assert response.status_code == 401


def test_user_application_categories(rmaker: RequestMaker, pri_data: PrimaryData):
    response = rmaker.make_authenticated_user_request(
        path='/api/v1/application_categories'
    )
    assert response.status_code == 200
    assert len(response.json) > 0
