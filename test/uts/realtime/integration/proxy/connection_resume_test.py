"""Derived from uts/realtime/integration/proxy/connection_resume.md in ably/specification.

Spec points: RTN14h, RTN15a, RTN15b, RTN15c6, RTN15c7, RTN15h1, RTN15h3, RTN15j, RTN16d,
RTN16l, RTN19a, RTN19a2

Every test here opens a `uts-proxy` session against the sandbox, points a realtime client
at it, and then takes the transport away — with a close frame, with a bare TCP FIN, with a
DISCONNECTED carrying an error the proxy invented, or with a CONNECTED the proxy rewrote.
What each one is about is what the client does next: whether it reconnects, whether the
reconnection carries a `resume` query parameter, and what identity and error it ends up
with. The proxy's event log is the second witness throughout — the SDK's own state answers
half of each question and the log answers the other half.

**The connection's identity is read through internal members.** `Connection` exposes
`state`, `error_reason`, `connection_details` and `connection_manager` and nothing else,
so the specification's `connection.id`, `connection.key` and `connection.createRecoveryKey()`
have no public spelling here. `connection_id`, `connection_key` and `recovery_key` below
are the readers the house ruling in `test/uts/deviations.md` calls for, defined once so the
adaptation is in one place. The proxy log is often the better witness anyway: the `resume`
query parameter *is* the connection key the client held when it reconnected.

**DISCONNECTED is transient.** RTN15a has the client retry a drop from CONNECTED
immediately — `loop.call_soon`, not a timer — so DISCONNECTED is gone within a millisecond
or two of being entered and `AWAIT_STATE disconnected` on the live state would be satisfied
by luck or not at all. Every test therefore registers a recorder on the connection before
it connects and waits on the recorded list, which is also what the specifications that read
`state_changes` want. `await_recorded_state(states, state, count)` is this file's
`AWAIT_STATE`.

The client options are the proxy tier's: `endpoint='localhost'` and `port` aim the client
at the session, `tls=False` because the session speaks plain WebSocket, and
`use_binary_protocol=False`. Authentication is the specification's `authCallback` returning
a locally signed Ably JWT, which reaches no network and so puts nothing in the event log
that a test counts. Cleanup is left to the fixtures — `proxy_session` closes every session
it opened and `test/uts/conftest.py` closes every client — except in RTN16d, where closing
the first client is a step of the scenario rather than tidying up.
"""

import asyncio
import json

from ably.realtime.channel import ChannelState
from ably.realtime.connection import ConnectionState
from test.uts.helpers.client import sandbox_realtime_client, sandbox_rest_client, wall_clock_poll_until
from test.uts.helpers.deviations import deviation
from test.uts.helpers.sandbox import extract_key_name, extract_key_secret, generate_jwt, random_id

# The waits the specification's `Integration Test Notes` section gives each step, in
# seconds: auth and transport setup through the proxy, a reconnection including the SDK's
# own retry, an injected DISCONNECTED arriving 1 s after the proxy's rule fires, and a
# transition to FAILED.
CONNECT_TIMEOUT = 15.0
RECONNECT_TIMEOUT = 15.0
DISCONNECT_TIMEOUT = 10.0
FAILED_TIMEOUT = 15.0
SUSPENDED_TIMEOUT = 15.0

# How often the recorded state list is re-read while waiting. The specifications' own
# polling interval is half a second, which is longer than the whole DISCONNECTED →
# CONNECTING → CONNECTED sequence takes; the list is append-only so nothing is missed
# either way, but a short interval keeps a test that waits on three states in turn from
# spending more time asleep than the scenario takes.
STATE_POLL_INTERVAL = 0.05

# The action numbers `uts/docs/proxy.md` tabulates, as they appear in a logged frame's
# decoded `message`.
ACK_ACTION = 1
MESSAGE_ACTION = 15


def jwt_auth_callback(api_key):
    """The specification's `authCallback`, returning an Ably JWT for `api_key`.

    The JWT is signed here rather than requested from the sandbox, so authenticating the
    client under test costs no traffic through the session and leaves the event log holding
    only what the scenario put there.
    """
    key_name = extract_key_name(api_key)
    key_secret = extract_key_secret(api_key)

    async def auth_callback(params):
        return generate_jwt(key_name, key_secret)

    return auth_callback


