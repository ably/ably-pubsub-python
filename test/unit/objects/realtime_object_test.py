"""A channel's `RealtimeObject`: waits for SYNCED the channel can no longer satisfy, object
messages that fail to decode or to apply, and the lifetime of the GC timer.

Spec points: RTL33b1, RTO5, RTO5c, RTO8, RTO9, RTO10, RTO10c, RTO18, RTO19, RTO20e1, RTO23c1,
RTO27a. No UTS specification covers these cases, so they are written against the features
specification.

Several cases race a channel state change against a coroutine resuming. The mock websocket
answers one client message with two frames, which the transport handles one after the other
before the coroutine awaiting the first of them resumes, as when the server's frames arrive in
one read.
"""

import asyncio
import logging

import pytest

from ably.pubsub.objects.defaults import GC_INTERVAL_MS
from ably.pubsub.objects.enums import ObjectsSyncState
from ably.pubsub.objects.realtimeobject import RealtimeObject
from ably.pubsub.realtime.connection import ConnectionState
from ably.pubsub.types.channelstate import ChannelState
from ably.pubsub.util.exceptions import AblyException
from test.uts.helpers.client import await_connection_state, poll_until
from test.uts.helpers.clock import FakeClock, settle
from test.uts.helpers.mock_websocket import MockWebSocket, channel_error_message
from test.uts.objects.helpers.standard_test_pool import (
    ATTACH,
    HAS_OBJECTS,
    LWW,
    STANDARD_POOL_OBJECTS,
    build_ack_message,
    build_counter_inc,
    build_map_set,
    build_object_message,
    build_object_state,
    objects_attached_message,
    objects_channel_options,
    objects_client,
    objects_connected_message,
    remote_serial,
    setup_synced_channel,
    standard_mock_websocket,
)

# How long a test waits on an operation it expects to complete or fail, so that one which
# never settles fails with a timeout rather than running into the suite's own
OPERATION_TIMEOUT = 5

SCORE = 'counter:score@1000'


def _score(channel):
    return channel.object._objects_pool[SCORE].data


def _assert_sync_wait_failure(excinfo, state_text, cause_code=None):
    """Asserts an RTO23c1/RTO20e1 failure: 92008, status 400, naming why, with the channel's error."""
    assert excinfo.value.code == 92008
    assert excinfo.value.status_code == 400
    assert state_text in excinfo.value.message
    if cause_code is not None:
        assert excinfo.value.cause.code == cause_code


async def _restart_sync(channel, mock_ws):
    """Sends an ATTACHED while attached, which restarts the sync (RTO4) with no OBJECT_SYNC to follow."""
    mock_ws.send_to_client(objects_attached_message('test', 'sync2:cursor', HAS_OBJECTS))
    await poll_until(lambda: channel.object._sync_state == ObjectsSyncState.SYNCING,
                     description='the sync to restart')


def _ack_then_channel_error(mock_ws_ref):
    """An `on_object` handler answering each OBJECT with its ACK and, in the same read, a channel ERROR."""
    def on_object(message):
        mock_ws_ref[0].send_to_client(build_ack_message(message['msgSerial'], ['t:9:0']))
        mock_ws_ref[0].send_to_client(channel_error_message('test', 90000, 'Channel error', 400))
    return on_object


# --- B1: a wait for SYNCED on a channel that has already left ATTACHED ----------------------

