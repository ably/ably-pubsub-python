"""Derived from uts/realtime/integration/proxy/presence_reentry.md in ably/specification.

Spec points: RTP17i, RTP17g

A member entered on a connection belongs to that connection, so re-entry is what keeps
it present once the channel attaches afresh. Both tests enter one member through a
`uts-proxy` session and then read the wire: a re-entry is a PRESENCE frame
(`action == 14`) from the client carrying an ENTER for the member, and the event log
records every one of them. Nothing here reads the SDK's internal presence map, and
neither test uses a second observer client — the server does not broadcast a re-entry
whose member, as far as it is concerned, never left.

`test/uts/realtime/unit/presence/realtime_presence_reentry_test.py` covers RTP17 against
a mock, where the reconnection is a dropped transport and a server that plays the
member back. These two differ in what triggers the re-attach and in what is measured:
the first injects an ATTACHED onto a channel that is already attached, which the mock
tier does not exercise, and the second drives a real WebSocket close from the proxy so
that the re-attach and the re-entry both complete against the sandbox. Where the unit
tests assert on the frames a mock server captured, these assert on the proxy's log.

Test 27 is gated: ably-python re-enters from `RealtimePresence.on_attached`, which runs
only when the channel transitions into ATTACHED, so an ATTACHED arriving on an
already-attached channel takes the RTL12 update path and re-enters nothing. Test 28
goes through a genuine ATTACHING and passes.
"""

from datetime import datetime

from ably.realtime.connection import ConnectionState
from ably.types.channelstate import ChannelState
from test.uts.helpers.client import (
    await_channel_state,
    await_connection_state,
    sandbox_realtime_client,
    wall_clock_poll_until,
)
from test.uts.helpers.deviations import deviation
from test.uts.helpers.sandbox import extract_key_name, extract_key_secret, generate_jwt, random_id

# The specification's `AWAIT_STATE ... WITH timeout` and `POLL_UNTIL` values, as
# wall-clock seconds, and the interval it polls the event log on.
CONNECT_TIMEOUT = 15.0
DISCONNECT_TIMEOUT = 10.0
CHANNEL_TIMEOUT = 15.0
POLL_TIMEOUT = 10.0
POLL_INTERVAL = 0.2

# PRESENCE and ENTER, as the event log reports the `action` of a protocol message and of
# the presence messages inside it.
PRESENCE_ACTION = 14
ENTER_ACTION = 2


def jwt_auth_callback(api_key, client_id):
    """The specification's `authCallback`, signing an Ably JWT carrying `clientId`.

    Presence needs an identity, and the specification gives the client one through the
    JWT's `clientId` claim rather than through `ClientOptions.clientId`, so that the
    identity the member is entered under is the one the token grants.
    """
    async def auth_callback(params):
        return generate_jwt(
            extract_key_name(api_key), extract_key_secret(api_key), client_id=client_id)

    return auth_callback


def proxied_client(api_key, session, client_id):
    """The `ClientOptions` both tests build their presence member with."""
    return sandbox_realtime_client(
        auth_callback=jwt_auth_callback(api_key, client_id),
        endpoint='localhost',
        port=session.proxy_port,
        tls=False,
        use_binary_protocol=False,
        auto_connect=False)


def presence_frames(log):
    """The PRESENCE frames the proxy recorded from the client."""
    return [event for event in log
            if event['type'] == 'ws_frame'
            and event.get('direction') == 'client_to_server'
            and (event.get('message') or {}).get('action') == PRESENCE_ACTION]


def event_time(event):
    """An event's `timestamp`, as a comparable value.

    The proxy timestamps an event as RFC 3339 with however many fractional digits the
    value needs, so `'...:24.46228Z'` and `'...:24.9Z'` do not order correctly as
    strings. The fraction is padded out to microseconds and parsed.
    """
    stamp = event['timestamp'].rstrip('Z')
    seconds, _, fraction = stamp.partition('.')
    return datetime.strptime(f'{seconds}.{fraction[:6].ljust(6, "0")}', '%Y-%m-%dT%H:%M:%S.%f')


