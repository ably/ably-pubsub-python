from datetime import timedelta
from urllib.parse import parse_qs

import pytest
import respx
from httpx import Response

from ably.pubsub.server import create_http_client


@pytest.fixture(scope='session', autouse=True)
def test_app_setup():
    """Avoid creating a sandbox application for these mocked requests."""
    yield


@pytest.mark.parametrize('method', ['GET', 'POST'])
@respx.mock
async def test_token_params_reach_auth_url_under_wire_names(method):
    """RSA8c1a: send TokenParams to the auth URL as another SDK would."""
    auth_url = 'https://auth.example.test/token'
    client = create_http_client(auth_url=auth_url, auth_method=method, client_id='alice',
                                auth_params={'clientId': 'overridden', 'extra': 'kept'})
    auth_route = respx.request(method, auth_url).mock(return_value=Response(
        200, json={'token': 'a-token', 'clientId': 'alice'}))
    try:
        await client.auth.authorize({
            'ttl': timedelta(hours=1),
            'capability': {'channel': ['subscribe', 'publish']},
            'nonce': 'a-nonce',
            'timestamp': 1234567890000,
        })
        request = auth_route.calls.last.request
        if method == 'GET':
            sent = parse_qs(request.url.query.decode('utf-8'))
        else:
            sent = parse_qs(request.content.decode('utf-8'))
        assert sent == {
            'clientId': ['alice'],
            'ttl': ['3600000'],
            'capability': ['{"channel": ["publish", "subscribe"]}'],
            'nonce': ['a-nonce'],
            'timestamp': ['1234567890000'],
            'extra': ['kept'],
        }
    finally:
        await client.close()
