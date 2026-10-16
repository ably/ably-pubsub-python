"""Derived from uts/objects/integration/proxy/objects_faults.md in ably/specification.

Spec points: RTO5a2, RTO7, RTO8, RTO17, RTO20e, RTO20e1

Each test routes a client through a `uts-proxy` session and faults the objects sync
against the real sandbox: the connection dropped on the first OBJECT_SYNC, a disconnect
while another client writes, a DETACHED injected onto an attached channel, an ATTACHED
injected to restart the sync followed by a channel ERROR while a write waits for it, and
the first OBJECT_SYNC delayed while another client writes. Only the public API is used;
the proxy's event log is the second witness where the specification reads it.

**Clients.** A client under test points at the session (`endpoint='localhost'`,
`port=session.proxy_port`, `tls=False`, `use_binary_protocol=False`) and authenticates with
an `auth_callback` returning a locally signed Ably JWT: the session speaks plain WebSocket,
over which basic auth is refused, and a JWT signed here puts nothing in the event log. The
specification's `key: api_key` on those clients is that callback. Client A, where a test
has one, goes straight to the sandbox with the key, as the specification builds it. There
is no `## Protocol Variants` section, so every client speaks JSON, which the proxy requires
in any case.

**Rules and the log.** A frame rule matches `action` as a string, and the proxy resolves
names only up to AUTH, so OBJECT_SYNC is matched as `'20'`. The log's frames carry
`direction` and a decoded `message` whose `action` is an integer.

**Transient and already-held states.** The specification's `AWAIT_STATE ... DISCONNECTED`
waits for a state the client leaves at once: it reconnects immediately (RTN15a), so the
state can be gone before a wait that starts after the fault is registered. A recorder is
registered on the connection before it connects and the waits read the recorded list,
which also tells the reconnection's CONNECTED from the first one. Likewise RTO17's
`AWAIT_STATE channel.state == attached` follows a DETACHED injected onto an attached
channel, so the wait is for ATTACHING followed by ATTACHED in the recorded sequence.

**Un-awaited calls.** `channel.attach()` and RTO20e's `pending = root.set(...)` are written
without `AWAIT`; they run as tasks. `poll_until_success` is the specification's: a read that
raises `AblyException` (the channel transiently not attached, RTO25b) means "not yet", and
the most recent such error is raised if the wait runs out. Any other error fails at once,
since it means the read is wrong rather than early.

**Cleanup.** The specification's `AFTER EACH TEST` is the fixtures': the suite closes every
client a test built and `proxy_session` closes every session it opened.

A primitive's `value()` is reached through `as_primitive()`, since ably-python's
`PathObject` is partitioned by type (RTTS); `root` is a `LiveMapPathObject`, so `set` is
called on it directly.
"""

import asyncio

import pytest

from ably.pubsub.realtime.connection import ConnectionState
from ably.pubsub.server import AblyException, PathObject
from ably.pubsub.types.channelstate import ChannelState
from test.uts.helpers.client import (
    await_channel_state,
    await_connection_state,
    sandbox_realtime_client,
    wall_clock_poll_until,
)
from test.uts.helpers.sandbox import extract_key_name, extract_key_secret, generate_jwt, random_id
from test.uts.objects.helpers.standard_test_pool import objects_channel_options

# The specification's `WITH timeout` values, as wall-clock seconds.
CONNECT_TIMEOUT = 15.0
DISCONNECT_TIMEOUT = 15.0
RECONNECT_TIMEOUT = 30.0
SYNC_TIMEOUT = 15.0
RESYNC_TIMEOUT = 30.0
REATTACH_TIMEOUT = 30.0
FAILED_TIMEOUT = 15.0
PENDING_TIMEOUT = 15.0
ACK_TIMEOUT = 10.0
VALUE_TIMEOUT = 15.0

# `poll_until_success`'s defaults, as `uts/README.md` gives them.
POLL_SUCCESS_TIMEOUT = 10.0
POLL_SUCCESS_INTERVAL = 0.5

# How often a recorded state list is re-read. The list is append-only, so nothing is
# missed at any interval; a short one keeps a wait from outlasting the reconnection.
STATE_POLL_INTERVAL = 0.05

# RTO20e's `WAIT 500ms`, for the ACKed operation to reach the wait for SYNCED.
PARK_DELAY = 0.5

# The actions `uts/docs/proxy.md` tabulates, as a logged frame's `message.action`.
ACK_ACTION = 1
OBJECT_ACTION = 19


def jwt_auth_callback(api_key):
    """The credentials of a proxied client: an Ably JWT signed locally for `api_key`."""
    key_name = extract_key_name(api_key)
    key_secret = extract_key_secret(api_key)

    async def auth_callback(params):
        return generate_jwt(key_name, key_secret)

    return auth_callback


