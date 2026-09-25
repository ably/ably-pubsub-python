"""Derived from uts/realtime/integration/proxy/channel_faults.md in ably/specification.

Spec points: RTL4f, RTL5f, RTL13a, RTL14, RTL12, RTL3d

Each test opens a `uts-proxy` session, points a realtime client at it and faults one
frame: an ATTACH or a DETACH suppressed so the server never answers it, an ATTACHED
replaced by an ERROR, or a DETACHED, an ERROR or an ATTACHED injected onto a channel
that is already attached. Everything the rule does not name reaches the sandbox, so the
re-attach a fault provokes completes against the real server.

A frame rule matches `action` as a string — `'ATTACH'`, `'ATTACHED'`, `'DETACH'` — and
the proxy records the frame it matched before applying the rule, so a suppressed frame
still appears in the event log with `ruleMatched` carrying the rule's `comment`. A
replaced frame is logged as the frame the server sent, not as the replacement.

Two of the specification's `AWAIT_STATE` steps wait for a state the channel already
holds: RTL13a and RTL3d both re-attach an attached channel, so waiting on ATTACHED
would return at once and assert nothing. Those steps are taken on the recorded state
sequence instead — the listener is registered before the fault is triggered, and the
wait is for ATTACHING followed by ATTACHED to appear in it, which is the transition the
specification is about and the same thing its `CONTAINS_IN_ORDER` assertion checks.

There is no `## Protocol Variants` section, so these run against JSON only, which the
proxy tier requires in any case.
"""

import asyncio

import pytest

from ably.realtime.connection import ConnectionState
from ably.types.channelstate import ChannelState
from ably.util.exceptions import AblyException
from test.uts.helpers.client import (
    await_channel_state,
    await_connection_state,
    sandbox_realtime_client,
    wall_clock_poll_until,
)
from test.uts.helpers.sandbox import extract_key_name, extract_key_secret, generate_jwt, random_id

# The specification's `realtimeRequestTimeout: 3000`, in the milliseconds the client
# option takes. It is the deadline on both the attach and the detach the two timeout
# tests provoke (TO3l11).
REALTIME_REQUEST_TIMEOUT_MS = 3000

# The specification's `AWAIT_STATE ... WITH timeout` values, as wall-clock seconds.
CONNECT_TIMEOUT = 15.0
CHANNEL_TIMEOUT = 15.0
FAILED_TIMEOUT = 10.0
PENDING_TIMEOUT = 5.0

# ATTACH, as the event log reports a protocol message's `action`.
ATTACH_ACTION = 10


def jwt_auth_callback(api_key):
    """The specification's `authCallback`, signing an Ably JWT for the app's key.

    The callback makes no request of its own: the JWT is signed locally from the key
    name and secret, so nothing the client authenticates with reaches the session and
    lands in the event log beside the frames a test counts.
    """
    async def auth_callback(params):
        return generate_jwt(extract_key_name(api_key), extract_key_secret(api_key))

    return auth_callback


def proxied_client(api_key, session, **kwargs):
    """The `ClientOptions` every test in this specification builds its client with."""
    return sandbox_realtime_client(
        auth_callback=jwt_auth_callback(api_key),
        endpoint='localhost',
        port=session.proxy_port,
        tls=False,
        use_binary_protocol=False,
        auto_connect=False,
        **kwargs)


def attach_frames(log, channel_name):
    """The ATTACH frames the proxy recorded from the client for `channel_name`."""
    return [event for event in log
            if event['type'] == 'ws_frame'
            and event.get('direction') == 'client_to_server'
            and (event.get('message') or {}).get('action') == ATTACH_ACTION
            and (event.get('message') or {}).get('channel') == channel_name]


def contains_in_order(recorded, expected):
    """The specifications' `CONTAINS_IN_ORDER`: `expected` as a subsequence of `recorded`."""
    remaining = list(expected)
    for item in recorded:
        if remaining and item == remaining[0]:
            remaining.pop(0)
    return not remaining


