from tests.conftest import PrimaryData, RequestMaker


def test_headers(rmaker: RequestMaker, pri_data: PrimaryData):
    """Test that we set headers for content caching and security"""
    response = rmaker.make_request(path='/api/v1/config')

    required_headers = ('Cache-Control', 'Expires', 'Strict-Transport-Security', 'Content-Security-Policy')
    for h in required_headers:
        assert h in response.headers.keys()
