"""Derived from uts/realtime/integration/connection_lifecycle_test.md in ably/specification.

Spec points: RTN4b, RTN4c, RTN11, RTN12, RTN12a, RTN21

`Connection#id` and `Connection#key` do not exist in ably-python, so the two readers below
stand in for them; see [deviations.md](../../deviations.md) for the house ruling on a
missing accessor. Both answer `None` once the connection is closed, which is what the
graceful-close assertions read.

`connection.close()` is a coroutine that returns once the connection has reached CLOSED, so
CLOSING is already gone by the time it does and cannot be waited for afterwards. The close
test therefore records the state changes with a listener registered beforehand and asserts
the sequence on the recording, which is what the specification's two consecutive
`AWAIT_STATE` steps describe.
"""

import re

from ably.realtime.connection import ConnectionState
from test.uts.helpers.client import await_connection_state, sandbox_realtime_client

# The waits the specification's `Integration Test Notes` give each leg: auth plus transport
# setup for the connect, and a CLOSE message round trip for the close.
CONNECT_TIMEOUT = 10.0
CLOSE_TIMEOUT = 5.0


def connection_id(client):
    """The specification's `connection.id`, held on the connection manager."""
    return client.connection.connection_manager.connection_id


def connection_key(client):
    """The specification's `connection.key`, held on the connection details."""
    details = client.connection.connection_details
    return details.connection_key if details is not None else None


# UTS: realtime/integration/RTN4b/successful-connection-0
async def test_rtn4b_successful_connection(realtime_sandbox):
    # UTS SPEC ERROR: the setup leaves autoConnect at its default and the first step then
    # asserts INITIALIZED. RTN3 makes that default true, so a client built as the setup has
    # it is already CONNECTING when the constructor returns. The fixture is corrected here
    # rather than the assertion dropped.
    client = sandbox_realtime_client(realtime_sandbox.key_str, auto_connect=False)

    assert client.connection.state is ConnectionState.INITIALIZED

    client.connect()

    await await_connection_state(client, ConnectionState.CONNECTING, CONNECT_TIMEOUT)
    await await_connection_state(client, ConnectionState.CONNECTED, CONNECT_TIMEOUT)

    assert connection_id(client) is not None
    assert connection_key(client) is not None

    assert client.connection.state is ConnectionState.CONNECTED
    assert re.fullmatch(r'[a-zA-Z0-9_-]+', connection_id(client))
    assert re.fullmatch(r'[a-zA-Z0-9_!-]+', connection_key(client))
    assert client.connection.error_reason is None


# UTS: realtime/integration/RTN4c/graceful-close-0
async def test_rtn4c_graceful_close(realtime_sandbox):
    client = sandbox_realtime_client(realtime_sandbox.key_str)

    client.connect()
    await await_connection_state(client, ConnectionState.CONNECTED, CONNECT_TIMEOUT)

    states = []

    def record(change):
        states.append(change.current)

    client.connection.on(record)

    await client.connection.close()

    assert ConnectionState.CLOSING in states
    assert states[states.index(ConnectionState.CLOSING) + 1] is ConnectionState.CLOSED

    assert client.connection.state is ConnectionState.CLOSED
    assert client.connection.error_reason is None
    assert connection_id(client) is None
    assert connection_key(client) is None


# UTS: realtime/integration/RTN11/connect-reconnect-cycle-0
async def test_rtn11_connect_reconnect_cycle(realtime_sandbox):
    client = sandbox_realtime_client(realtime_sandbox.key_str, auto_connect=False)

    assert client.connection.state is ConnectionState.INITIALIZED

    client.connect()
    await await_connection_state(client, ConnectionState.CONNECTED, CONNECT_TIMEOUT)

    first_connection_id = connection_id(client)

    await client.connection.close()
    await await_connection_state(client, ConnectionState.CLOSED, CLOSE_TIMEOUT)

    client.connect()
    await await_connection_state(client, ConnectionState.CONNECTED, CONNECT_TIMEOUT)

    second_connection_id = connection_id(client)

    assert second_connection_id is not None
    assert first_connection_id != second_connection_id
    assert client.connection.error_reason is None
