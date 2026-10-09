"""Derived from uts/objects/unit/realtime_object.md in ably/specification.

Spec points: RTO2, RTO2a, RTO2b, RTO5c9, RTO10, RTO10a, RTO10b1, RTO10c1b, RTO10c1b1, RTO15,
RTO15e1, RTO15e2, RTO15e3, RTO17, RTO17b, RTO18, RTO18b, RTO18d, RTO18e, RTO19, RTO20, RTO20b,
RTO20c1, RTO20d1, RTO20d2, RTO20d4, RTO20e, RTO20e1, RTO20f, RTO23, RTO23a, RTO23c, RTO23c1,
RTO23d, RTO23e, RTO24a, RTO24c1, RTO25a, RTO25b, RTO26a, RTO26b, RTO26c, RTO27a, RTO27b, RTL33b,
RTL33c, RTLO4e10

The specification drives `channel.object` against the mock websocket, and reaches into the
RealtimeObject where nothing public observes what it asserts: the channel-state handler
(`_act_on_channel_state`), the pool (`_objects_pool`), the sync state (`_sync_state`) and the
GC interval (`_gc_interval_ms`).

Several translations recur through the file.

Every OBJECT the client publishes is ACKed, by the standard mock or by a test's own handler,
because a publish resolves only on its ACK (RTO15g). The one test whose specification sends
the ACK by hand, `ack-after-echo-no-double-apply`, drives the write as a task and ACKs it once
the OBJECT has left the client.

The specifications' untyped `PathObject` calls go through the typed views:
`root.get("score").value()` is `root.get('score').as_live_counter().value()`, and
`root.get("name").value()` is `root.get('name').as_primitive().value()`.

The modes a server grants travel as bits of the ATTACHED `flags`, so the specification's
`modes: ["OBJECT_SUBSCRIBE"]` is `flags=HAS_OBJECTS | OBJECT_SUBSCRIBE_FLAG`.

An inbound frame is processed on the transport's read task, so state is read after a
`poll_until` or a `settle()`, and a negative assertion ("the listener did not fire", "the echo
did not apply") follows a positive control delivered behind the message under test.

`enable_fake_timers()` is a `FakeClock` given to the client, which is where the GC timer
(RTO10a) is scheduled and where `now_ms()` is read for a sweep (RTO10c1b).
"""

import asyncio

import pytest

from ably.pubsub.objects.enums import ObjectsEvent, ObjectsSyncState
from ably.pubsub.objects.objectmessage import ObjectOperationAction
from ably.pubsub.objects.pathobject import PathObject
from ably.pubsub.objects.valuetypes import LiveCounter
from ably.pubsub.transport.websockettransport import ProtocolMessageAction
from ably.pubsub.types.channelmode import ChannelMode
from ably.pubsub.types.channelstate import ChannelState
from ably.pubsub.util.exceptions import AblyException
from test.uts.helpers.client import await_channel_state, poll_until
from test.uts.helpers.clock import FakeClock, settle
from test.uts.helpers.mock_websocket import MockWebSocket, channel_error_message, contains_in_order
from test.uts.objects.helpers.standard_test_pool import (
    ATTACH,
    HAS_OBJECTS,
    OBJECT,
    OBJECT_PUBLISH_FLAG,
    OBJECT_SUBSCRIBE_FLAG,
    SITE_CODE,
    STANDARD_POOL_OBJECTS,
    ack_serial,
    assert_unchanged_after_quiescence,
    below_ack_serial,
    build_ack_message,
    build_counter_inc,
    build_map_set,
    build_object_delete,
    build_object_message,
    build_object_sync_message,
    objects_attached_message,
    objects_channel_options,
    objects_client,
    objects_connected_message,
    remote_serial,
    setup_synced_channel,
    setup_synced_channel_no_ack,
    standard_mock_websocket,
)

# How long a test waits on an operation it expects to complete or fail, so that one which
# never settles fails with a timeout rather than running into the suite's own
OPERATION_TIMEOUT = 5

# RTO10b3's default grace period and RTO10a's example interval, which the GC tests advance past
DEFAULT_GC_GRACE_PERIOD_MS = 86_400_000
DEFAULT_GC_INTERVAL_MS = 300_000


def _score(root):
    """The value of the standard pool's `score` counter, read through the counter view."""
    return root.get('score').as_live_counter().value()


def _nested_counter(root):
    """The value of the standard pool's `profile.nested_counter` counter."""
    return root.get('profile').get('nested_counter').as_live_counter().value()


def _name(root):
    """The standard pool's `name` primitive, read through the primitive view."""
    return root.get('name').as_primitive().value()


def _sent(mock_ws, action):
    """How many protocol messages carrying `action` the client has sent."""
    return sum(1 for message in mock_ws.messages_from_client if message.get('action') == int(action))


def _raise_if_failed(task):
    """Re-raises the exception `task` finished with, so that an early failure reports itself."""
    if task.done() and not task.cancelled() and task.exception() is not None:
        raise task.exception()