def proxied_client(session, api_key):
    """The specification's `Realtime(options: ClientOptions(...))` pointed at `session`."""
    return sandbox_realtime_client(
        auth_callback=jwt_auth_callback(api_key),
        endpoint='localhost',
        port=session.proxy_port,
        tls=False,
        use_binary_protocol=False,
        auto_connect=False,
    )


def direct_client(api_key):
    """The specification's client A, which goes straight to the sandbox with the key."""
    return sandbox_realtime_client(api_key, auto_connect=False)


def record_states(emitter):
    """Records every state `emitter` enters from now on, in order."""
    states = []

    def on_state_change(change):
        states.append(change.current)

    emitter.on(on_state_change)
    return states


async def await_recorded_state(states, state, count=1, timeout=CONNECT_TIMEOUT):
    """This file's `AWAIT_STATE` for a connection: waits until `states` holds `count` entries of `state`."""
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


def contains_in_order(recorded, expected):
    """The specifications' `CONTAINS_IN_ORDER`: `expected` as a subsequence of `recorded`."""
    remaining = list(expected)
    for item in recorded:
        if remaining and item == remaining[0]:
            remaining.pop(0)
    return not remaining


async def bounded(awaitable, timeout, description):
    """An `AWAIT ... WITH timeout`, failing with `description` when the time runs out."""
    try:
        return await asyncio.wait_for(awaitable, timeout)
    except asyncio.TimeoutError:
        raise AssertionError(f'Timed out after {timeout}s waiting for {description}') from None


def in_background(coroutine):
    """Starts `coroutine` without awaiting it, as an un-awaited call in the specification.

    What it ends with is retrieved when it ends, so an outcome the specification does not
    assert on is not reported again as an exception nobody retrieved.
    """
    task = asyncio.ensure_future(coroutine)
    task.add_done_callback(lambda done: done.cancelled() or done.exception())
    return task


async def poll_until_success(condition, timeout=POLL_SUCCESS_TIMEOUT, description='condition'):
    """The specification's `poll_until_success`, for a read across a fault and its recovery."""
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    last_error = None
    while True:
        try:
            result = condition()
            if result:
                return result
        except AblyException as error:
            last_error = error
        if loop.time() >= deadline:
            if last_error is not None:
                raise last_error
            raise AssertionError(f'Timed out after {timeout}s waiting for {description}')
        await asyncio.sleep(POLL_SUCCESS_INTERVAL)


def object_publish_acked(log):
    """Whether the log holds the server's ACK for an OBJECT frame the client sent.

    The specification polls for any server-to-client ACK; the client sends nothing else
    that is ACKed before the `set`, so requiring the OBJECT frame first names the same
    frame and cannot be satisfied by anything else.
    """
    published = False
    for event in log:
        if event['type'] != 'ws_frame':
            continue
        action = (event.get('message') or {}).get('action')
        if event.get('direction') == 'client_to_server' and action == OBJECT_ACTION:
            published = True
        elif published and event.get('direction') == 'server_to_client' and action == ACK_ACTION:
            return True
    return False


# UTS: objects/proxy/RTO5a2-RTO17/sync-interrupted-reconnect-0
async def test_rto5a2_rto17_sync_interrupted_reconnect(realtime_sandbox, proxy_session):
    channel_name = 'objects-sync-interrupt-' + random_id()

    # Disconnect after first OBJECT_SYNC frame
    session = await proxy_session(rules=[{
        'match': {'type': 'ws_frame_to_client', 'action': '20'},
        'action': {'type': 'disconnect'},
        'times': 1,
        'comment': 'RTO5a2: Disconnect after first OBJECT_SYNC to interrupt sync',
    }])

    client = proxied_client(session, realtime_sandbox.key_str)
    channel = client.channels.get(channel_name, objects_channel_options())
    states = record_states(client.connection)

    client.connect()
    await await_recorded_state(states, ConnectionState.CONNECTED, timeout=CONNECT_TIMEOUT)

    # First attach triggers sync; proxy disconnects mid-sync
    in_background(channel.attach())
    await await_recorded_state(states, ConnectionState.DISCONNECTED, timeout=DISCONNECT_TIMEOUT)

    # Client auto-reconnects; re-attach triggers fresh sync
    await await_recorded_state(states, ConnectionState.CONNECTED, count=2, timeout=RECONNECT_TIMEOUT)

    # get() waits for SYNCED, and will only resolve if the re-sync completes
    root = await bounded(channel.object.get(), RESYNC_TIMEOUT, 'channel.object.get() after the re-sync')

    assert isinstance(root, PathObject)
    assert root.path() == ''


