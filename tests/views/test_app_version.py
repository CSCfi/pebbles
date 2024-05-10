import json

from pyfakefs.fake_filesystem_unittest import Patcher

from tests.conftest import RequestMaker


def test_get(rmaker: RequestMaker):
    # mimic image build generated file
    with Patcher() as patcher:
        patcher.fs.create_file(
            'app-version.json',
            contents=json.dumps(dict(appVersion='1.2.34'))
        )
        response = rmaker.make_request(path='/api/v1/version')
        assert response.status_code == 401

        response = rmaker.make_authenticated_user_request(
            path='/api/v1/version',
        )
        assert response.status_code == 200
        assert response.json == dict(appVersion='1.2.34')

    # test behaviour with a missing file
    response = rmaker.make_authenticated_user_request(
        path='/api/v1/version',
    )
    assert response.status_code == 200
    assert response.json == dict(appVersion='not-set')