def _assert_pending(task, description):
    """Asserts `task` is still waiting; a task that already failed re-raises its own error."""
    _raise_if_failed(task)
    assert not task.done(), f'{description} completed while it should still be waiting'


async def _await_sent(mock_ws, action, task):
    """Waits for the client to send a message carrying `action` on behalf of `task`."""
    await poll_until(lambda: task.done() or _sent(mock_ws, action) >= 1,
                     description=f'the client to send a message with action {int(action)}')
    _raise_if_failed(task)


async def _restart_sync(channel, mock_ws, channel_serial='sync2:cursor'):
    """Sends an ATTACHED carrying a sync cursor and waits for the sync state to leave SYNCED.

    A new ATTACHED moves the sync state to SYNCING (RTO4c), and the cursor keeps it there
    until an OBJECT_SYNC completes the sequence.
    """
    mock_ws.send_to_client(objects_attached_message(channel.name, channel_serial))
    await poll_until(lambda: channel.object._sync_state == ObjectsSyncState.SYNCING,
                     description='the ATTACHED to restart the objects sync')


def _acking_mock_websocket(serials, captured=None, **kwargs):
    """The standard mock, ACKing each OBJECT with the serials `serials(message)` gives.

    Each OBJECT is recorded in `captured` first, if given. `kwargs` go to
    `standard_mock_websocket`.
    """
    mock_ws = None

    def on_object(message):
        if captured is not None:
            captured.append(message)
        mock_ws.send_to_client(build_ack_message(message['msgSerial'], serials(message)))

    mock_ws = standard_mock_websocket(auto_ack=False, on_object=on_object, **kwargs)
    return mock_ws


# UTS: objects/unit/RTO23/get-returns-path-object-0
async def test_rto23_get_returns_path_object():
    client, channel, root, mock_ws = await setup_synced_channel('test')

    assert isinstance(root, PathObject)
    assert root._path == []
    # RTO23d: the root is the pool's InternalLiveMap with id `root`
    assert root._root is channel.object._objects_pool['root']


# UTS: objects/unit/RTO23a/get-requires-subscribe-mode-0
async def test_rto23a_get_requires_subscribe_mode():
    mock_ws = standard_mock_websocket(sync_objects=None)
    client = objects_client(mock_ws)
    channel = client.channels.get('test', objects_channel_options(ChannelMode.OBJECT_PUBLISH))

    with pytest.raises(AblyException) as excinfo:
        await channel.object.get()

    assert excinfo.value.code == 40024


# UTS: objects/unit/RTO23e/get-reattaches-detached-0
async def test_rto23e_get_reattaches_detached():
    client, channel, root, mock_ws = await setup_synced_channel('test', modes=(ChannelMode.OBJECT_SUBSCRIBE,))

    await channel.detach()
    assert channel.state == ChannelState.DETACHED

    root = await asyncio.wait_for(channel.object.get(), OPERATION_TIMEOUT)

    assert isinstance(root, PathObject)
    assert root._path == []
    assert channel.state == ChannelState.ATTACHED


# UTS: objects/unit/RTO23c/get-waits-for-synced-0
async def test_rto23c_get_waits_for_synced():
    mock_ws = standard_mock_websocket(attached_channel_serial='sync1:cursor', sync_objects=None)
    client = objects_client(mock_ws)
    channel = client.channels.get('test', objects_channel_options())

    task = asyncio.ensure_future(channel.object.get())
    await _await_sent(mock_ws, ProtocolMessageAction.ATTACH, task)

    # The ATTACHED carries a sync cursor and no OBJECT_SYNC has arrived, so get() must still
    # be waiting for SYNCED
    await settle()
    _assert_pending(task, 'get()')

    mock_ws.send_to_client(build_object_sync_message('test', 'sync1:', STANDARD_POOL_OBJECTS))
    root = await asyncio.wait_for(task, OPERATION_TIMEOUT)

    assert isinstance(root, PathObject)
    assert root._path == []


# UTS: objects/unit/RTO23c1/fails-on-channel-detached-0
async def test_rto23c1_fails_on_channel_detached():
    client, channel, root, mock_ws = await setup_synced_channel('test')
    await _restart_sync(channel, mock_ws)

    task = asyncio.ensure_future(channel.object.get())
    await settle()
    _assert_pending(task, 'get()')

    await channel.detach()

    with pytest.raises(AblyException) as excinfo:
        await asyncio.wait_for(task, OPERATION_TIMEOUT)

    assert excinfo.value.code == 92008
    assert excinfo.value.status_code == 400


# UTS: objects/unit/RTO23c1/fails-on-channel-suspended-0
async def test_rto23c1_fails_on_channel_suspended():
    client, channel, root, mock_ws = await setup_synced_channel('test')
    await _restart_sync(channel, mock_ws)

    task = asyncio.ensure_future(channel.object.get())
    await settle()
    _assert_pending(task, 'get()')

    # The mock cannot drive the channel to SUSPENDED, so the RealtimeObject's channel-state
    # handler is called directly, as the RTO27 test does
    channel.object._act_on_channel_state(ChannelState.SUSPENDED)

    with pytest.raises(AblyException) as excinfo:
        await asyncio.wait_for(task, OPERATION_TIMEOUT)

    assert excinfo.value.code == 92008
    assert excinfo.value.status_code == 400