def state_recorder(emitter):
    """Records every state `emitter` enters, from the moment this is called."""
    recorded = []

    def record(change):
        recorded.append(change.current)

    emitter.on(record)
    return recorded


# UTS: realtime/proxy/RTL4f/attach-timeout-suppressed-0
async def test_rtl4f_attach_timeout_suppressed(realtime_sandbox, proxy_session):
    channel_name = f'test-RTL4f-{random_id()}'

    session = await proxy_session(rules=[{
        'match': {'type': 'ws_frame_to_server', 'action': 'ATTACH', 'channel': channel_name},
        'action': {'type': 'suppress'},
        'comment': 'RTL4f: Suppress ATTACH so server never responds',
    }])

    client = proxied_client(realtime_sandbox.key_str, session,
                            realtime_request_timeout=REALTIME_REQUEST_TIMEOUT_MS)
    channel = client.channels.get(channel_name)

    # Record channel state changes for sequence verification
    channel_state_changes = state_recorder(channel)

    # Connect through proxy -- connection itself is not faulted
    client.connect()
    await await_connection_state(client, ConnectionState.CONNECTED, CONNECT_TIMEOUT)

    # Start attach -- proxy will suppress the ATTACH, so server never responds
    attach_future = asyncio.ensure_future(channel.attach())

    # Channel should enter ATTACHING immediately
    await await_channel_state(channel, ChannelState.ATTACHING, PENDING_TIMEOUT)

    # Wait for the channel to transition to SUSPENDED after realtimeRequestTimeout
    await await_channel_state(channel, ChannelState.SUSPENDED, CHANNEL_TIMEOUT)

    # The attach() call should have failed with a timeout error
    with pytest.raises(AblyException) as excinfo:
        await asyncio.wait_for(attach_future, PENDING_TIMEOUT)

    # Channel transitioned to SUSPENDED
    assert channel.state == ChannelState.SUSPENDED

    # Error indicates timeout
    assert excinfo.value is not None

    # State sequence: ATTACHING -> SUSPENDED
    assert contains_in_order(channel_state_changes, [ChannelState.ATTACHING, ChannelState.SUSPENDED])

    # Connection remains CONNECTED (attach timeout is channel-scoped)
    assert client.connection.state == ConnectionState.CONNECTED

    # Proxy log confirms the ATTACH frames were received but suppressed.
    # The proxy logs frames before applying rules, so suppressed frames still appear in
    # the log with `ruleMatched` set.
    log = await session.get_log()
    frames = attach_frames(log, channel_name)
    assert len(frames) >= 1

    # All ATTACH frames were caught by the suppress rule
    for frame in frames:
        assert frame.get('ruleMatched') is not None


# UTS: realtime/proxy/RTL14/error-on-attach-0
async def test_rtl14_error_on_attach(realtime_sandbox, proxy_session):
    channel_name = f'test-RTL14-error-on-attach-{random_id()}'

    session = await proxy_session(rules=[{
        'match': {'type': 'ws_frame_to_client', 'action': 'ATTACHED', 'channel': channel_name},
        'action': {
            'type': 'replace',
            'message': {
                'action': 9,
                'channel': channel_name,
                'error': {'code': 40160, 'statusCode': 403, 'message': 'Not permitted'},
            },
        },
        'times': 1,
        'comment': 'RTL14: Replace ATTACHED with channel ERROR',
    }])

    client = proxied_client(realtime_sandbox.key_str, session)
    channel = client.channels.get(channel_name)

    # Record channel state changes for sequence verification
    channel_state_changes = state_recorder(channel)

    client.connect()
    await await_connection_state(client, ConnectionState.CONNECTED, CONNECT_TIMEOUT)

    # Attach -- proxy replaces ATTACHED with ERROR
    with pytest.raises(AblyException) as excinfo:
        await channel.attach()

    await await_channel_state(channel, ChannelState.FAILED, FAILED_TIMEOUT)

    # Channel transitioned to FAILED
    assert channel.state == ChannelState.FAILED

    # Error reason matches the injected error
    assert channel.error_reason is not None
    assert channel.error_reason.code == 40160
    assert channel.error_reason.status_code == 403

    # The error returned from attach() matches
    assert excinfo.value is not None
    assert excinfo.value.code == 40160

    # State sequence: ATTACHING -> FAILED
    assert contains_in_order(channel_state_changes, [ChannelState.ATTACHING, ChannelState.FAILED])

    # Connection remains CONNECTED (channel error does not affect connection)
    assert client.connection.state == ConnectionState.CONNECTED


