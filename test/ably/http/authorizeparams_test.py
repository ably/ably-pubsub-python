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