# UTS: objects/unit/RTO23c1/fails-on-channel-failed-0
async def test_rto23c1_fails_on_channel_failed():
    client, channel, root, mock_ws = await setup_synced_channel('test')
    await _restart_sync(channel, mock_ws)

    task = asyncio.ensure_future(channel.object.get())
    await settle()
    _assert_pending(task, 'get()')

    mock_ws.send_to_client(channel_error_message('test', 90000, 'Channel failed', 400))

    with pytest.raises(AblyException) as excinfo:
        await asyncio.wait_for(task, OPERATION_TIMEOUT)

    assert excinfo.value.code == 92008
    assert excinfo.value.status_code == 400
    # The cause is the channel's errorReason, the injected channel error
    assert excinfo.value.cause.code == 90000


# UTS: objects/unit/RTO15/publish-sends-object-pm-0
async def test_rto15_publish_sends_object_pm():
    captured = []
    mock_ws = _acking_mock_websocket(lambda message: ['serial-0'], captured)
    client, channel, root, mock_ws = await setup_synced_channel('test', mock_ws=mock_ws)

    await root.get('score').as_live_counter().increment(5)

    assert len(captured) == 1
    assert captured[0]['action'] == OBJECT
    assert captured[0]['channel'] == 'test'
    assert len(captured[0]['state']) == 1
    # RTO15e3: the state entry is the encoded ObjectMessage for the increment
    operation = captured[0]['state'][0]['operation']
    assert operation['action'] == ObjectOperationAction.COUNTER_INC
    assert operation['objectId'] == 'counter:score@1000'
    assert operation['counterInc']['number'] == 5


# UTS: objects/unit/RTO20/publish-and-apply-local-0
async def test_rto20_publish_and_apply_local():
    client, channel, root, mock_ws = await setup_synced_channel('test')

    await root.get('score').as_live_counter().increment(10)

    assert _score(root) == 110


# UTS: objects/unit/RTO20c/missing-site-code-0
async def test_rto20c_missing_site_code():
    captured = []
    mock_ws = _acking_mock_websocket(lambda message: ['serial-0'], captured,
                                     connected=objects_connected_message(site_code=None))
    client, channel, root, mock_ws = await setup_synced_channel('test', mock_ws=mock_ws)

    await root.get('score').as_live_counter().increment(10)

    # The increment was published and ACKed, so its not being applied is the siteCode's doing
    assert len(captured) == 1
    assert _score(root) == 100


# UTS: objects/unit/RTO20d1/null-serial-skipped-0
async def test_rto20d1_null_serial_skipped():
    captured = []
    mock_ws = _acking_mock_websocket(lambda message: [None], captured)
    client, channel, root, mock_ws = await setup_synced_channel('test', mock_ws=mock_ws)

    await root.get('score').as_live_counter().increment(10)

    # The increment was published and ACKed, so its not being applied is the null serial's doing
    assert len(captured) == 1
    assert _score(root) == 100


# UTS: objects/unit/RTO20d4/empty-synthetic-list-skips-sync-wait-0
async def test_rto20d4_empty_synthetic_list_skips_sync_wait():
    mock_ws = _acking_mock_websocket(lambda message: [None])
    client, channel, root, mock_ws = await setup_synced_channel('test', mock_ws=mock_ws)

    # Back to SYNCING, where a write with something to apply would wait for SYNCED (RTO20e).
    # No OBJECT_SYNC is ever sent, so the increment completing at all shows the wait was skipped.
    await _restart_sync(channel, mock_ws)

    await asyncio.wait_for(root.get('score').as_live_counter().increment(10), OPERATION_TIMEOUT)

    assert channel.object._sync_state == ObjectsSyncState.SYNCING
    assert _score(root) == 100


# UTS: objects/unit/RTO20d4/mixed-null-serials-applies-non-null-0
async def test_rto20d4_mixed_null_serials_applies_non_null():
    # The set() publishes [COUNTER_CREATE, MAP_SET] (RTLM20h1); the CREATE is ACKed with a
    # null serial and skipped (RTO20d1), and the MAP_SET with a real one and applied
    mock_ws = _acking_mock_websocket(lambda message: [None, ack_serial(message['msgSerial'], 1)])
    client, channel, root, mock_ws = await setup_synced_channel('test', mock_ws=mock_ws)

    await root.set('child', LiveCounter.create(0))

    assert 'child' in root.keys()
    # The seven standard-pool entries and `child`
    assert root.size() == 8