async def test_rto23c1_get_fails_when_the_channel_fails_with_its_attached():
    """RTO23c1: an ATTACHED and a channel ERROR read together leave the channel FAILED before
    `get()` resumes from its attach, so `get()` begins its wait on a channel that will never
    sync. It fails at once with 92008, the channel's error as the cause, rather than waiting
    for a transition that has already happened."""
    mock_ws = None

    def on_message_from_client(message):
        if message.get('action') == ATTACH:
            channel_name = message.get('channel')
            mock_ws.send_to_client(objects_attached_message(channel_name, 'sync1:cursor', HAS_OBJECTS))
            mock_ws.send_to_client(channel_error_message(channel_name, 90000, 'Channel error', 400))

    mock_ws = MockWebSocket(
        on_connection_attempt=lambda conn: conn.respond_with_success(objects_connected_message()),
        on_message_from_client=on_message_from_client,
    )
    client = objects_client(mock_ws)
    channel = client.channels.get('test', objects_channel_options())

    with pytest.raises(AblyException) as excinfo:
        await asyncio.wait_for(channel.object.get(), OPERATION_TIMEOUT)

    _assert_sync_wait_failure(excinfo, 'failed', cause_code=90000)
    assert channel.state == ChannelState.FAILED
    assert channel.object._sync_waiters == {}


async def test_rto20e1_publish_and_apply_fails_when_the_channel_fails_with_the_ack():
    """RTO20e1: an ACK and a channel ERROR read together leave the channel FAILED before the
    write resumes, so its wait for SYNCED begins on a channel that will never sync. It fails at
    once with 92008, the channel's error as the cause."""
    mock_ws_ref = []
    mock_ws = standard_mock_websocket(auto_ack=False, on_object=_ack_then_channel_error(mock_ws_ref))
    mock_ws_ref.append(mock_ws)
    client, channel, root, mock_ws = await setup_synced_channel('test', mock_ws=mock_ws)
    await _restart_sync(channel, mock_ws)

    with pytest.raises(AblyException) as excinfo:
        await asyncio.wait_for(root.set('name', 'Bob'), OPERATION_TIMEOUT)

    _assert_sync_wait_failure(excinfo, 'failed', cause_code=90000)
    assert channel.state == ChannelState.FAILED
    assert channel.object._sync_waiters == {}


async def test_rto20e1_publish_and_apply_fails_when_the_channel_detached_before_the_ack():
    """RTO20e1: a write whose channel detaches while its publish awaits the ACK begins its wait
    for SYNCED on a DETACHED channel, and fails at once with 92008."""
    published = []
    mock_ws = standard_mock_websocket(auto_ack=False, on_object=published.append)
    client, channel, root, mock_ws = await setup_synced_channel('test', mock_ws=mock_ws)
    await _restart_sync(channel, mock_ws)

    task = asyncio.ensure_future(root.get('score').as_live_counter().increment(10))
    await poll_until(lambda: len(published) == 1, description='the OBJECT to be published')
    await channel.detach()
    mock_ws.send_to_client(build_ack_message(published[0]['msgSerial'], ['t:9:0']))

    with pytest.raises(AblyException) as excinfo:
        await asyncio.wait_for(task, OPERATION_TIMEOUT)

    _assert_sync_wait_failure(excinfo, 'detached')
    assert channel.object._sync_waiters == {}


async def test_rto27a_publish_and_apply_does_not_apply_once_the_channel_has_failed():
    """RTO27a, RTO20f: a write on a SYNCED channel whose ACK is read together with a channel
    ERROR completes, as it was published, but is not applied locally: the channel's FAILED
    has cleared the objects' data, and applying it would rebuild that data and notify
    subscribers on a failed channel."""
    mock_ws_ref = []
    mock_ws = standard_mock_websocket(auto_ack=False, on_object=_ack_then_channel_error(mock_ws_ref))
    mock_ws_ref.append(mock_ws)
    client, channel, root, mock_ws = await setup_synced_channel('test', mock_ws=mock_ws)
    calls = []
    root.get('score').subscribe(calls.append)

    await asyncio.wait_for(root.get('score').as_live_counter().increment(10), OPERATION_TIMEOUT)
    await settle()

    assert channel.state == ChannelState.FAILED
    assert _score(channel) == 0
    assert calls == []