def proxy_realtime_client(session, api_key, **kwargs):
    """The specification's `Realtime(options: ClientOptions(...))` for a proxy session."""
    return sandbox_realtime_client(
        auth_callback=jwt_auth_callback(api_key),
        endpoint='localhost',
        port=session.proxy_port,
        tls=False,
        use_binary_protocol=False,
        auto_connect=False,
        **kwargs,
    )


def connection_id(client):
    """The specification's `connection.id`, which has no public accessor."""
    return client.connection.connection_manager.connection_id


def connection_key(client):
    """The specification's `connection.key`, which has no public accessor.

    `connection_details` is `None` whenever the key would be, so the two are null together
    exactly as the specification expects of `Connection#key`.
    """
    details = client.connection.connection_details
    return details.connection_key if details is not None else None


def recovery_key(client):
    """The specification's `connection.createRecoveryKey()`, which the SDK does not define.

    RTN16i makes a recovery key the JSON serialisation of the connection key, the current
    `msgSerial` and the `channelSerial` of every channel that is attached or attaching. All
    three are held internally, so they are read from there and assembled here.
    """
    manager = client.connection.connection_manager
    channel_serials = {}
    for channel in client.channels:
        if channel.state in (ChannelState.ATTACHED, ChannelState.ATTACHING):
            channel_serials[channel.name] = channel._RealtimeChannel__channel_serial
    return json.dumps({
        'connectionKey': connection_key(client),
        'msgSerial': manager.msg_serial,
        'channelSerials': channel_serials,
    })


def record_states(emitter):
    """Records every state `emitter` enters from now on, as the specifications' `state_changes`.

    Returned as a plain list of states in the order they were entered, which is what
    `CONTAINS`, `CONTAINS_IN_ORDER` and `indexOf` in the assertions read.
    """
    states = []

    def on_state_change(change):
        states.append(change.current)

    emitter.on(on_state_change)
    return states


async def await_recorded_state(states, state, count=1, timeout=CONNECT_TIMEOUT):
    """This file's `AWAIT_STATE`: waits until `states` holds `count` entries of `state`.

    Waiting on the recorded list rather than on the live state is what makes a transient
    state waitable, and `count` distinguishes the reconnection a test is waiting for from
    the CONNECTED the client already reached once. A timeout names the states that were
    recorded instead, which is the first thing worth knowing when one of these fails.
    """
    try:
        await wall_clock_poll_until(
            lambda: states.count(state) >= count,
            timeout=timeout,
            description=f'{count} state change(s) to {state.value}',
            interval=STATE_POLL_INTERVAL,
        )
    except AssertionError as error:
        recorded = [recorded_state.value for recorded_state in states]
        raise AssertionError(f'{error}; the states recorded were {recorded}') from None


def contains_in_order(states, expected):
    """Whether `expected` appears in `states` in order, as the specifications' `CONTAINS_IN_ORDER`."""
    remaining = list(expected)
    for state in states:
        if remaining and state == remaining[0]:
            remaining.pop(0)
    return not remaining


def ws_connects(log):
    """The `ws_connect` events the proxy recorded, in the order the client made them."""
    return [event for event in log if event['type'] == 'ws_connect']


def resume_param(ws_connect):
    """The `resume` query parameter of a `ws_connect` event, or `None` where it carried none."""
    return (ws_connect.get('queryParams') or {}).get('resume')


def recover_param(ws_connect):
    """The `recover` query parameter of a `ws_connect` event, or `None` where it carried none."""
    return (ws_connect.get('queryParams') or {}).get('recover')


def frames(log, direction, action):
    """The logged WebSocket frames of one action travelling one way.

    A frame is a `ws_frame` event carrying `direction` and the decoded `message`, whose
    `action` is an integer. The specification's `ws_frame_to_server` and its `action ==
    "MESSAGE"` name the same two things the log spells this way.
    """
    return [event for event in log
            if event['type'] == 'ws_frame'
            and event.get('direction') == direction
            and (event.get('message') or {}).get('action') == action]