# UTS: objects/unit/RTO20e/waits-for-synced-0
async def test_rto20e_waits_for_synced():
    client, channel, root, mock_ws = await setup_synced_channel('test')
    await _restart_sync(channel, mock_ws)

    task = asyncio.ensure_future(root.get('score').as_live_counter().increment(10))

    # The OBJECT is published and ACKed; while still SYNCING the increment must wait, unapplied
    await _await_sent(mock_ws, ProtocolMessageAction.OBJECT, task)
    await settle()
    _assert_pending(task, 'increment()')
    assert _score(root) == 100

    mock_ws.send_to_client(build_object_sync_message('test', 'sync2:', STANDARD_POOL_OBJECTS))
    await asyncio.wait_for(task, OPERATION_TIMEOUT)

    assert _score(root) == 110


# UTS: objects/unit/RTO20e1/fails-on-channel-detached-0
async def test_rto20e1_fails_on_channel_detached():
    client, channel, root, mock_ws = await setup_synced_channel('test')
    await _restart_sync(channel, mock_ws)

    task = asyncio.ensure_future(root.get('score').as_live_counter().increment(10))

    # The publish and its ACK complete against the mock, and the increment waits for SYNCED
    await _await_sent(mock_ws, ProtocolMessageAction.OBJECT, task)
    await settle()
    _assert_pending(task, 'increment()')

    await channel.detach()

    with pytest.raises(AblyException) as excinfo:
        await asyncio.wait_for(task, OPERATION_TIMEOUT)

    assert excinfo.value.code == 92008
    # RTO20e1 gives the status code as well
    assert excinfo.value.status_code == 400


# UTS: objects/unit/RTO20e1/fails-on-channel-failed-0
async def test_rto20e1_fails_on_channel_failed():
    client, channel, root, mock_ws = await setup_synced_channel('test')
    await _restart_sync(channel, mock_ws)

    task = asyncio.ensure_future(root.get('score').as_live_counter().increment(10))

    # The publish and its ACK complete against the mock, and the increment waits for SYNCED
    await _await_sent(mock_ws, ProtocolMessageAction.OBJECT, task)
    await settle()
    _assert_pending(task, 'increment()')

    mock_ws.send_to_client(channel_error_message('test', 90000, 'Channel failed', 400))

    with pytest.raises(AblyException) as excinfo:
        await asyncio.wait_for(task, OPERATION_TIMEOUT)

    assert excinfo.value.code == 92008
    # RTO20e1 gives the status code, and the channel's errorReason as the cause
    assert excinfo.value.status_code == 400
    assert excinfo.value.cause.code == 90000


# UTS: objects/unit/RTO17/sync-state-events-0
async def test_rto17_sync_state_events():
    mock_ws = standard_mock_websocket(attached_channel_serial='sync1:cursor', sync_objects=None)
    client = objects_client(mock_ws)
    channel = client.channels.get('test', objects_channel_options())

    events = []
    channel.object.on(ObjectsEvent.SYNCING, lambda: events.append('SYNCING'))
    channel.object.on(ObjectsEvent.SYNCED, lambda: events.append('SYNCED'))

    task = asyncio.ensure_future(channel.object.get())
    await poll_until(lambda: task.done() or len(events) >= 1, description='the SYNCING event')
    _raise_if_failed(task)

    mock_ws.send_to_client(build_object_sync_message('test', 'sync1:', STANDARD_POOL_OBJECTS))
    await asyncio.wait_for(task, OPERATION_TIMEOUT)

    assert contains_in_order(events, ['SYNCING', 'SYNCED']), events


# UTS: objects/unit/RTO18d/duplicate-listener-0
async def test_rto18d_duplicate_listener():
    client, channel, root, mock_ws = await setup_synced_channel('test')
    calls = []

    def listener():
        calls.append('SYNCED')

    channel.object.on(ObjectsEvent.SYNCED, listener)
    channel.object.on(ObjectsEvent.SYNCED, listener)

    mock_ws.send_to_client(objects_attached_message('test', 'sync2:cursor'))
    mock_ws.send_to_client(build_object_sync_message('test', 'sync2:', STANDARD_POOL_OBJECTS))
    await poll_until(lambda: len(calls) >= 2, description='the listener to be called twice')
    await settle()

    assert len(calls) == 2


# UTS: objects/unit/RTO19/off-deregisters-0
async def test_rto19_off_deregisters():
    client, channel, root, mock_ws = await setup_synced_channel('test')
    calls = []

    def listener():
        calls.append('SYNCED')

    subscription = channel.object.on(ObjectsEvent.SYNCED, listener)
    subscription.off()

    # A second listener on the same event is the control which shows the SYNCED was emitted
    control = []
    channel.object.on(ObjectsEvent.SYNCED, lambda: control.append('SYNCED'))

    mock_ws.send_to_client(objects_attached_message('test', 'sync2:cursor'))
    mock_ws.send_to_client(build_object_sync_message('test', 'sync2:', STANDARD_POOL_OBJECTS))
    await assert_unchanged_after_quiescence(lambda: len(calls), lambda: len(control) >= 1,
                                            description='the control listener receives SYNCED')

    assert len(calls) == 0