# UTS: realtime/proxy/RTP17i/reenter-on-non-resumed-0
@deviation
async def test_rtp17i_reenter_on_non_resumed(realtime_sandbox, proxy_session):
    channel_name = f'test-rtp17i-{random_id()}'

    session = await proxy_session(rules=[])

    client = proxied_client(realtime_sandbox.key_str, session, 'client-a')
    channel = client.channels.get(channel_name)

    # Phase 1 -- Establish real presence state
    client.connect()
    await await_connection_state(client, ConnectionState.CONNECTED, CONNECT_TIMEOUT)

    await channel.attach()
    await channel.presence.enter(data='hello')

    # Phase 2 -- Count PRESENCE frames in the log before injection
    log_before = await session.get_log()
    presence_frames_before = len(presence_frames(log_before))

    # Phase 3 -- Inject ATTACHED with resumed=false (flags=0). This triggers RTP17i
    # re-entry without needing an actual disconnect.
    await session.trigger_action({
        'type': 'inject_to_client',
        'message': {
            'action': 11,
            'channel': channel_name,
            'flags': 0,
            'error': {'code': 91001, 'statusCode': 500, 'message': 'Continuity lost'},
        },
    })

    # Phase 4 -- Poll until a new PRESENCE frame appears in the log
    async def a_new_presence_frame():
        return len(presence_frames(await session.get_log())) > presence_frames_before

    await wall_clock_poll_until(
        a_new_presence_frame, POLL_TIMEOUT, 'a re-enter PRESENCE frame', POLL_INTERVAL)

    log_after = await session.get_log()
    all_presence_frames = presence_frames(log_after)

    # At least one new PRESENCE frame was sent after the injection
    assert len(all_presence_frames) > presence_frames_before

    # The last (most recent) re-enter frame should contain the presence data
    reenter_frame = all_presence_frames[-1]
    assert reenter_frame['message'].get('presence') is not None
    assert len(reenter_frame['message']['presence']) >= 1

    # RTP17g: re-enter uses stored clientId, data, and ENTER action
    reenter_msg = reenter_frame['message']['presence'][0]
    assert reenter_msg['clientId'] == 'client-a'
    assert reenter_msg['data'] == 'hello'
    assert reenter_msg['action'] == ENTER_ACTION

    # Channel should still be attached and connection still connected
    assert channel.state == ChannelState.ATTACHED
    assert client.connection.state == ConnectionState.CONNECTED


# UTS: realtime/proxy/RTP17i/reenter-after-disconnect-1
async def test_rtp17i_reenter_after_disconnect(realtime_sandbox, proxy_session):
    channel_name = f'test-rtp17i-real-{random_id()}'

    session = await proxy_session(rules=[
        {
            'match': {'type': 'delay_after_ws_connect', 'delayMs': 3000},
            'action': {'type': 'close'},
            'times': 1,
            'comment': 'RTP17i: Close WebSocket after 3s to trigger reconnect',
        },
        {
            'match': {'type': 'ws_frame_to_client', 'action': 'ATTACHED',
                      'channel': channel_name, 'count': 2},
            'action': {
                'type': 'replace',
                'message': {
                    'action': 11,
                    'channel': channel_name,
                    'flags': 0,
                    'error': {'code': 91001, 'statusCode': 500, 'message': 'Continuity lost'},
                },
            },
            'times': 1,
            'comment': 'RTP17i: Replace 2nd ATTACHED with non-resumed to trigger re-entry',
        },
    ])

    client_a = proxied_client(realtime_sandbox.key_str, session, 'client-a')
    channel_a = client_a.channels.get(channel_name)

    # The proxy closes the WebSocket 3 seconds after it opens, and the client retries at
    # once, so the connection states are recorded from before the connection is made
    # rather than waited on one at a time.
    connection_state_changes = []

    def record(change):
        connection_state_changes.append(change.current)

    client_a.connection.on(record)

    # Phase 1 -- Establish presence before the proxy closes the connection
    client_a.connect()
    await await_connection_state(client_a, ConnectionState.CONNECTED, CONNECT_TIMEOUT)

    await channel_a.attach()
    await channel_a.presence.enter(data='hello')

    # Phase 2 -- Wait for the temporal trigger to fire (at T+3s) and for reconnect
    await wall_clock_poll_until(
        lambda: ConnectionState.DISCONNECTED in connection_state_changes,
        DISCONNECT_TIMEOUT, 'the connection to report DISCONNECTED', POLL_INTERVAL)
    await await_connection_state(client_a, ConnectionState.CONNECTED, CONNECT_TIMEOUT)

    # Wait for the channel to reattach (the 2nd ATTACHED is replaced with non-resumed)
    await await_channel_state(channel_a, ChannelState.ATTACHED, CHANNEL_TIMEOUT)

    # Phase 3 -- Poll until a PRESENCE frame appears in the log after the 2nd ws_connect
    async def presence_after_reconnect():
        log = await session.get_log()
        ws_connects = [event for event in log if event['type'] == 'ws_connect']
        if len(ws_connects) < 2:
            return None
        second_connect_time = event_time(ws_connects[1])
        return [event for event in presence_frames(log)
                if event_time(event) > second_connect_time] or None

    await wall_clock_poll_until(
        presence_after_reconnect, POLL_TIMEOUT, 'a re-enter PRESENCE frame', POLL_INTERVAL)

    log = await session.get_log()
    ws_connects = [event for event in log if event['type'] == 'ws_connect']
    second_connect_time = event_time(ws_connects[1])

    reenter_frames = [event for event in presence_frames(log)
                      if event_time(event) > second_connect_time]

    assert len(reenter_frames) >= 1

    # Check the first re-enter frame
    reenter_frame = reenter_frames[0]
    assert reenter_frame['message'].get('presence') is not None
    assert len(reenter_frame['message']['presence']) >= 1

    # RTP17g: re-enter uses stored clientId, data, and ENTER action
    reenter_msg = reenter_frame['message']['presence'][0]
    assert reenter_msg['clientId'] == 'client-a'
    assert reenter_msg['data'] == 'hello'
    assert reenter_msg['action'] == ENTER_ACTION

    # Channel is still attached and connection is still connected
    assert channel_a.state == ChannelState.ATTACHED
    assert client_a.connection.state == ConnectionState.CONNECTED