# UTS: realtime/proxy/RTL5f/detach-timeout-suppressed-0
async def test_rtl5f_detach_timeout_suppressed(realtime_sandbox, proxy_session):
    channel_name = f'test-RTL5f-{random_id()}'

    # Phase 1: a session with no fault rules, so the attach passes through
    session = await proxy_session(rules=[])

    client = proxied_client(realtime_sandbox.key_str, session,
                            realtime_request_timeout=REALTIME_REQUEST_TIMEOUT_MS)
    channel = client.channels.get(channel_name)

    # Record channel state changes for sequence verification
    channel_state_changes = state_recorder(channel)

    # Phase 1: Connect and attach normally through proxy
    client.connect()
    await await_connection_state(client, ConnectionState.CONNECTED, CONNECT_TIMEOUT)

    await channel.attach()
    assert channel.state == ChannelState.ATTACHED

    # Clear state change history from the attach phase
    channel_state_changes.clear()

    # Phase 2: Add rule to suppress DETACH messages
    await session.add_rules([{
        'match': {'type': 'ws_frame_to_server', 'action': 'DETACH', 'channel': channel_name},
        'action': {'type': 'suppress'},
        'comment': 'RTL5f: Suppress DETACH so server never responds',
    }], position='prepend')

    # Phase 3: Try to detach -- proxy suppresses DETACH, so server never sends DETACHED
    detach_future = asyncio.ensure_future(channel.detach())

    # Channel should enter DETACHING
    await await_channel_state(channel, ChannelState.DETACHING, PENDING_TIMEOUT)

    # Wait for the channel to revert to ATTACHED after realtimeRequestTimeout
    await await_channel_state(channel, ChannelState.ATTACHED, CHANNEL_TIMEOUT)

    # The detach() call should have failed with a timeout error
    with pytest.raises(AblyException) as excinfo:
        await asyncio.wait_for(detach_future, PENDING_TIMEOUT)

    # Channel reverted to ATTACHED (previous state)
    assert channel.state == ChannelState.ATTACHED

    # Error indicates timeout
    assert excinfo.value is not None

    # State sequence: DETACHING -> ATTACHED (revert)
    assert contains_in_order(channel_state_changes, [ChannelState.DETACHING, ChannelState.ATTACHED])

    # Connection remains CONNECTED
    assert client.connection.state == ConnectionState.CONNECTED