# UTS: objects/unit/RTO2/mode-enforcement-0
async def test_rto2_mode_enforcement():
    # The server grants OBJECT_SUBSCRIBE only, where the channel requested both modes
    mock_ws = standard_mock_websocket(attached_flags=HAS_OBJECTS | OBJECT_SUBSCRIBE_FLAG)
    client, channel, root, mock_ws = await setup_synced_channel('test', mock_ws=mock_ws)

    with pytest.raises(AblyException) as excinfo:
        await root.set('name', 'Bob')

    assert excinfo.value.code == 40024


# UTS: objects/unit/RTO23e/get-rejects-failed-0
async def test_rto23e_get_rejects_failed():
    mock_ws = None

    def on_message_from_client(message):
        if message.get('action') == ATTACH:
            mock_ws.send_to_client(channel_error_message(message.get('channel'), 90000, 'Channel error', 400))

    mock_ws = MockWebSocket(
        on_connection_attempt=lambda conn: conn.respond_with_success(objects_connected_message()),
        on_message_from_client=on_message_from_client,
    )
    client = objects_client(mock_ws)
    channel = client.channels.get('test', objects_channel_options(ChannelMode.OBJECT_SUBSCRIBE))

    # The attach fails, which leaves the channel FAILED
    with pytest.raises(AblyException):
        await channel.attach()
    assert channel.state == ChannelState.FAILED

    with pytest.raises(AblyException) as excinfo:
        await channel.object.get()

    assert excinfo.value.code == 90001
    assert excinfo.value.status_code == 400


# UTS: objects/unit/RTO25a/access-requires-subscribe-mode-0
async def test_rto25a_access_requires_subscribe_mode():
    mock_ws = standard_mock_websocket(attached_flags=HAS_OBJECTS | OBJECT_PUBLISH_FLAG)
    client = objects_client(mock_ws)
    channel = client.channels.get('test', objects_channel_options(ChannelMode.OBJECT_PUBLISH))

    with pytest.raises(AblyException) as excinfo:
        await channel.object.get()

    assert excinfo.value.code == 40024
    assert excinfo.value.status_code == 400


# UTS: objects/unit/RTO25b/access-throws-detached-0
async def test_rto25b_access_throws_detached():
    client, channel, root, mock_ws = await setup_synced_channel('test')

    await channel.detach()
    assert channel.state == ChannelState.DETACHED

    with pytest.raises(AblyException) as excinfo:
        root.keys()

    assert excinfo.value.code == 90001
    assert excinfo.value.status_code == 400


# UTS: objects/unit/RTO25b/access-throws-failed-0
async def test_rto25b_access_throws_failed():
    client, channel, root, mock_ws = await setup_synced_channel('test')

    mock_ws.send_to_client(channel_error_message('test', 90000, 'Channel error', 400))
    await await_channel_state(channel, ChannelState.FAILED)

    with pytest.raises(AblyException) as excinfo:
        root.keys()

    assert excinfo.value.code == 90001
    assert excinfo.value.status_code == 400


# UTS: objects/unit/RTO26a/write-requires-publish-mode-0
async def test_rto26a_write_requires_publish_mode():
    mock_ws = standard_mock_websocket(attached_flags=HAS_OBJECTS | OBJECT_SUBSCRIBE_FLAG)
    client, channel, root, mock_ws = await setup_synced_channel('test', mock_ws=mock_ws,
                                                                modes=(ChannelMode.OBJECT_SUBSCRIBE,))

    with pytest.raises(AblyException) as excinfo:
        await root.set('name', 'Bob')

    assert excinfo.value.code == 40024
    assert excinfo.value.status_code == 400


# UTS: objects/unit/RTO26b/write-throws-detached-0
async def test_rto26b_write_throws_detached():
    client, channel, root, mock_ws = await setup_synced_channel('test')

    await channel.detach()
    assert channel.state == ChannelState.DETACHED

    with pytest.raises(AblyException) as excinfo:
        await root.set('name', 'Bob')

    assert excinfo.value.code == 90001
    assert excinfo.value.status_code == 400


# UTS: objects/unit/RTO26b/write-throws-failed-0
async def test_rto26b_write_throws_failed():
    client, channel, root, mock_ws = await setup_synced_channel('test')

    mock_ws.send_to_client(channel_error_message('test', 90000, 'Channel error', 400))
    await await_channel_state(channel, ChannelState.FAILED)

    with pytest.raises(AblyException) as excinfo:
        await root.set('name', 'Bob')

    assert excinfo.value.code == 90001
    assert excinfo.value.status_code == 400


# UTS: objects/unit/RTO26c/write-throws-echo-disabled-0
async def test_rto26c_write_throws_echo_disabled():
    client, channel, root, mock_ws = await setup_synced_channel('test', echo_messages=False)

    with pytest.raises(AblyException) as excinfo:
        await root.set('name', 'Bob')

    assert excinfo.value.code == 40000
    assert excinfo.value.status_code == 400