# UTS: objects/proxy/RTO7-RTO8/mutations-buffered-during-resync-0
async def test_rto7_rto8_mutations_buffered_during_resync(realtime_sandbox, proxy_session):
    channel_name = 'objects-buffer-resync-' + random_id()

    # Client A: direct connection (no proxy), publishes mutations
    client_a = direct_client(realtime_sandbox.key_str)
    client_a.connect()
    await await_connection_state(client_a, ConnectionState.CONNECTED, timeout=CONNECT_TIMEOUT)

    channel_a = client_a.channels.get(channel_name, objects_channel_options())
    root_a = await bounded(channel_a.object.get(), SYNC_TIMEOUT, "client A's channel.object.get()")

    # Set initial data
    await root_a.set('key1', 'initial')

    # Client B: through proxy, will be disconnected
    session = await proxy_session(rules=[])

    client_b = proxied_client(session, realtime_sandbox.key_str)
    channel_b = client_b.channels.get(channel_name, objects_channel_options())
    states_b = record_states(client_b.connection)

    # Client B connects and syncs
    client_b.connect()
    await await_recorded_state(states_b, ConnectionState.CONNECTED, timeout=CONNECT_TIMEOUT)

    root_b = await bounded(channel_b.object.get(), SYNC_TIMEOUT, "client B's channel.object.get()")
    await poll_until_success(
        lambda: root_b.get('key1').as_primitive().value() == 'initial',
        description="client B to read key1 == 'initial'")

    # Disconnect client B
    await session.trigger_action({'type': 'disconnect'})
    await await_recorded_state(states_b, ConnectionState.DISCONNECTED, timeout=DISCONNECT_TIMEOUT)

    # While B is disconnected, A publishes a mutation
    await root_a.set('key1', 'updated_during_disconnect')

    # Client B reconnects and re-syncs; the mutation should be visible
    await await_recorded_state(states_b, ConnectionState.CONNECTED, count=2, timeout=RECONNECT_TIMEOUT)

    root_b = await bounded(
        channel_b.object.get(), SYNC_TIMEOUT, "client B's channel.object.get() after reconnecting")
    await poll_until_success(
        lambda: root_b.get('key1').as_primitive().value() == 'updated_during_disconnect',
        timeout=VALUE_TIMEOUT,
        description="client B to read key1 == 'updated_during_disconnect'")

    assert root_b.get('key1').as_primitive().value() == 'updated_during_disconnect'


# UTS: objects/proxy/RTO17/server-detach-resync-0
async def test_rto17_server_detach_resync(realtime_sandbox, proxy_session):
    channel_name = 'objects-detach-resync-' + random_id()

    session = await proxy_session(rules=[])

    client = proxied_client(session, realtime_sandbox.key_str)
    channel = client.channels.get(channel_name, objects_channel_options())

    client.connect()
    await await_connection_state(client, ConnectionState.CONNECTED, timeout=CONNECT_TIMEOUT)

    root = await bounded(channel.object.get(), SYNC_TIMEOUT, 'channel.object.get()')

    # Set some data. The write is applied locally once the server ACKs it (RTO20), so it
    # reads back as soon as `set` returns.
    await root.set('before_detach', 'hello')
    assert root.get('before_detach').as_primitive().value() == 'hello'

    channel_states = record_states(channel)

    # Inject server-initiated DETACHED
    await session.trigger_action({
        'type': 'inject_to_client',
        'message': {
            'action': 13,
            'channel': channel_name,
        },
    })

    # Client should auto-re-attach (RTL13a). The channel is ATTACHED when the wait begins,
    # so it is the recorded re-attach that is waited for.
    try:
        await wall_clock_poll_until(
            lambda: contains_in_order(channel_states, [ChannelState.ATTACHING, ChannelState.ATTACHED]),
            timeout=REATTACH_TIMEOUT,
            description='the channel to re-attach after the injected DETACHED',
            interval=STATE_POLL_INTERVAL)
    except AssertionError as error:
        recorded = [recorded_state.value for recorded_state in channel_states]
        raise AssertionError(f'{error}; the channel states recorded were {recorded}') from None
    assert channel.state == ChannelState.ATTACHED

    # Re-sync should restore data
    root = await bounded(channel.object.get(), SYNC_TIMEOUT, 'channel.object.get() after the re-attach')
    await poll_until_success(
        lambda: root.get('before_detach').as_primitive().value() == 'hello',
        timeout=VALUE_TIMEOUT,
        description="before_detach to read 'hello' after the re-sync")

    assert root.get('before_detach').as_primitive().value() == 'hello'


