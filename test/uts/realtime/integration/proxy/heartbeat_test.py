"""Derived from uts/realtime/integration/proxy/heartbeat.md in ably/specification.

Spec points: RTN23a

RTN23a says a transport that has heard nothing for `maxIdleInterval +
realtimeRequestTimeout` is to be treated as dropped. This test does not wait that
interval out: the rule is `delay_after_ws_connect` at 2000 ms followed by `close`,
so the proxy sends a WebSocket close frame two seconds into the connection and the
SDK reacts to the close rather than to an expired idle timer. The sandbox advertises
`maxIdleInterval: 15000` in the CONNECTED frame — read off `connectionDetails` in
the proxy event log while this was derived — so the close lands well inside the
window the idle timer would have measured, and the reconnection the assertions look
for can only be the close frame's doing. That is also why the session needs no
`timeout_ms` of its own: the whole test runs in three or four seconds, nowhere near
the harness's 120-second idle limit.

`test/uts/realtime/unit/connection/heartbeat_test.py` covers RTN23a — and RTN23b,
RTN23c and RTN23c1 alongside it — against `MockWebSocket`, and is where the idle
timer itself is pinned: it scales `maxIdleInterval` down to 200 ms and shows that a
HEARTBEAT, a MESSAGE or an ACK each reset the timer while silence does not. None of
that is observable here, where the interval is the server's and the timer never
expires. What this test adds is the recovery: a real transport goes away mid-
connection, and the SDK opens a second real WebSocket carrying the first
connection's key as its `resume` parameter, which the proxy records.

The `times: 1` on the rule is load-bearing — the second connection has no close
waiting for it, so the reconnection settles instead of cycling.
"""

from ably.realtime.connection import ConnectionState
from test.uts.helpers.client import await_connection_state, sandbox_realtime_client, wall_clock_poll_until
from test.uts.helpers.mock_websocket import contains_in_order
from test.uts.helpers.sandbox import extract_key_name, extract_key_secret, generate_jwt

# The specification's `AWAIT_STATE ... WITH timeout`, in seconds.
CONNECT_TIMEOUT = 15
RECONNECT_TIMEOUT = 30

# The specification's `delayMs: 2000`.
CLOSE_DELAY_MS = 2000

# The specification's `state_changes CONTAINS_IN_ORDER [...]`: one connection lost
# and replaced.
FULL_CYCLE = [
    ConnectionState.CONNECTING,
    ConnectionState.CONNECTED,
    ConnectionState.DISCONNECTED,
    ConnectionState.CONNECTING,
    ConnectionState.CONNECTED,
]


def connection_id(client):
    """The specification's `client.connection.id`, which `Connection` does not expose.

    See the house ruling on missing accessors in `test/uts/deviations.md`.
    """
    return client.connection.connection_manager.connection_id


def connection_key(client):
    """The specification's `client.connection.key`, which arrives in `connectionDetails`."""
    details = client.connection.connection_details
    return details.connection_key if details is not None else None


def record_states(client):
    """The specification's `state_changes`, filled from `client.connection.on(...)`."""
    states = []

    def on_change(change):
        states.append(change.current)

    client.connection.on(on_change)
    return states


def jwt_auth_callback(api_key):
    """The specification's `authCallback` returning `generateJWT({keyName, keySecret})`.

    A JWT is signed from the two halves of the sandbox key, so the callback reaches
    no network at all and adds nothing to the session's event log.
    """
    key_name = extract_key_name(api_key)
    key_secret = extract_key_secret(api_key)

    async def auth_callback(params):
        return generate_jwt(key_name, key_secret)

    return auth_callback


# UTS: realtime/proxy/RTN23a/heartbeat-starvation-reconnect-0
async def test_rtn23a_heartbeat_starvation_reconnect(realtime_sandbox, proxy_session):
    session = await proxy_session(rules=[{
        'match': {'type': 'delay_after_ws_connect', 'delayMs': CLOSE_DELAY_MS},
        'action': {'type': 'close'},
        'times': 1,
        'comment': 'RTN23a: Close WebSocket after 2s to simulate transport failure',
    }])

    client = sandbox_realtime_client(
        auth_callback=jwt_auth_callback(realtime_sandbox.key_str),
        endpoint='localhost',
        port=session.proxy_port,
        tls=False,
        use_binary_protocol=False,
        auto_connect=False,
    )
    state_changes = record_states(client)

    client.connect()

    await await_connection_state(client, ConnectionState.CONNECTED, timeout=CONNECT_TIMEOUT)

    # Capture connection details from the first connection
    first_connection_id = connection_id(client)
    first_connection_key = connection_key(client)
    assert first_connection_id is not None

    # RTN15a has the SDK retry a drop from CONNECTED on the next loop iteration
    # rather than after a timer, so DISCONNECTED is gone again before anything can
    # observe the connection resting in it. Both waits below are therefore made
    # against the recorded sequence, which keeps every state the connection passed
    # through, rather than against the state the connection currently holds.
    await wall_clock_poll_until(
        lambda: ConnectionState.DISCONNECTED in state_changes,
        timeout=CONNECT_TIMEOUT,
        description='the connection to report DISCONNECTED')

    await wall_clock_poll_until(
        lambda: contains_in_order(state_changes, FULL_CYCLE),
        timeout=RECONNECT_TIMEOUT,
        description='the connection to be re-established')

    # Connection is re-established with new connection details
    assert client.connection.state == ConnectionState.CONNECTED
    assert connection_id(client) is not None
    assert connection_key(client) is not None

    # State sequence shows: connected -> disconnected -> reconnecting -> connected
    assert contains_in_order(state_changes, FULL_CYCLE)

    # Proxy event log confirms two WebSocket connections
    log = await session.get_log()
    ws_connects = [event for event in log if event['type'] == 'ws_connect']
    assert len(ws_connects) >= 2

    # Second connection should include resume parameter (RTN15c)
    assert ws_connects[1]['queryParams'].get('resume') is not None
    # The resume parameter is the first connection's key, which is how the key the
    # specification reads off `connection.key` is observable at all here
    assert ws_connects[1]['queryParams']['resume'] == first_connection_key