# UTS: objects/unit/RTO24a/single-register-instance-0
async def test_rto24a_single_register_instance():
    client, channel, root, mock_ws = await setup_synced_channel('test')
    events_root = []
    events_score = []

    root.subscribe(events_root.append)
    score_path = root.get('score')
    score_path.subscribe(events_score.append)

    # `remote` has no entry in the counter's siteTimeserials, so the increment is new (RTLO4a)
    mock_ws.send_to_client(build_object_message('test', [
        build_counter_inc('counter:score@1000', 5, 't:1', 'remote'),
    ]))
    await poll_until(lambda: len(events_score) >= 1, description='the score subscription to fire')

    # Both subscriptions are held by the one register, so both fire
    assert len(events_root) >= 1
    assert len(events_score) >= 1


# UTS: objects/unit/RTO24c1/coverage-prefix-depth-0
async def test_rto24c1_coverage_prefix_depth():
    client, channel, root, mock_ws = await setup_synced_channel('test')
    shallow_events = []
    deep_events = []

    # With depth 1 a subscription at the root covers the root's own path only; a child such
    # as ['score'] is at relative depth 2 (RTO24c2b)
    root.subscribe(shallow_events.append, depth=1)
    root.subscribe(deep_events.append)

    # A MAP_SET on the root itself, at path []
    mock_ws.send_to_client(build_object_message('test', [
        build_map_set('root', 'name', {'string': 'Bob'}, remote_serial(0), 'remote'),
    ]))
    await poll_until(lambda: len(deep_events) >= 1, description='the deep subscription to see the root update')

    # An increment on the root's child, at path ['score']
    mock_ws.send_to_client(build_object_message('test', [
        build_counter_inc('counter:score@1000', 5, 't:2', 'remote'),
    ]))
    await poll_until(lambda: len(deep_events) >= 2, description='the deep subscription to see the child update')
    await poll_until(lambda: len(shallow_events) >= 1,
                     description='the shallow subscription to see the root update')
    await settle()

    # The shallow subscription sees the root update only; the deep one both
    assert len(shallow_events) == 1
    assert len(deep_events) >= 2


# UTS: objects/unit/RTO10/gc-tombstoned-objects-0
async def test_rto10_gc_tombstoned_objects():
    clock = FakeClock()
    client, channel, root, mock_ws = await setup_synced_channel('test', clock=clock)
    pool = channel.object._objects_pool

    # A tombstone stamped now, which only the advance below makes eligible for collection
    mock_ws.send_to_client(build_object_message('test', [
        build_object_delete('counter:score@1000', '99', 'site1', clock.now_ms()),
    ]))
    await poll_until(lambda: pool['counter:score@1000'].is_tombstone,
                     description='the OBJECT_DELETE to tombstone the score counter')

    await clock.advance(DEFAULT_GC_GRACE_PERIOD_MS + DEFAULT_GC_INTERVAL_MS)

    assert _score(root) is None
    # UTS SPEC ERROR: the specification asserts only that `score` reads null, which holds
    # from the moment the counter is tombstoned (RTLM14c, RTLM5d2h), with or without a GC
    # sweep. The sweep itself is observed as the counter leaving the pool (RTO10c1b).
    assert 'counter:score@1000' not in pool


# UTS: objects/unit/RTO10c1b1/gc-root-never-removed-0
async def test_rto10c1b1_gc_root_never_removed():
    clock = FakeClock()
    client, channel, root, mock_ws = await setup_synced_channel('test', clock=clock)
    pool = channel.object._objects_pool
    root_map = pool['root']

    # A rogue OBJECT_DELETE targeting the root, which RTLO4e10 rejects
    mock_ws.send_to_client(build_object_message('test', [
        build_object_delete('root', remote_serial(0), 'remote', clock.now_ms()),
    ]))
    # The score counter is tombstoned behind it: the control which shows the rogue delete has
    # been processed, and, once collected, that a GC sweep has run past the grace period
    mock_ws.send_to_client(build_object_message('test', [
        build_object_delete('counter:score@1000', '99', 'site1', clock.now_ms()),
    ]))
    await poll_until(lambda: pool['counter:score@1000'].is_tombstone,
                     description='the control OBJECT_DELETE to tombstone the score counter')

    # The root is not tombstoned and its data is untouched
    assert _name(root) == 'Alice'
    assert root_map.is_tombstone is False

    await clock.advance(DEFAULT_GC_GRACE_PERIOD_MS + DEFAULT_GC_INTERVAL_MS)

    assert 'counter:score@1000' not in pool
    assert pool['root'] is root_map

    # The root is still live: an operation still applies to the root object the client holds
    mock_ws.send_to_client(build_object_message('test', [
        build_map_set('root', 'name', {'string': 'Bob'}, remote_serial(1), 'remote'),
    ]))
    await poll_until(lambda: _name(root) == 'Bob', description='the MAP_SET to apply to the root')

    assert _name(root) == 'Bob'