# UTS: realtime/proxy/RTL13a/unsolicited-detach-reattach-0
async def test_rtl13a_unsolicited_detach_reattach(realtime_sandbox, proxy_session):
    channel_name = f'test-RTL13a-{random_id()}'

    session = await proxy_session(rules=[])

    client = proxied_client(realtime_sandbox.key_str, session)
    channel = client.channels.get(channel_name)

    client.connect()
    await await_connection_state(client, ConnectionState.CONNECTED, CONNECT_TIMEOUT)

    await channel.attach()
    assert channel.state == ChannelState.ATTACHED

    # Record channel state changes from this point
    channel_state_changes = state_recorder(channel)

    # Inject an unsolicited DETACHED message with error via imperative action
    await session.trigger_action({
        'type': 'inject_to_client',
        'message': {
            'action': 13,
            'channel': channel_name,
            'error': {'code': 90198, 'statusCode': 500, 'message': 'Channel detached by server'},
        },
    })

    # Channel should transition ATTACHING (reattach) -> ATTACHED (reattach succeeds).
    # The channel is attached when this wait begins, so it is the recorded sequence that
    # is waited on rather than the state itself.
    await wall_clock_poll_until(
        lambda: contains_in_order(channel_state_changes, [ChannelState.ATTACHING, ChannelState.ATTACHED]),
        CHANNEL_TIMEOUT,
        'the channel to re-attach after the injected DETACHED',
        0.2)

    # Channel re-attached successfully
    assert channel.state == ChannelState.ATTACHED

    # State sequence: ATTACHING (with error from DETACHED) -> ATTACHED
    assert contains_in_order(channel_state_changes, [ChannelState.ATTACHING, ChannelState.ATTACHED])

    # Connection remains CONNECTED throughout
    assert client.connection.state == ConnectionState.CONNECTED

    # Proxy log shows the re-attach ATTACH message from the client: at least 2 ATTACH
    # frames, the initial attach and the reattach after the injected DETACHED
    log = await session.get_log()
    assert len(attach_frames(log, channel_name)) >= 2


# UTS: realtime/proxy/RTL14/channel-error-goes-failed-1
async def test_rtl14_channel_error_goes_failed(realtime_sandbox, proxy_session):
    channel_name = f'test-RTL14-{random_id()}'

    session = await proxy_session(rules=[])

    client = proxied_client(realtime_sandbox.key_str, session)
    channel = client.channels.get(channel_name)

    client.connect()
    await await_connection_state(client, ConnectionState.CONNECTED, CONNECT_TIMEOUT)

    await channel.attach()
    assert channel.state == ChannelState.ATTACHED

    # Record channel state changes from this point
    channel_state_changes = state_recorder(channel)

    # Inject a channel-scoped ERROR message via imperative action
    await session.trigger_action({
        'type': 'inject_to_client',
        'message': {
            'action': 9,
            'channel': channel_name,
            'error': {'code': 40160, 'statusCode': 403, 'message': 'Not permitted'},
        },
    })

    await await_channel_state(channel, ChannelState.FAILED, FAILED_TIMEOUT)

    # Channel transitioned to FAILED
    assert channel.state == ChannelState.FAILED

    # errorReason is set from the injected ERROR
    assert channel.error_reason is not None
    assert channel.error_reason.code == 40160
    assert channel.error_reason.status_code == 403
    assert 'Not permitted' in channel.error_reason.message

    # State change event shows ATTACHED -> FAILED
    assert contains_in_order(channel_state_changes, [ChannelState.FAILED])
    assert len(channel_state_changes) == 1

    # Connection remains CONNECTED (channel-scoped ERROR does not close connection)
    assert client.connection.state == ConnectionState.CONNECTED


# UTS: realtime/proxy/RTL12/attached-non-resumed-update-0
async def test_rtl12_attached_non_resumed_update(realtime_sandbox, proxy_session):
    channel_name = f'test-RTL12-{random_id()}'

    session = await proxy_session(rules=[])

    client = proxied_client(realtime_sandbox.key_str, session)
    channel = client.channels.get(channel_name)

    client.connect()
    await await_connection_state(client, ConnectionState.CONNECTED, CONNECT_TIMEOUT)

    await channel.attach()
    assert channel.state == ChannelState.ATTACHED

    # Listen for both 'update' and 'attached' events. `EventEmitter` keys its listener
    # registry on the function, so the two events take a function each.
    update_events = []
    attached_events = []

    def on_update(change):
        update_events.append(change)

    def on_attached(change):
        attached_events.append(change)

    channel.on('update', on_update)
    channel.on('attached', on_attached)

    # Inject an ATTACHED message with resumed=false and an error via imperative action
    await session.trigger_action({
        'type': 'inject_to_client',
        'message': {
            'action': 11,
            'channel': channel_name,
            'flags': 0,
            'error': {'code': 91001, 'statusCode': 500, 'message': 'Continuity lost'},
        },
    })

    # Wait for the update event to be emitted
    await wall_clock_poll_until(
        lambda: len(update_events) >= 1, FAILED_TIMEOUT, 'the channel to emit UPDATE', 0.2)

    # Channel emitted an UPDATE event
    assert len(update_events) == 1

    # The ChannelStateChange has correct fields
    assert update_events[0].current == ChannelState.ATTACHED
    assert update_events[0].previous == ChannelState.ATTACHED
    assert update_events[0].resumed is False
    assert update_events[0].reason is not None
    assert update_events[0].reason.code == 91001
    assert update_events[0].reason.status_code == 500
    assert 'Continuity lost' in update_events[0].reason.message

    # No 'attached' event was emitted (RTL2g)
    assert len(attached_events) == 0

    # Channel state remains ATTACHED
    assert channel.state == ChannelState.ATTACHED

    # Connection remains CONNECTED
    assert client.connection.state == ConnectionState.CONNECTED


