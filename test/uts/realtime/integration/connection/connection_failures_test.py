"""Derived from uts/realtime/integration/connection/connection_failures_test.md in ably/specification.

Spec points: RTN14a, RTN14g

Both tests present the sandbox with a key naming an application that does not exist, and
both are answered the same way: the server closes the websocket with a policy violation and
the SDK reports `40101 / 401 "unable to handle request; no application id found in
request"`. Each specification admits that code — RTN14a as one of `40005` or `40101`, RTN14g
as anything outside the token-error range `40140`-`40149` — so the two tests differ in what
they assert about one shared server response rather than in the response they provoke.

Neither test asks for the `realtime_sandbox` fixture the specification's `BEFORE ALL
TESTS` provisions: the credentials under test name an application that was never
created, so the provisioned app has nothing to do with either connection.

A failed connect leaves a `Task exception was never retrieved` line behind it:
`WebSocketTransport.close` sends a CLOSE over a socket the server has already closed with
1008. It is noise from teardown, not a failure of either test.
"""

from ably.realtime.connection import ConnectionState
from test.uts.helpers.client import await_connection_state, sandbox_realtime_client

# The wait the specification gives each connect attempt.
FAIL_TIMEOUT = 15.0


# UTS: realtime/integration/RTN14a/invalid-key-failed-0
async def test_rtn14a_invalid_key_failed():
    client = sandbox_realtime_client('invalid.key:secret', auto_connect=False)

    client.connect()
    await await_connection_state(client, ConnectionState.FAILED, FAIL_TIMEOUT)

    assert client.connection.state is ConnectionState.FAILED
    assert client.connection.error_reason is not None
    assert client.connection.error_reason.code in (40005, 40101)
    assert client.connection.error_reason.status_code in (401, 404)


# UTS: realtime/integration/RTN14g/revoked-key-failed-0
async def test_rtn14g_revoked_key_failed():
    client = sandbox_realtime_client('nonexistent.keyname:keysecret', auto_connect=False)

    client.connect()
    await await_connection_state(client, ConnectionState.FAILED, FAIL_TIMEOUT)

    assert client.connection.state is ConnectionState.FAILED
    assert client.connection.error_reason is not None
    # Outside the token-error range, so RTN14g and not RTN14b applies.
    assert client.connection.error_reason.code < 40140 or client.connection.error_reason.code >= 40150