# UTS: realtime/proxy/RTN15a/disconnect-triggers-resume-0
async def test_rtn15a_disconnect_triggers_resume(realtime_sandbox, proxy_session):
    session = await proxy_session(rules=[{
        'match': {'type': 'delay_after_ws_connect', 'delayMs': 1000},
        'action': {'type': 'close'},
        'times': 1,
        'comment': 'RTN15a: Close WebSocket after 1s to trigger unexpected disconnect',
    }])

    client = proxy_realtime_client(session, realtime_sandbox.key_str)

    # Register state listener BEFORE connecting so we capture all state transitions
    state_changes = record_states(client.connection)

    client.connect()

    # Wait for first connected (rule fires after 1s, then proxy closes connection)
    # SDK should reconnect and resume
    await await_recorded_state(state_changes, ConnectionState.CONNECTED, count=2, timeout=30.0)

    # State changes should include: connecting, connected, disconnected, connecting, connected
    disconnected_index = state_changes.index(ConnectionState.DISCONNECTED)
    assert disconnected_index >= 0

    # After the disconnected, there should be another connecting and connected
    post_disconnect_connecting = state_changes.index(ConnectionState.CONNECTING, disconnected_index)
    assert post_disconnect_connecting > disconnected_index

    assert contains_in_order(state_changes, [
        ConnectionState.DISCONNECTED,
        ConnectionState.CONNECTING,
        ConnectionState.CONNECTED,
    ])

    # Verify resume was attempted via proxy log
    log = await session.get_log()
    connects = ws_connects(log)
    assert len(connects) >= 2

    # Second WebSocket connection should include resume query parameter
    assert resume_param(connects[1]) is not None


# UTS: realtime/proxy/RTN15a/tcp-close-triggers-resume-1
async def test_rtn15a_tcp_close_triggers_resume(realtime_sandbox, proxy_session):
    # `disconnect` drops the TCP connection without a WebSocket close frame, where the test
    # above sends one. The client detects the FIN and reports DISCONNECTED just as quickly.
    session = await proxy_session(rules=[{
        'match': {'type': 'delay_after_ws_connect', 'delayMs': 1000},
        'action': {'type': 'disconnect'},
        'times': 1,
        'comment': 'RTN15a: Close TCP (no close frame) after 1s to trigger unexpected disconnect',
    }])

    client = proxy_realtime_client(session, realtime_sandbox.key_str)

    state_changes = record_states(client.connection)

    client.connect()

    await await_recorded_state(state_changes, ConnectionState.CONNECTED, count=2, timeout=30.0)

    disconnected_index = state_changes.index(ConnectionState.DISCONNECTED)
    assert disconnected_index >= 0

    post_disconnect_connecting = state_changes.index(ConnectionState.CONNECTING, disconnected_index)
    assert post_disconnect_connecting > disconnected_index

    assert contains_in_order(state_changes, [
        ConnectionState.DISCONNECTED,
        ConnectionState.CONNECTING,
        ConnectionState.CONNECTED,
    ])

    log = await session.get_log()
    connects = ws_connects(log)
    assert len(connects) >= 2

    assert resume_param(connects[1]) is not None


# UTS: realtime/proxy/RTN15b/resume-preserves-connid-0
async def test_rtn15b_resume_preserves_connid(realtime_sandbox, proxy_session):
    session = await proxy_session(rules=[{
        'match': {'type': 'delay_after_ws_connect', 'delayMs': 1000},
        'action': {'type': 'close'},
        'times': 1,
        'comment': 'RTN15b/c6: Close WebSocket after 1s to trigger resume',
    }])

    client = proxy_realtime_client(session, realtime_sandbox.key_str)
    state_changes = record_states(client.connection)

    client.connect()
    await await_recorded_state(state_changes, ConnectionState.CONNECTED, timeout=CONNECT_TIMEOUT)

    # Record connection identity before disconnect
    original_connection_id = connection_id(client)
    original_connection_key = connection_key(client)
    assert original_connection_id is not None
    assert original_connection_key is not None

    # Proxy closes connection after 1s; wait for disconnected then reconnected
    await await_recorded_state(state_changes, ConnectionState.DISCONNECTED, timeout=DISCONNECT_TIMEOUT)

    # Wait for SDK to resume
    await await_recorded_state(state_changes, ConnectionState.CONNECTED, count=2, timeout=RECONNECT_TIMEOUT)

    # RTN15c6: Connection ID is preserved (successful resume)
    assert connection_id(client) == original_connection_id

    # RTN15b: Second ws_connect URL includes resume={connectionKey}
    log = await session.get_log()
    connects = ws_connects(log)
    assert len(connects) >= 2
    assert resume_param(connects[1]) == original_connection_key

    # No error reason on successful resume
    assert client.connection.error_reason is None