async def test_rtl33b1_get_fails_when_the_client_closes_during_the_attach():
    """RTL33b1, RTO23e: closing the client while `get()` attaches moves the ATTACHING channel to
    DETACHED, which ends the attach without attaching. `get()` fails with the attach's error,
    rather than waiting for a sync on a channel that has detached."""
    mock_ws = MockWebSocket(
        on_connection_attempt=lambda conn: conn.respond_with_success(objects_connected_message()),
        on_message_from_client=lambda message: None,  # never answers the ATTACH
    )
    client = objects_client(mock_ws)
    channel = client.channels.get('test', objects_channel_options())
    await await_connection_state(client, ConnectionState.CONNECTED)

    task = asyncio.ensure_future(channel.object.get())
    await poll_until(lambda: channel.state == ChannelState.ATTACHING, description='the channel to attach')
    await client.close()

    with pytest.raises(AblyException) as excinfo:
        await asyncio.wait_for(task, OPERATION_TIMEOUT)

    assert excinfo.value.code == 90001
    assert excinfo.value.status_code == 400
    assert channel.state == ChannelState.DETACHED
    assert channel.object._sync_waiters == {}


# --- R1: object messages that fail to decode or to apply ------------------------------------

async def test_rto5_an_object_sync_message_that_fails_to_decode_is_skipped(caplog):
    """RTO5, RTO5a4: one undecodable value in the last OBJECT_SYNC of a sequence costs only the
    ObjectMessage carrying it. The rest of the ProtocolMessage, its cursor included, is
    handled, so the sync completes and `get()` returns."""
    bad = build_object_state('map:bad@1000', {'aaa': 't:0'}, map={
        'semantics': LWW, 'entries': {'k': {'data': {'json': '{not json'}, 'timeserial': 't:0'}}})
    mock_ws = standard_mock_websocket(sync_objects=(*STANDARD_POOL_OBJECTS, bad))

    with caplog.at_level(logging.ERROR, logger='ably.pubsub.objects'):
        client, channel, root, mock_ws = await asyncio.wait_for(
            setup_synced_channel('test', mock_ws=mock_ws), OPERATION_TIMEOUT)

    assert channel.object._sync_state == ObjectsSyncState.SYNCED
    assert root.get('score').as_live_counter().value() == 100
    assert 'map:bad@1000' not in channel.object._objects_pool
    assert any('failed to decode' in record.getMessage() for record in caplog.records)


async def test_rto8_an_object_message_that_fails_to_decode_costs_only_itself(caplog):
    """RTO8: an OBJECT carrying an undecodable value and a valid operation applies the valid
    one."""
    client, channel, root, mock_ws = await setup_synced_channel('test')

    with caplog.at_level(logging.ERROR, logger='ably.pubsub.objects'):
        mock_ws.send_to_client(build_object_message('test', [
            build_map_set('root', 'data', {'json': '{not json'}, remote_serial(0), 'remote'),
            build_counter_inc(SCORE, 1, remote_serial(1), 'remote'),
        ]))
        await poll_until(lambda: _score(channel) == 101, description='the valid increment to apply')

    assert root.get('data').as_primitive().value() == {'tags': ['a', 'b']}
    assert any('failed to decode' in record.getMessage() for record in caplog.records)


async def test_rto9_an_object_message_that_fails_to_apply_costs_only_itself(caplog):
    """RTO9: an operation that decodes but raises as it is applied, here an increment by a
    string, is logged and skipped, and the operations after it in the OBJECT still apply."""
    client, channel, root, mock_ws = await setup_synced_channel('test')

    with caplog.at_level(logging.ERROR, logger='ably.pubsub.objects'):
        mock_ws.send_to_client(build_object_message('test', [
            build_counter_inc(SCORE, 'one', remote_serial(0), 'remote'),
            build_map_set('root', 'name', {'string': 'Bob'}, remote_serial(1), 'remote'),
        ]))
        await poll_until(lambda: root.get('name').as_primitive().value() == 'Bob',
                         description='the MAP_SET after the failing increment to apply')

    assert _score(channel) == 100
    assert any('could not be applied' in record.getMessage() for record in caplog.records)


