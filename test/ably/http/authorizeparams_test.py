import pytest

from ably.pubsub.server import IncompatibleClientIdException, TokenDetails, create_http_client


@pytest.fixture(scope='session', autouse=True)
def test_app_setup():
    """Avoid creating a sandbox application for these offline calls."""
    yield


def callback_client(received, token_client_id):
    async def auth_callback(token_params):
        received.append(token_params)
        return TokenDetails(token='a-token', client_id=token_client_id)

    return create_http_client(auth_callback=auth_callback, client_id='configured')


async def test_authorize_fills_the_configured_client_id_without_mutating_params():
    """RSA10h: Auth#clientId is the default clientId, applied to a copy of the caller's params."""
    received = []
    client = callback_client(received, 'configured')
    token_params = {'ttl': 60000}
    try:
        await client.auth.authorize(token_params)
        assert received[0] == {'ttl': 60000, 'client_id': 'configured'}
        assert token_params == {'ttl': 60000}
    finally:
        await client.close()


async def test_authorize_keeps_an_explicit_client_id():
    """RSA10b, RSA10j: an explicit clientId reaches the callback, and a conflicting token fails 40102."""
    received = []
    client = callback_client(received, 'explicit')
    token_params = {'client_id': 'explicit'}
    try:
        with pytest.raises(IncompatibleClientIdException) as excinfo:
            await client.auth.authorize(token_params)
        assert excinfo.value.code == 40102
        assert received[0]['client_id'] == 'explicit'
        assert token_params == {'client_id': 'explicit'}
    finally:
        await client.close()


async def test_given_token_params_replace_the_defaults():
    """RSA8e, RSA9h: default_token_params apply only when no params are given."""
    received = []

    async def auth_callback(token_params):
        received.append(token_params)
        return 'a-token'

    defaults = {'ttl': 1800000, 'capability': '{"*":["subscribe"]}'}
    key_client = create_http_client(key='app.key:secret', default_token_params=dict(defaults))
    callback_client = create_http_client(auth_callback=auth_callback, default_token_params=dict(defaults))
    try:
        token_request = await key_client.auth.create_token_request()
        assert (token_request.ttl, token_request.capability) == (1800000, '{"*": ["subscribe"]}')

        token_request = await key_client.auth.create_token_request({'ttl': 600000})
        assert (token_request.ttl, token_request.capability) == (600000, None)

        await callback_client.auth.request_token()
        await callback_client.auth.request_token({'ttl': 600000})
        assert received == [defaults, {'ttl': 600000}]
    finally:
        await key_client.close()
        await callback_client.close()