# UTS: realtime/proxy/RTN15c7/failed-resume-new-connid-0
async def test_rtn15c7_failed_resume_new_connid(realtime_sandbox, proxy_session):
    session = await proxy_session(rules=[
        {
            'match': {'type': 'delay_after_ws_connect', 'delayMs': 1000},
            'action': {'type': 'close'},
            'times': 1,
            'comment': 'RTN15c7: Close WebSocket after 1s to trigger resume attempt',
        },
        {
            'match': {'type': 'ws_frame_to_client', 'action': 'CONNECTED', 'count': 2},
            'action': {
                'type': 'replace',
                'message': {
                    'action': 4,
                    'connectionId': 'proxy-injected-new-id',
                    'connectionKey': 'proxy-injected-new-key',
                    'connectionDetails': {
                        'connectionKey': 'proxy-injected-new-key',
                        'clientId': None,
                        'maxMessageSize': 65536,
                        'maxInboundRate': 250,
                        'maxOutboundRate': 100,
                        'maxFrameSize': 524288,
                        'serverId': 'test-server',
                        'connectionStateTtl': 120000,
                        'maxIdleInterval': 15000,
                    },
                    'error': {
                        'code': 80008,
                        'statusCode': 400,
                        'message': 'Unable to recover connection',
                    },
                },
            },
            'times': 1,
            'comment': 'RTN15c7: Replace 2nd CONNECTED with failed resume (different connectionId + error 80008)',
        },
    ])

    client = proxy_realtime_client(session, realtime_sandbox.key_str)
    state_changes = record_states(client.connection)

    # Connect through proxy -- first CONNECTED passes through normally
    client.connect()
    await await_recorded_state(state_changes, ConnectionState.CONNECTED, timeout=CONNECT_TIMEOUT)

    # Record original identity
    original_connection_id = connection_id(client)
    assert original_connection_id is not None
    assert original_connection_id != 'proxy-injected-new-id'

    # Proxy closes connection after 1s; the SDK reconnects, but the proxy replaces the
    # CONNECTED response with a new connectionId, so the SDK reaches CONNECTED with the
    # new identity.
    await await_recorded_state(state_changes, ConnectionState.DISCONNECTED, timeout=DISCONNECT_TIMEOUT)
    await await_recorded_state(state_changes, ConnectionState.CONNECTED, count=2, timeout=RECONNECT_TIMEOUT)

    # RTN15c7: Connection ID changed (resume failed, got new connection)
    assert connection_id(client) == 'proxy-injected-new-id'
    assert connection_id(client) != original_connection_id

    # Connection key updated to the new one
    assert connection_key(client) == 'proxy-injected-new-key'

    # Error reason is set indicating why resume failed
    assert client.connection.error_reason is not None
    assert client.connection.error_reason.code == 80008

    # Connection is still CONNECTED (not FAILED -- the server gave a new connection)
    assert client.connection.state == ConnectionState.CONNECTED

    # Verify resume was attempted in the proxy log
    log = await session.get_log()
    connects = ws_connects(log)
    assert len(connects) >= 2
    assert resume_param(connects[1]) is not None


# UTS: realtime/proxy/RTN15h1/token-error-nonrenewable-failed-0
async def test_rtn15h1_token_error_nonrenewable_failed(realtime_sandbox, proxy_session):
    session = await proxy_session(rules=[{
        'match': {'type': 'delay_after_ws_connect', 'delayMs': 1000},
        'action': {
            'type': 'inject_to_client_and_close',
            'message': {
                'action': 6,
                'error': {
                    'code': 40142,
                    'statusCode': 401,
                    'message': 'Token expired',
                },
            },
        },
        'times': 1,
        'comment': 'RTN15h1: Inject DISCONNECTED with token error (40142) after 1s',
    }])

    # Obtain a real token from the sandbox so the initial connection succeeds. The Rest
    # client asking for it is aimed straight at the sandbox, so the request does not cross
    # the session and leaves nothing in its event log.
    rest = sandbox_rest_client(realtime_sandbox.key_str)
    token_details = await rest.auth.request_token()

    # Use the token string directly -- no key, no authCallback. This makes the token
    # non-renewable.
    client = sandbox_realtime_client(
        token=token_details.token,
        endpoint='localhost',
        port=session.proxy_port,
        tls=False,
        use_binary_protocol=False,
        auto_connect=False,
    )
    connect_states = record_states(client.connection)

    # Connect through proxy -- initial connection succeeds with the real token
    client.connect()
    await await_recorded_state(connect_states, ConnectionState.CONNECTED, timeout=CONNECT_TIMEOUT)

    # Record state changes
    state_changes = record_states(client.connection)

    # After 1s the proxy injects DISCONNECTED with 40142 and closes the socket.
    # The SDK has a non-renewable token, so it cannot renew -> FAILED.
    await await_recorded_state(state_changes, ConnectionState.FAILED, timeout=FAILED_TIMEOUT)

    # RTN15h1: Ended in FAILED state
    assert client.connection.state == ConnectionState.FAILED

    # Error reason reflects the token error. The SDK detects it has no means to renew and
    # substitutes 40171 for the injected 40142, which is what the specification asks for.
    error = client.connection.error_reason
    assert error is not None
    assert error.code == 40171

    # UTS SPEC ERROR: the specification asserts statusCode 401 here, citing ably-js. ably-js
    # pairs 40171 with statusCode 403 (`src/common/lib/client/auth.ts`, the ErrorInfo thrown
    # when authOptions offer no way to request a token), and so does ably-python
    # (`ably/rest/auth.py:200`). 403 is what both libraries report.
    assert error.status_code == 403

    # State changes should show the transition to FAILED
    # (may pass through DISCONNECTED briefly before FAILED)
    assert ConnectionState.FAILED in state_changes