async def test_rto5c_an_object_state_that_fails_to_apply_does_not_stall_the_sync(caplog):
    """RTO5c: an object state that decodes but raises as it is applied, here a counter whose
    count is a string, is logged and skipped, and the sync still completes."""
    bad = build_object_state('counter:bad@1000', {'aaa': 't:0'}, counter={'count': 'many'})
    mock_ws = standard_mock_websocket(sync_objects=(*STANDARD_POOL_OBJECTS, bad))

    with caplog.at_level(logging.ERROR, logger='ably.pubsub.objects'):
        client, channel, root, mock_ws = await asyncio.wait_for(
            setup_synced_channel('test', mock_ws=mock_ws), OPERATION_TIMEOUT)

    assert channel.object._sync_state == ObjectsSyncState.SYNCED
    assert root.get('score').as_live_counter().value() == 100
    assert any('could not be applied' in record.getMessage() for record in caplog.records)


# --- R2: the GC timer and waits of a released channel ---------------------------------------

async def test_rto10_a_released_channel_stops_its_gc_timer():
    """RTO10a: the GC timer every ATTACHED schedules stops when its channel is released. A
    released channel is out of the client's collection, so closing the client never detaches
    it; the release itself stops the timer, for good."""
    clock = FakeClock()
    client, channel, root, mock_ws = await setup_synced_channel('test', clock=clock)
    timer = channel.object._gc_timer
    assert timer is not None

    client.channels.release('test')
    await client.close()
    await clock.advance(GC_INTERVAL_MS)

    assert timer.cancelled
    assert channel.object._gc_timer is None


async def test_rto23c1_a_wait_for_synced_fails_when_its_channel_is_released():
    """RTO23c1: a released channel receives nothing more, so it can never sync. A `get()`
    waiting for SYNCED when the channel is released fails with 92008, and so does a later one,
    at once."""
    client, channel, root, mock_ws = await setup_synced_channel('test')
    await _restart_sync(channel, mock_ws)
    task = asyncio.ensure_future(channel.object.get())
    await settle()
    assert not task.done()

    client.channels.release('test')

    with pytest.raises(AblyException) as excinfo:
        await asyncio.wait_for(task, OPERATION_TIMEOUT)
    _assert_sync_wait_failure(excinfo, 'released')

    with pytest.raises(AblyException) as excinfo:
        await asyncio.wait_for(channel.object.get(), OPERATION_TIMEOUT)
    _assert_sync_wait_failure(excinfo, 'released')


# --- R4: a GC sweep that raises -------------------------------------------------------------

async def test_rto10c_a_gc_sweep_that_raises_is_logged_and_the_next_still_runs(caplog, monkeypatch):
    """RTO10c: a sweep that raises is logged, and the next is scheduled all the same; the error
    does not escape the timer's callback."""
    clock = FakeClock()
    client, channel, root, mock_ws = await setup_synced_channel('test', clock=clock)
    sweeps = []

    def collect_garbage(grace_period_ms, now_ms):
        sweeps.append(now_ms)
        if len(sweeps) == 1:
            raise RuntimeError('the sweep failed')

    monkeypatch.setattr(channel.object._objects_pool, 'collect_garbage', collect_garbage)

    with caplog.at_level(logging.ERROR, logger='ably.pubsub.objects'):
        await clock.advance(GC_INTERVAL_MS)
    assert len(sweeps) == 1
    assert any('GC sweep raised' in record.getMessage() for record in caplog.records)
    assert channel.object._gc_timer is not None

    await clock.advance(GC_INTERVAL_MS)
    assert len(sweeps) == 2


# --- on and off --------------------------------------------------------------------------

@pytest.mark.parametrize('register', [
    lambda realtime_object: realtime_object.on('synched', lambda: None),
    lambda realtime_object: realtime_object.off('synched', lambda: None),
])
def test_rto18_rto19_an_unknown_event_raises_40003(register):
    """RTO18, RTO19: `on` and `off` take an `ObjectsEvent`; any other event is an invalid
    argument, raised as AblyException 40003 like the other argument errors."""
    with pytest.raises(AblyException) as excinfo:
        register(RealtimeObject())

    assert excinfo.value.code == 40003
    assert excinfo.value.status_code == 400