# UTS: realtime/proxy/RTL3d/channels-reattach-on-reconnect-0
async def test_rtl3d_channels_reattach_on_reconnect(realtime_sandbox, proxy_session):
    channel_a_name = f'test-RTL3d-a-{random_id()}'
    channel_b_name = f'test-RTL3d-b-{random_id()}'

    session = await proxy_session(rules=[])

    client = proxied_client(realtime_sandbox.key_str, session)
    channel_a = client.channels.get(channel_a_name)
    channel_b = client.channels.get(channel_b_name)

    client.connect()
    await await_connection_state(client, ConnectionState.CONNECTED, CONNECT_TIMEOUT)

    await channel_a.attach()
    await channel_b.attach()
    assert channel_a.state == ChannelState.ATTACHED
    assert channel_b.state == ChannelState.ATTACHED

    # Record channel state changes from this point
    channel_a_state_changes = state_recorder(channel_a)
    channel_b_state_changes = state_recorder(channel_b)

    # The connection retries a drop from CONNECTED at once, so DISCONNECTED is recorded
    # rather than waited on: by the time a wait could be registered the connection may
    # already be CONNECTING again.
    connection_state_changes = state_recorder(client.connection)

    # Trigger disconnect via imperative action (close the WebSocket)
    await session.trigger_action({'type': 'close'})

    # Wait for connection to reach DISCONNECTED
    await wall_clock_poll_until(
        lambda: ConnectionState.DISCONNECTED in connection_state_changes,
        FAILED_TIMEOUT, 'the connection to report DISCONNECTED', 0.2)

    # Wait for connection to recover to CONNECTED
    await await_connection_state(client, ConnectionState.CONNECTED, 30.0)

    # Wait for both channels to re-attach. Both are attached when this wait begins, so
    # it is their recorded sequences that are waited on.
    reattached = [ChannelState.ATTACHING, ChannelState.ATTACHED]
    await wall_clock_poll_until(
        lambda: contains_in_order(channel_a_state_changes, reattached),
        CHANNEL_TIMEOUT, 'channel a to re-attach', 0.2)
    await wall_clock_poll_until(
        lambda: contains_in_order(channel_b_state_changes, reattached),
        CHANNEL_TIMEOUT, 'channel b to re-attach', 0.2)

    # Both channels end in ATTACHED state
    assert channel_a.state == ChannelState.ATTACHED
    assert channel_b.state == ChannelState.ATTACHED

    # Both channels transitioned through ATTACHING -> ATTACHED after reconnection
    assert contains_in_order(channel_a_state_changes, reattached)
    assert contains_in_order(channel_b_state_changes, reattached)

    # Connection is CONNECTED
    assert client.connection.state == ConnectionState.CONNECTED

    # Proxy log shows ATTACH messages for both channels on the second WS connection: at
    # least 2 each, the initial attach and the reattach after reconnection
    log = await session.get_log()
    assert len(attach_frames(log, channel_a_name)) >= 2
    assert len(attach_frames(log, channel_b_name)) >= 2