# UTS: realtime/proxy/RTN15h3/non-token-error-reconnects-0
@deviation
async def test_rtn15h3_non_token_error_reconnects(realtime_sandbox, proxy_session):
    session = await proxy_session(rules=[{
        'match': {'type': 'delay_after_ws_connect', 'delayMs': 1000},
        'action': {
            'type': 'inject_to_client_and_close',
            'message': {
                'action': 6,
                'error': {
                    'code': 80003,
                    'statusCode': 500,
                    'message': 'Service temporarily unavailable',
                },
            },
        },
        'times': 1,
        'comment': 'RTN15h3: Inject DISCONNECTED with non-token error (80003) after 1s, once only',
    }])

    client = proxy_realtime_client(session, realtime_sandbox.key_str)
    connect_states = record_states(client.connection)

    client.connect()
    await await_recorded_state(connect_states, ConnectionState.CONNECTED, timeout=CONNECT_TIMEOUT)

    # Record state changes
    state_changes = record_states(client.connection)

    # After 1s the proxy injects DISCONNECTED with non-token error and closes.
    # The rule fires once, so the reconnection attempt passes through to the real server.

    # Wait for DISCONNECTED (from the injected message)
    await await_recorded_state(state_changes, ConnectionState.DISCONNECTED, timeout=DISCONNECT_TIMEOUT)

    # SDK should automatically reconnect
    await await_recorded_state(state_changes, ConnectionState.CONNECTED, timeout=RECONNECT_TIMEOUT)

    # RTN15h3: SDK reconnected successfully (not FAILED)
    assert client.connection.state == ConnectionState.CONNECTED

    # State changes should show: disconnected -> connecting -> connected
    assert contains_in_order(state_changes, [
        ConnectionState.DISCONNECTED,
        ConnectionState.CONNECTING,
        ConnectionState.CONNECTED,
    ])

    # Verify resume was attempted
    log = await session.get_log()
    connects = ws_connects(log)
    assert len(connects) >= 2
    assert resume_param(connects[1]) is not None

    # No error reason after successful reconnection
    assert client.connection.error_reason is None


