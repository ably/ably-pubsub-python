import pytest
import respx
from httpx import Response

from ably import AblyRest


@pytest.fixture(scope='session', autouse=True)
def test_app_setup():
    """Avoid creating a sandbox application for these mocked requests."""
    yield


@pytest.mark.parametrize('method', ['GET', 'POST'])
@pytest.mark.parametrize('binary', [False, True])
@pytest.mark.parametrize('override', [False, True])
@respx.mock
async def test_auth_headers_are_only_sent_to_auth_url(method, binary, override):
    """Keep custom headers on the auth URL across methods, protocols, and overrides."""
    auth_url = 'https://auth.example.test/token'
    headers = {'Authorization': 'Bearer external-auth-token', 'X-Custom-Auth': 'custom-value'}
    options = {'auth_url': auth_url, 'auth_method': method, 'use_binary_protocol': binary}
    if not override:
        options['auth_headers'] = headers
    client = AblyRest(**options)
    auth_route = respx.request(method, auth_url).mock(return_value=Response(200, json={
        'keyName': 'app.key', 'nonce': 'nonce', 'timestamp': 123456789,
        'mac': 'signed-request', 'capability': '{"*":["*"]}',
    }))
    token_route = respx.post('https://main.realtime.ably.net/keys/app.key/requestToken').mock(
        return_value=Response(200, json={'token': 'ably-token'}))
    try:
        result = await client.auth.request_token(**({'auth_headers': headers} if override else {}))
        assert result.token == 'ably-token'
        for name, value in headers.items():
            assert auth_route.calls.last.request.headers[name] == value
            assert name not in token_route.calls.last.request.headers
        expected_type = 'application/x-msgpack' if binary else 'application/json'
        assert token_route.calls.last.request.headers['Content-Type'] == expected_type
        assert headers == {'Authorization': 'Bearer external-auth-token', 'X-Custom-Auth': 'custom-value'}
    finally:
        await client.close()
