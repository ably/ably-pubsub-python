"""Derived from uts/realtime/integration/proxy/auth_reauth.md in ably/specification.

Spec points: RTN22, RTC8a

The session carries no rules. The fault is imperative instead: once the connection
is up, `trigger_action({'type': 'inject_to_client', 'message': {'action': 17}})`
plants an AUTH ProtocolMessage in the stream as though the sandbox had asked the
client to re-authenticate, and everything else on the connection is the sandbox's
own traffic.

`test/uts/realtime/unit/connection/server_initiated_reauth_test.py` covers RTN22 and
RTN22a against `MockWebSocket`, where the mock answers the client's AUTH itself and
the test can read the outgoing ProtocolMessage directly — it pins that the token in
`auth.accessToken` is the one the callback just returned and that the reauth surfaces
as a single UPDATE event. Here the AUTH the SDK sends reaches the real server, which
answers it with a CONNECTED of its own; the outgoing frame is read back out of the
proxy's event log rather than off a mock, and what the test shows is that a reauth
carried out against the sandbox leaves the connection and its identity intact.

The injected AUTH is not a genuine server request, so the specification is careful
about what it asserts: that the SDK's auth machinery ran, that an AUTH frame carrying
an `auth` attribute left the client, and that the connection was never disturbed.
"""

from ably.realtime.connection import ConnectionState
from test.uts.helpers.client import await_connection_state, sandbox_realtime_client, wall_clock_poll_until
from test.uts.helpers.sandbox import extract_key_name, extract_key_secret, generate_jwt

# The specification's `AWAIT_STATE ... WITH timeout` and its `pollUntil` timeout,
# in seconds.
CONNECT_TIMEOUT = 15
REAUTH_TIMEOUT = 15

# AUTH, from the action table in `uts/docs/proxy.md`.
AUTH_ACTION = 17


def connection_id(client):
    """The specification's `client.connection.id`, which `Connection` does not expose.

    See the house ruling on missing accessors in `test/uts/deviations.md`.
    """
    return client.connection.connection_manager.connection_id


def jwt_auth_callback(api_key, calls):
    """The specification's `authCallback`, counting its invocations in `calls`.

    It signs a JWT from the two halves of the sandbox key rather than asking for a
    token, so re-authentication costs no round trip and puts nothing of its own in
    the session's event log.
    """
    key_name = extract_key_name(api_key)
    key_secret = extract_key_secret(api_key)

    async def auth_callback(params):
        calls.append(params)
        return generate_jwt(key_name, key_secret)

    return auth_callback


# UTS: realtime/proxy/RTN22/server-initiated-reauth-0
async def test_rtn22_server_initiated_reauth(realtime_sandbox, proxy_session):
    auth_callback_calls = []

    session = await proxy_session(rules=[])

    client = sandbox_realtime_client(
        auth_callback=jwt_auth_callback(realtime_sandbox.key_str, auth_callback_calls),
        endpoint='localhost',
        port=session.proxy_port,
        tls=False,
        use_binary_protocol=False,
        auto_connect=False,
    )

    client.connect()
    await await_connection_state(client, ConnectionState.CONNECTED, timeout=CONNECT_TIMEOUT)

    # Record identity and auth state before injection
    original_connection_id = connection_id(client)
    original_auth_callback_count = len(auth_callback_calls)
    assert original_connection_id is not None
    assert original_auth_callback_count >= 1

    # Record state changes from this point
    state_changes = []

    def on_change(change):
        state_changes.append(change.current)

    client.connection.on(on_change)

    # Inject a server-initiated AUTH ProtocolMessage (action 17), as though Ably
    # were asking the client to re-authenticate
    await session.trigger_action({'type': 'inject_to_client', 'message': {'action': AUTH_ACTION}})

    # Wait for the SDK to process the AUTH and invoke the callback again
    await wall_clock_poll_until(
        lambda: len(auth_callback_calls) > original_auth_callback_count,
        timeout=REAUTH_TIMEOUT,
        description='the auth callback to be invoked again')

    # authCallback was called again (re-authentication triggered)
    assert len(auth_callback_calls) == original_auth_callback_count + 1

    # Connection remains CONNECTED (re-auth does not disrupt the connection)
    assert client.connection.state == ConnectionState.CONNECTED

    # Connection ID is unchanged (no reconnection occurred)
    assert connection_id(client) == original_connection_id

    # No state transitions away from CONNECTED occurred
    assert [state for state in state_changes if state != ConnectionState.CONNECTED] == []

    # Proxy log shows the SDK sent an AUTH frame (action 17) from client to server.
    # The callback returns before the frame is written, so the log is polled for it
    # rather than read once: the wait above is satisfied by the token alone.
    async def client_auth_frames_in_log():
        log = await session.get_log()
        frames = [event for event in log
                  if event['type'] == 'ws_frame'
                  and event.get('direction') == 'client_to_server'
                  and (event.get('message') or {}).get('action') in (AUTH_ACTION, 'AUTH')
                  and (event.get('message') or {}).get('auth') is not None]
        return frames or None

    client_auth_frames = await wall_clock_poll_until(
        client_auth_frames_in_log,
        timeout=REAUTH_TIMEOUT,
        description="the SDK's AUTH frame to reach the proxy")
    assert len(client_auth_frames) >= 1