# UTS: realtime/proxy/RTN15j/fatal-error-established-conn-0
@deviation
async def test_rtn15j_fatal_error_established_conn(realtime_sandbox, proxy_session):
    # No rules: the ERROR is injected imperatively once the connection and both channels
    # are up.
    session = await proxy_session(rules=[])

    client = proxy_realtime_client(session, realtime_sandbox.key_str)
    connect_states = record_states(client.connection)

    client.connect()
    await await_recorded_state(connect_states, ConnectionState.CONNECTED, timeout=CONNECT_TIMEOUT)

    # Attach two channels in parallel
    channel_a = client.channels.get(f'fatal-error-a-{random_id()}')
    channel_b = client.channels.get(f'fatal-error-b-{random_id()}')
    await asyncio.gather(channel_a.attach(), channel_b.attach())

    # Record state changes
    connection_state_changes = record_states(client.connection)
    channel_a_state_changes = record_states(channel_a)
    channel_b_state_changes = record_states(channel_b)

    # Inject a connection-level ERROR via proxy imperative action
    await session.trigger_action({
        'type': 'inject_to_client',
        'message': {
            'action': 9,
            'error': {
                'code': 50000,
                'statusCode': 500,
                'message': 'Internal server error',
            },
        },
    })

    # SDK should transition to FAILED
    await await_recorded_state(connection_state_changes, ConnectionState.FAILED, timeout=FAILED_TIMEOUT)

    # RTN15j: Connection is in FAILED state
    assert client.connection.state == ConnectionState.FAILED

    # Connection errorReason has the injected error
    assert client.connection.error_reason is not None
    assert client.connection.error_reason.code == 50000
    assert client.connection.error_reason.status_code == 500

    # Both channels transitioned to FAILED
    assert channel_a.state == ChannelState.FAILED
    assert channel_b.state == ChannelState.FAILED

    # Channel errors match the connection error
    assert channel_a.error_reason is not None
    assert channel_a.error_reason.code == 50000
    assert channel_b.error_reason is not None
    assert channel_b.error_reason.code == 50000

    # State change sequences
    assert ConnectionState.FAILED in connection_state_changes
    assert ChannelState.FAILED in channel_a_state_changes
    assert ChannelState.FAILED in channel_b_state_changes

    # No reconnection attempted -- only the original ws_connect in the proxy log
    log = await session.get_log()
    assert len(ws_connects(log)) == 1


# UTS: realtime/proxy/RTN14h/resume-after-ttl-expiry-0
@deviation
async def test_rtn14h_resume_after_ttl_expiry(realtime_sandbox, proxy_session):
    session = await proxy_session(rules=[
        {
            'match': {'type': 'ws_frame_to_client', 'action': 'CONNECTED', 'count': 1},
            'action': {
                'type': 'replace',
                'message': {
                    'action': 4,
                    'connectionId': 'proxy-ttl-test-id',
                    'connectionKey': '__PASSTHROUGH__',
                    'connectionDetails': {
                        'connectionKey': '__PASSTHROUGH__',
                        'clientId': None,
                        'maxMessageSize': 65536,
                        'maxInboundRate': 250,
                        'maxOutboundRate': 100,
                        'maxFrameSize': 524288,
                        'serverId': 'test-server',
                        'connectionStateTtl': 2000,
                        'maxIdleInterval': 15000,
                    },
                },
            },
            'times': 1,
            'comment': 'RTN14h: Replace 1st CONNECTED to set short connectionStateTtl (2s) and known connectionId',
        },
        {
            'match': {'type': 'delay_after_ws_connect', 'delayMs': 1000},
            'action': {'type': 'close'},
            'times': 1,
            'comment': 'RTN14h: Close connection after 1s -- client enters DISCONNECTED with 2s TTL',
        },
        {
            'match': {'type': 'ws_connect', 'count': 2},
            'action': {'type': 'refuse_connection'},
            'times': 1,
            'comment': 'RTN14h: Refuse 2nd ws_connect -- keeps client disconnected until TTL expires',
        },
    ])

    # A short `suspended_retry_timeout` so the test does not wait long after SUSPENDED.
    client = proxy_realtime_client(session, realtime_sandbox.key_str, suspended_retry_timeout=1000)
    state_changes = record_states(client.connection)

    # Connect through proxy -- first CONNECTED is replaced with short TTL and known connectionId
    client.connect()
    await await_recorded_state(state_changes, ConnectionState.CONNECTED, timeout=CONNECT_TIMEOUT)

    # Verify proxy-injected connectionId
    assert connection_id(client) == 'proxy-ttl-test-id'

    # T=1s: proxy closes connection -> DISCONNECTED
    # T=1-3s: retry attempt is refused -> stays DISCONNECTED
    # T=3s: connectionStateTtl(2s) expires -> SUSPENDED
    # T=4s: suspendedRetryTimeout(1s) fires -> ws_connect that still attempts a resume
    #       (RTN14h); the server has discarded the state, so it responds with a new
    #       connectionId -> CONNECTED
    await await_recorded_state(state_changes, ConnectionState.SUSPENDED, timeout=SUSPENDED_TIMEOUT)

    # After suspended, SDK makes a fresh connection
    await await_recorded_state(
        state_changes, ConnectionState.CONNECTED, count=2, timeout=RECONNECT_TIMEOUT)

    # The server discarded the connection state, so the resume failed server-side and the
    # connection ID changed.
    assert connection_id(client) != 'proxy-ttl-test-id'

    # Verify the proxy log shows at least 3 ws_connects
    log = await session.get_log()
    connects = ws_connects(log)
    assert len(connects) >= 3

    # First ws_connect: initial -- no resume
    assert resume_param(connects[0]) is None

    # RTN14h: the reconnection made after the TTL expired and the connection became
    # suspended still attempts a resume, so it carries the resume query param.
    assert resume_param(connects[-1]) is not None