# UTS: objects/unit/RTO20/echo-dedup-0
async def test_rto20_echo_dedup():
    client, channel, root, mock_ws = await setup_synced_channel('test')

    await root.get('score').as_live_counter().increment(10)
    score_after_apply = _score(root)

    # The echo of the increment, carrying the serial it was ACKed and applied with
    mock_ws.send_to_client(build_object_message('test', [
        build_counter_inc('counter:score@1000', 10, ack_serial(0, 0), SITE_CODE),
    ]))
    # A control behind the echo on the same connection, which shows the echo has been processed
    mock_ws.send_to_client(build_object_message('test', [
        build_counter_inc('counter:nested@1000', 1, remote_serial(0), 'remote'),
    ]))
    await assert_unchanged_after_quiescence(lambda: _score(root), lambda: _nested_counter(root) == 6,
                                            description='the control increment has applied')
    score_after_echo = _score(root)

    assert score_after_apply == 110
    assert score_after_echo == 110


# UTS: objects/unit/RTO20f/ack-no-site-timeserials-update-0
async def test_rto20f_ack_no_site_timeserials_update():
    client, channel, root, mock_ws = await setup_synced_channel('test')

    await root.get('score').as_live_counter().increment(10)
    assert _score(root) == 110

    # `below_ack_serial(9)` is not the ACK serial, so the echo dedup (RTO9a3) leaves it alone,
    # and it sorts below `ack_serial(0, 0)`, so it is rejected as stale (RTLO4a) if and only if
    # the LOCAL apply recorded the ACK serial in siteTimeserials
    mock_ws.send_to_client(build_object_message('test', [
        build_counter_inc('counter:score@1000', 10, below_ack_serial(9), SITE_CODE),
    ]))
    await poll_until(lambda: _score(root) == 120, description='the inbound increment to apply')

    assert _score(root) == 120


# UTS: objects/unit/RTO20/ack-after-echo-no-double-apply-0
async def test_rto20_ack_after_echo_no_double_apply():
    client, channel, root, mock_ws = await setup_synced_channel_no_ack('test')

    task = asyncio.ensure_future(root.get('score').as_live_counter().increment(10))

    # The OBJECT must be pending on the connection before its ACK can be matched to it
    await _await_sent(mock_ws, ProtocolMessageAction.OBJECT, task)

    # The echo arrives before the ACK
    mock_ws.send_to_client(build_object_message('test', [
        build_counter_inc('counter:score@1000', 10, ack_serial(0, 0), SITE_CODE),
    ]))
    mock_ws.send_to_client(build_ack_message(0, [ack_serial(0, 0)]))

    await asyncio.wait_for(task, OPERATION_TIMEOUT)

    assert _score(root) == 110


# UTS: objects/unit/RTO5c9-RTO20/ack-serials-cleared-on-resync-0
async def test_rto5c9_rto20_ack_serials_cleared_on_resync():
    client, channel, root, mock_ws = await setup_synced_channel('test')

    await root.get('score').as_live_counter().increment(10)
    assert _score(root) == 110

    # A re-sync replaces the data and clears appliedOnAckSerials (RTO5c9)
    mock_ws.send_to_client(objects_attached_message('test', 'sync2:cursor'))
    mock_ws.send_to_client(build_object_sync_message('test', 'sync2:', STANDARD_POOL_OBJECTS))
    await poll_until(lambda: _score(root) == 100, description='the re-sync to replace the score')
    assert _score(root) == 100

    # The serial the increment was applied with on ACK applies normally once the set is cleared;
    # were it still recorded, the dedup (RTO9a3) would discard it and the score would stay 100
    mock_ws.send_to_client(build_object_message('test', [
        build_counter_inc('counter:score@1000', 10, ack_serial(0, 0), SITE_CODE),
    ]))
    await poll_until(lambda: _score(root) == 110, description='the replayed increment to apply')

    assert _score(root) == 110


# UTS: objects/unit/RTO20/subscription-fires-on-ack-apply-0
async def test_rto20_subscription_fires_on_ack_apply():
    client, channel, root, mock_ws = await setup_synced_channel('test')
    events = []
    root.get('score').subscribe(events.append)

    await root.get('score').as_live_counter().increment(10)

    assert len(events) >= 1
    assert _score(root) == 110


# UTS: objects/unit/RTO23/get-implicit-attach-0
async def test_rto23_get_implicit_attach():
    mock_ws = standard_mock_websocket()
    client = objects_client(mock_ws)
    channel = client.channels.get('test', objects_channel_options())

    assert channel.state == ChannelState.INITIALIZED
    root = await asyncio.wait_for(channel.object.get(), OPERATION_TIMEOUT)

    assert isinstance(root, PathObject)
    assert root._path == []
    assert channel.state == ChannelState.ATTACHED


# UTS: objects/unit/RTO23d/get-resolves-immediately-synced-0
async def test_rto23d_get_resolves_immediately_synced():
    client, channel, root, mock_ws = await setup_synced_channel('test')

    root2 = await asyncio.wait_for(channel.object.get(), OPERATION_TIMEOUT)

    assert isinstance(root2, PathObject)
    assert root2._path == []


