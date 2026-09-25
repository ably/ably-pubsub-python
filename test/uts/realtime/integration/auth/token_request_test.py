"""Derived from uts/realtime/integration/auth/token_request_test.md in ably/specification.

Spec points: RSA9, RSA9a, RSA9g

Both tests split the credentials in two: a REST client holding the API key signs
TokenRequests, and a realtime client with no key of its own connects with whatever that
callback hands it. Reaching CONNECTED is therefore the server's verdict on the HMAC the
creator computed, which is what RSA9g is about.

`Connection#id` is not a member of ably-python's `Connection`, so `connection_id` below
reads the value off the connection manager. See
[deviations.md](../../../deviations.md) for the house ruling on a missing accessor.

`create_token_request` takes the specification's `TokenParams` as a plain dict in snake
case, so `TokenParams(clientId: x)` is `{'client_id': x}`.
"""

from ably.realtime.connection import ConnectionState
from test.uts.helpers.client import await_connection_state, sandbox_realtime_client, sandbox_rest_client
from test.uts.helpers.sandbox import random_id

# The wait the specification gives each connection.
CONNECT_TIMEOUT = 15.0


def connection_id(client):
    """The specification's `connection.id`, held on the connection manager."""
    return client.connection.connection_manager.connection_id


# UTS: realtime/integration/RSA9a/token-request-server-accepted-0
async def test_rsa9a_token_request_server_accepted(realtime_sandbox):
    creator = sandbox_rest_client(realtime_sandbox.key_str)

    async def auth_callback(params):
        return await creator.auth.create_token_request()

    client = sandbox_realtime_client(auth_callback=auth_callback, auto_connect=False)

    client.connect()
    await await_connection_state(client, ConnectionState.CONNECTED, CONNECT_TIMEOUT)

    assert client.connection.state is ConnectionState.CONNECTED
    assert connection_id(client) is not None
    assert client.connection.error_reason is None


# UTS: realtime/integration/RSA9/token-request-with-clientid-0
async def test_rsa9_token_request_with_clientid(realtime_sandbox):
    test_client_id = 'token-request-client-' + random_id()

    creator = sandbox_rest_client(realtime_sandbox.key_str)

    async def auth_callback(params):
        return await creator.auth.create_token_request({'client_id': test_client_id})

    client = sandbox_realtime_client(
        auth_callback=auth_callback, client_id=test_client_id, auto_connect=False)

    client.connect()
    await await_connection_state(client, ConnectionState.CONNECTED, CONNECT_TIMEOUT)

    assert client.connection.state is ConnectionState.CONNECTED
    assert client.auth.client_id == test_client_id