# UTS: realtime/proxy/RTN19a/unacked-resent-on-resume-0
async def test_rtn19a_unacked_resent_on_resume(realtime_sandbox, proxy_session):
    session = await proxy_session(rules=[{
        'match': {'type': 'ws_frame_to_client', 'action': 'ACK'},
        'action': {'type': 'suppress'},
        'times': 1,
        'comment': 'RTN19a: Suppress the first ACK so the SDK has a pending unacked message',
    }])

    client = proxy_realtime_client(session, realtime_sandbox.key_str)
    state_changes = record_states(client.connection)

    client.connect()
    await await_recorded_state(state_changes, ConnectionState.CONNECTED, timeout=CONNECT_TIMEOUT)

    # One sandbox app serves the whole realtime integration tier, so the specification's
    # fixed channel name takes a suffix of its own.
    channel = client.channels.get(f'test-resend-unacked-{random_id()}')
    await channel.attach()
    assert channel.state == ChannelState.ATTACHED

    # Start a publish -- do NOT await it yet. The message is sent to the server, but the
    # ACK is suppressed by the proxy rule.
    publish_future = asyncio.ensure_future(channel.publish('event', 'test-data'))

    # Poll the proxy log until we can confirm both:
    #   (a) the MESSAGE frame has been sent client->server (action==15)
    #   (b) the ACK frame has been suppressed server->client (action==1 with ruleMatched)
    # This avoids a fixed sleep and ensures the disconnect fires at the right moment.
    async def message_sent_and_ack_suppressed():
        log = await session.get_log()
        message_sent = bool(frames(log, 'client_to_server', MESSAGE_ACTION))
        ack_suppressed = any(event.get('ruleMatched') for event in frames(log, 'server_to_client', ACK_ACTION))
        return message_sent and ack_suppressed

    await wall_clock_poll_until(
        message_sent_and_ack_suppressed,
        timeout=DISCONNECT_TIMEOUT,
        description='the MESSAGE to be sent and its ACK to be suppressed')

    # Close the connection -- the SDK has an unacked message pending
    await session.trigger_action({'type': 'close'})

    # SDK reconnects and resumes (the ACK suppression rule already fired once, so the
    # reconnected session passes ACKs through normally)
    await await_recorded_state(
        state_changes, ConnectionState.CONNECTED, count=2, timeout=RECONNECT_TIMEOUT)

    # Now await the publish -- it should complete successfully after the message is resent
    # on the new transport and ACKed. The publish completed: no exception raised.
    await asyncio.wait_for(asyncio.shield(publish_future), RECONNECT_TIMEOUT)
    assert publish_future.done()
    assert publish_future.exception() is None

    # Verify resume occurred
    log = await session.get_log()
    connects = ws_connects(log)
    assert len(connects) >= 2
    assert resume_param(connects[1]) is not None

    # RTN19a: The MESSAGE frame was sent on both transports (original + resend)
    message_frames = frames(log, 'client_to_server', MESSAGE_ACTION)
    assert len(message_frames) >= 2

    # RTN19a2: On successful resume, the resent message has the same msgSerial
    assert message_frames[0]['message']['msgSerial'] == message_frames[1]['message']['msgSerial']