# UTS: objects/unit/RTO10b1/gc-grace-period-source-0
async def test_rto10b1_gc_grace_period_source():
    clock = FakeClock()
    mock_ws = standard_mock_websocket(connected=objects_connected_message(objects_gc_grace_period=5000))
    client = objects_client(mock_ws, clock=clock)
    channel = client.channels.get('test', objects_channel_options())
    # UTS SPEC ERROR: the specification advances 6000 ms, which RTO10a's example interval of
    # five minutes never sweeps within, so as written no GC check runs at all. The interval is
    # shortened before the first ATTACHED schedules the GC timer, so that sweeps fall inside it.
    channel.object._gc_interval_ms = 1000
    root = await channel.object.get()
    pool = channel.object._objects_pool

    assert channel.object._gc_grace_period_ms == 5000

    # A tombstone stamped now: eligible after 6000 ms under the 5000 ms grace period from
    # ConnectionDetails, but not under the 24 hour default
    mock_ws.send_to_client(build_object_message('test', [
        build_object_delete('counter:score@1000', '99', 'site1', clock.now_ms()),
    ]))
    await poll_until(lambda: pool['counter:score@1000'].is_tombstone,
                     description='the OBJECT_DELETE to tombstone the score counter')

    # The advance is taken in two steps so that the object is seen to survive the sweeps that
    # fall inside the grace period (RTO10c1b)
    await clock.advance(4000)
    assert 'counter:score@1000' in pool

    await clock.advance(2000)

    assert _score(root) is None
    # UTS SPEC ERROR: as in RTO10, `score` reads null from the moment the counter is
    # tombstoned; the collection is observed as the counter leaving the pool
    assert 'counter:score@1000' not in pool


# UTS: objects/unit/RTO17-RTO18/sync-event-sequences-0
@pytest.mark.parametrize('scenario', [
    'initial attach',
    're-sync on new ATTACHED',
    'ATTACHED without HAS_OBJECTS',
])
async def test_rto17_rto18_sync_event_sequences(scenario):
    if scenario == 'initial attach':
        # A first attach is only observable on a channel that has not attached, with the
        # listeners registered before attach() is called
        mock_ws = standard_mock_websocket()
        client = objects_client(mock_ws)
        channel = client.channels.get('test', objects_channel_options())
    else:
        client, channel, root, mock_ws = await setup_synced_channel('test')

    events = []
    channel.object.on(ObjectsEvent.SYNCING, lambda: events.append('SYNCING'))
    channel.object.on(ObjectsEvent.SYNCED, lambda: events.append('SYNCED'))

    if scenario == 'initial attach':
        await channel.attach()
    elif scenario == 're-sync on new ATTACHED':
        mock_ws.send_to_client(objects_attached_message('test', 'sync3:cursor'))
        mock_ws.send_to_client(build_object_sync_message('test', 'sync3:', STANDARD_POOL_OBJECTS))
    else:
        # RTO4c moves the sync state to SYNCING on any ATTACHED, and with no HAS_OBJECTS the
        # sync completes at once (RTO4b4), moving it to SYNCED
        mock_ws.send_to_client(objects_attached_message('test', 'sync4:', flags=0))

    expected_events = ['SYNCING', 'SYNCED']
    await poll_until(lambda: len(events) >= len(expected_events), description=f'the {scenario} events')
    await settle()

    assert events == expected_events


# UTS: objects/unit/RTO27/channel-state-data-lifecycle-0
@pytest.mark.parametrize('state', [ChannelState.DETACHED, ChannelState.FAILED, ChannelState.SUSPENDED],
                         ids=['RTO27a-detached', 'RTO27a-failed', 'RTO27b-suspended'])
async def test_rto27_channel_state_data_lifecycle(state):
    client, channel, root, mock_ws = await setup_synced_channel('test')
    pool = channel.object._objects_pool

    # The standard pool has been materialised: the root map, a counter and a nested map
    assert 'name' in pool['root'].data
    assert pool['counter:score@1000'].value() == 100
    assert 'email' in pool['map:profile@1000'].data

    updates = []
    pool['root'].subscribe(updates.append)
    pool['counter:score@1000'].subscribe(updates.append)
    pool['map:profile@1000'].subscribe(updates.append)

    # The mock cannot drive every state, so the channel-state handler is called directly
    channel.object._act_on_channel_state(state)

    if state == ChannelState.SUSPENDED:
        # RTO27b: the data is retained unchanged
        assert 'name' in pool['root'].data
        assert pool['counter:score@1000'].value() == 100
        assert 'email' in pool['map:profile@1000'].data
    else:
        # RTO27a1: every object's data is cleared, the nested map's checked through the pool
        # rather than through the root, while the objects themselves stay in the pool
        assert pool['root'].data == {}
        assert 'counter:score@1000' in pool
        assert pool['counter:score@1000'].value() == 0
        assert 'map:profile@1000' in pool
        assert pool['map:profile@1000'].data == {}

        # RTO27a1: and no update is emitted for the clear
        await settle()
        assert updates == []