# UTS: objects/proxy/RTO20e/publish-fails-on-channel-failed-0
async def test_rto20e_publish_fails_on_channel_failed(realtime_sandbox, proxy_session):
    channel_name = 'objects-publish-failed-' + random_id()

    session = await proxy_session(rules=[])

    client = proxied_client(session, realtime_sandbox.key_str)
    channel = client.channels.get(channel_name, objects_channel_options())

    client.connect()
    await await_connection_state(client, ConnectionState.CONNECTED, timeout=CONNECT_TIMEOUT)

    root = await bounded(channel.object.get(), SYNC_TIMEOUT, 'channel.object.get()')

    # Force the objects back into SYNCING: inject an ATTACHED (action 11) carrying the
    # HAS_OBJECTS flag (bit 7, i.e. flags: 128). RTO4c starts a new sync sequence on every
    # ATTACHED protocol message; the server never sent this ATTACHED, so no OBJECT_SYNC
    # follows and the objects remain SYNCING. The channel itself stays ATTACHED.
    await session.trigger_action({
        'type': 'inject_to_client',
        'message': {'action': 11, 'channel': channel_name, 'flags': 128},
    })

    # Mutate WHILE SYNCING: the channel is ATTACHED so the write preconditions (RTO26)
    # pass and the publish + ACK complete against the real server; publishAndApply then
    # waits for a SYNCED that will never arrive (RTO20e). Do not await yet.
    pending = asyncio.ensure_future(root.set('key', 'value'))

    # Ensure the operation is in the RTO20e sync-wait, not still publishing: wait until
    # the proxy log shows the server's ACK for the OBJECT publish, then allow a brief
    # real-time yield for the client to move the ACKed operation into the wait.
    async def acked():
        return object_publish_acked(await session.get_log())

    await wall_clock_poll_until(acked, timeout=ACK_TIMEOUT, description='the server to ACK the OBJECT publish')
    await asyncio.sleep(PARK_DELAY)

    # The channel enters FAILED whilst the operation waits for SYNCED (RTO20e1)
    await session.trigger_action({
        'type': 'inject_to_client',
        'message': {
            'action': 9,
            'channel': channel_name,
            'error': {'statusCode': 400, 'code': 90000, 'message': 'injected error'},
        },
    })

    await await_channel_state(channel, ChannelState.FAILED, timeout=FAILED_TIMEOUT)

    with pytest.raises(AblyException) as excinfo:
        await bounded(pending, PENDING_TIMEOUT, 'the pending set() to fail')

    error = excinfo.value
    assert error.code == 92008
    assert error.status_code == 400
    # RTO20e1: cause is set to RealtimeChannel.errorReason, the injected channel ERROR
    assert error.cause is not None
    assert error.cause.code == 90000


# UTS: objects/proxy/RTO5-RTO7/publish-during-sync-echo-after-0
async def test_rto5_rto7_publish_during_sync_echo_after(realtime_sandbox, proxy_session):
    channel_name = 'objects-publish-during-sync-' + random_id()

    # Client A: direct, no proxy
    client_a = direct_client(realtime_sandbox.key_str)
    client_a.connect()
    await await_connection_state(client_a, ConnectionState.CONNECTED, timeout=CONNECT_TIMEOUT)

    channel_a = client_a.channels.get(channel_name, objects_channel_options())
    root_a = await bounded(channel_a.object.get(), SYNC_TIMEOUT, "client A's channel.object.get()")

    # Set up initial data
    await root_a.set('existing', 'before')

    # Client B: through proxy with delayed OBJECT_SYNC
    session = await proxy_session(rules=[{
        'match': {'type': 'ws_frame_to_client', 'action': '20'},
        'action': {'type': 'delay', 'delayMs': 3000},
        'times': 1,
        'comment': 'Delay first OBJECT_SYNC to keep B in SYNCING state',
    }])

    client_b = proxied_client(session, realtime_sandbox.key_str)
    channel_b = client_b.channels.get(channel_name, objects_channel_options())

    # Start client B, which stays SYNCING while its first OBJECT_SYNC is delayed
    client_b.connect()
    await await_connection_state(client_b, ConnectionState.CONNECTED, timeout=CONNECT_TIMEOUT)
    in_background(channel_b.attach())

    # While B is syncing, A publishes a mutation
    await root_a.set('existing', 'after')

    # B's get() will resolve once the delayed sync completes
    root_b = await bounded(channel_b.object.get(), RESYNC_TIMEOUT, "client B's channel.object.get()")

    # The mutation from A should be visible (either in sync data or buffered OBJECT)
    await poll_until_success(
        lambda: root_b.get('existing').as_primitive().value() == 'after',
        timeout=VALUE_TIMEOUT,
        description="client B to read existing == 'after'")

    assert root_b.get('existing').as_primitive().value() == 'after'