# UTS: realtime/proxy/RTN16d/recovery-preserves-connid-0
@deviation
async def test_rtn16d_recovery_preserves_connid(realtime_sandbox, proxy_session):
    # A session each: the first establishes the connection whose recovery key is taken, the
    # second carries the recovering client so its `recover` query parameter can be read off
    # a log of its own.
    session_1 = await proxy_session(rules=[])
    session_2 = await proxy_session(rules=[])

    client_1 = proxy_realtime_client(session_1, realtime_sandbox.key_str)
    client_1_states = record_states(client_1.connection)

    # --- Phase 1: Obtain recovery key from first client ---

    client_1.connect()
    await await_recorded_state(client_1_states, ConnectionState.CONNECTED, timeout=CONNECT_TIMEOUT)

    original_connection_id = connection_id(client_1)
    original_connection_key = connection_key(client_1)
    assert original_connection_id is not None

    # Attach a channel so it appears in the recovery key
    channel_1 = client_1.channels.get(f'recovery-test-{random_id()}')
    await channel_1.attach()
    assert channel_1.state == ChannelState.ATTACHED

    # Get the recovery key
    key = recovery_key(client_1)
    assert key is not None

    # Close the first client's transport WITHOUT closing the Ably connection gracefully, so
    # that the server keeps the connection state alive for recovery.
    await session_1.trigger_action({'type': 'close'})

    # Wait for the client to detect the disconnect
    await await_recorded_state(client_1_states, ConnectionState.DISCONNECTED, timeout=DISCONNECT_TIMEOUT)

    # Close client_1 without allowing it to reconnect
    await client_1.close()
    assert client_1.connection.state == ConnectionState.CLOSED
    await session_1.close()

    # --- Phase 2: Recover using the recovery key ---

    client_2 = proxy_realtime_client(session_2, realtime_sandbox.key_str, recover=key)
    client_2_states = record_states(client_2.connection)

    client_2.connect()
    await await_recorded_state(client_2_states, ConnectionState.CONNECTED, timeout=CONNECT_TIMEOUT)

    # RTN16d: Connection ID is preserved (same as original connection)
    assert connection_id(client_2) == original_connection_id

    # RTN16d: Connection key is updated (new key from server)
    assert connection_key(client_2) is not None
    assert connection_key(client_2) != original_connection_key

    # RTN16k: Verify the recover query parameter was sent via proxy log
    log = await session_2.get_log()
    connects = ws_connects(log)
    assert len(connects) >= 1
    assert recover_param(connects[0]) == original_connection_key

    # No resume param (this is recovery, not resume)
    assert resume_param(connects[0]) is None

    # No error on successful recovery
    assert client_2.connection.error_reason is None


# UTS: realtime/proxy/RTN16l/recovery-failure-fresh-conn-0
@deviation
async def test_rtn16l_recovery_failure_fresh_conn(realtime_sandbox, proxy_session):
    session = await proxy_session(rules=[{
        'match': {'type': 'ws_frame_to_client', 'action': 'CONNECTED', 'count': 1},
        'action': {
            'type': 'replace',
            'message': {
                'action': 4,
                'connectionId': 'recovery-failed-new-id',
                'connectionKey': 'recovery-failed-new-key',
                'connectionDetails': {
                    'connectionKey': 'recovery-failed-new-key',
                    'clientId': None,
                    'maxMessageSize': 65536,
                    'maxInboundRate': 250,
                    'maxOutboundRate': 100,
                    'maxFrameSize': 524288,
                    'serverId': 'test-server',
                    'connectionStateTtl': 120000,
                    'maxIdleInterval': 15000,
                },
                'error': {
                    'code': 80008,
                    'statusCode': 400,
                    'message': 'Unable to recover connection',
                },
            },
        },
        'times': 1,
        'comment': 'RTN16l: Replace CONNECTED with recovery failure (new connectionId + error 80008)',
    }])

    # A fabricated recovery key. The connectionKey does not need to be valid, since the
    # proxy replaces the server's response anyway.
    fabricated_recovery_key = json.dumps({
        'connectionKey': 'stale-old-key',
        'msgSerial': 99,
        'channelSerials': {
            'old-channel': 'old-serial',
        },
    })

    client = proxy_realtime_client(session, realtime_sandbox.key_str, recover=fabricated_recovery_key)
    state_changes = record_states(client.connection)

    # Connect with the fabricated recovery key
    client.connect()
    await await_recorded_state(state_changes, ConnectionState.CONNECTED, timeout=CONNECT_TIMEOUT)

    # RTN16l + RTN15c7: Connection got a new ID (recovery failed)
    assert connection_id(client) == 'recovery-failed-new-id'
    assert connection_key(client) == 'recovery-failed-new-key'

    # RTN15c7: Error is set on the connection indicating recovery failure
    assert client.connection.error_reason is not None
    assert client.connection.error_reason.code == 80008

    # Connection is still CONNECTED (not FAILED -- the server gave a new connection)
    assert client.connection.state == ConnectionState.CONNECTED

    # Verify the recover param was sent via proxy log
    log = await session.get_log()
    connects = ws_connects(log)
    assert len(connects) >= 1
    assert recover_param(connects[0]) == 'stale-old-key'
