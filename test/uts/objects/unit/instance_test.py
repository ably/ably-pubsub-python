"""Derived from uts/objects/unit/instance.md in ably/specification.

Spec points: RTINS3, RTINS4, RTINS5, RTINS6, RTINS9, RTINS10, RTINS12, RTINS13, RTINS14,
RTINS15, RTINS16, RTTS8a, RTTS9d, RTTS10

The specification is written against the untyped `Instance`, one class carrying every
method. ably-python partitions it per RTTS7-RTTS10: `id` and `type` are properties, `get`,
`compact` and the three view helpers are on the base `Instance`, and a type-specific method
is reached through the checked view helper for the wrapped type, so `inst.value()` on a
counter is `inst.as_live_counter().value()` and `inst.set(k, v)` on a map is
`await inst.as_live_map().set(k, v)`. A view helper asked for a type the instance does not
wrap raises AblyException 92007 (RTTS9d).

That makes three of the specification's reads unreachable: `value()` on a map instance
(RTINS4d), `size()` on a counter instance (RTINS9c) and `subscribe` on a primitive instance
(RTINS16c), since the typed instance for those types has no such method and the views
that do have it refuse the wrapped type. Those tests assert the wrapped `type`, the
absence of the method, and the 92007 the view helpers raise in its place (S-5).

`setup_synced_channel` uses the standard mock, which ACKs every OBJECT the client sends,
so each write is awaited to completion and is applied locally by the time it returns
(RTO20).
"""

import pytest

from ably.pubsub.objects import publicmessage
from ably.pubsub.objects.enums import ValueType
from ably.pubsub.objects.instance import Instance, InstanceSubscriptionEvent, PrimitiveInstance
from ably.pubsub.objects.objectmessage import ObjectOperationAction
from ably.pubsub.objects.subscription import Subscription
from ably.pubsub.types.channelstate import ChannelState
from ably.pubsub.util.exceptions import AblyException
from test.uts.helpers.client import poll_until
from test.uts.helpers.clock import settle
from test.uts.objects.helpers.standard_test_pool import (
    assert_unchanged_after_quiescence,
    build_counter_inc,
    build_map_set,
    build_object_message,
    build_public_object_message,
    remote_serial,
    setup_synced_channel,
)


def assert_view_refused(view_helper):
    """Asserts that calling an `Instance` view helper fails fast with 92007 (RTTS9d)."""
    with pytest.raises(AblyException) as excinfo:
        view_helper()
    assert excinfo.value.code == 92007
    assert excinfo.value.status_code == 400


# UTS: objects/unit/RTINS3/id-returns-objectid-0
async def test_rtins3_id_returns_objectid():
    client, channel, root, mock_ws = await setup_synced_channel('test')

    counter_inst = root.get('score').instance()
    assert counter_inst.id == 'counter:score@1000'

    map_inst = root.get('profile').instance()
    assert map_inst.id == 'map:profile@1000'


# UTS: objects/unit/RTINS4/value-counter-0
async def test_rtins4_value_counter():
    client, channel, root, mock_ws = await setup_synced_channel('test')

    counter_inst = root.get('score').instance()
    assert counter_inst.as_live_counter().value() == 100

    map_inst = root.instance()
    # S-5: the specification asserts `map_inst.value() == null` (RTINS4d). A map instance has
    # no `value()` (RTTS10a), and the two views that do have one refuse a map (RTTS9d)
    assert map_inst.type is ValueType.LIVE_MAP
    assert not hasattr(map_inst, 'value')
    assert_view_refused(map_inst.as_primitive)
    assert_view_refused(map_inst.as_live_counter)


# UTS: objects/unit/RTINS5/get-wraps-entry-0
async def test_rtins5_get_wraps_entry():
    client, channel, root, mock_ws = await setup_synced_channel('test')
    root_inst = root.instance()

    name_inst = root_inst.get('name')
    assert isinstance(name_inst, Instance)
    assert name_inst.as_primitive().value() == 'Alice'

    score_inst = root_inst.get('score')
    assert score_inst.id == 'counter:score@1000'

    null_inst = root_inst.get('nonexistent')
    assert null_inst is None


# UTS: objects/unit/RTINS6/entries-yields-instances-0
async def test_rtins6_entries_yields_instances():
    client, channel, root, mock_ws = await setup_synced_channel('test')
    root_inst = root.instance()

    entries = {}
    for key, inst in root_inst.as_live_map().entries():
        entries[key] = inst

    assert len(entries) == 7
    assert isinstance(entries['name'], Instance)
    assert entries['name'].as_primitive().value() == 'Alice'


# UTS: objects/unit/RTINS9/size-0
async def test_rtins9_size():
    client, channel, root, mock_ws = await setup_synced_channel('test')

    root_inst = root.instance()
    assert root_inst.as_live_map().size() == 7

    counter_inst = root.get('score').instance()
    # S-5: the specification asserts `counter_inst.size() == null` (RTINS9c). A counter
    # instance has no `size()` (RTTS10b), and the map view that has one refuses a counter
    # (RTTS9d)
    assert counter_inst.type is ValueType.LIVE_COUNTER
    assert not hasattr(counter_inst, 'size')
    assert_view_refused(counter_inst.as_live_map)


# UTS: objects/unit/RTINS10/compact-0
async def test_rtins10_compact():
    client, channel, root, mock_ws = await setup_synced_channel('test')
    root_inst = root.instance()

    result = root_inst.compact()

    assert result['name'] == 'Alice'
    assert result['score'] == 100
    assert result['profile']['email'] == 'alice@example.com'


# UTS: objects/unit/RTINS12/set-delegates-0
async def test_rtins12_set_delegates():
    client, channel, root, mock_ws = await setup_synced_channel('test')
    root_inst = root.instance()

    await root_inst.as_live_map().set('name', 'Bob')

    assert root.get('name').as_primitive().value() == 'Bob'


# UTS: objects/unit/RTINS12d/set-non-map-throws-0
async def test_rtins12d_set_non_map_throws():
    client, channel, root, mock_ws = await setup_synced_channel('test')
    counter_inst = root.get('score').instance()

    # `set` is reached through the map view, which refuses a counter with the 92007 and
    # status 400 that RTINS12d requires of `set` (RTTS9d)
    with pytest.raises(AblyException) as excinfo:
        await counter_inst.as_live_map().set('key', 'value')

    assert excinfo.value.code == 92007
    assert excinfo.value.status_code == 400


# UTS: objects/unit/RTINS13/remove-delegates-0
async def test_rtins13_remove_delegates():
    client, channel, root, mock_ws = await setup_synced_channel('test')
    root_inst = root.instance()
    assert root.get('name').as_primitive().value() == 'Alice'

    await root_inst.as_live_map().remove('name')

    assert root.get('name').as_primitive().value() is None


# UTS: objects/unit/RTINS14/increment-delegates-0
async def test_rtins14_increment_delegates():
    client, channel, root, mock_ws = await setup_synced_channel('test')
    counter_inst = root.get('score').instance()

    await counter_inst.as_live_counter().increment(25)

    assert root.get('score').as_live_counter().value() == 125


# UTS: objects/unit/RTINS14d/increment-non-counter-throws-0
async def test_rtins14d_increment_non_counter_throws():
    client, channel, root, mock_ws = await setup_synced_channel('test')
    map_inst = root.instance()

    # `increment` is reached through the counter view, which refuses a map with the 92007
    # and status 400 that RTINS14d requires of `increment` (RTTS9d)
    with pytest.raises(AblyException) as excinfo:
        await map_inst.as_live_counter().increment(5)

    assert excinfo.value.code == 92007
    assert excinfo.value.status_code == 400


# UTS: objects/unit/RTINS15/decrement-delegates-0
async def test_rtins15_decrement_delegates():
    client, channel, root, mock_ws = await setup_synced_channel('test')
    counter_inst = root.get('score').instance()

    await counter_inst.as_live_counter().decrement(10)

    assert root.get('score').as_live_counter().value() == 90


# UTS: objects/unit/RTINS14a/increment-default-0
async def test_rtins14a_increment_default():
    client, channel, root, mock_ws = await setup_synced_channel('test')
    counter_inst = root.get('score').instance()

    await counter_inst.as_live_counter().increment()

    assert root.get('score').as_live_counter().value() == 101


# UTS: objects/unit/RTINS15a/decrement-default-0
async def test_rtins15a_decrement_default():
    client, channel, root, mock_ws = await setup_synced_channel('test')
    counter_inst = root.get('score').instance()

    await counter_inst.as_live_counter().decrement()

    assert root.get('score').as_live_counter().value() == 99


# UTS: objects/unit/RTINS16/subscribe-receives-events-0
async def test_rtins16_subscribe_receives_events():
    client, channel, root, mock_ws = await setup_synced_channel('test')
    counter_inst = root.get('score').instance()
    events = []
    sub = counter_inst.as_live_counter().subscribe(events.append)

    mock_ws.send_to_client(build_object_message('test', [
        build_counter_inc('counter:score@1000', 7, '99', 'remote'),
    ]))
    await poll_until(lambda: len(events) >= 1, timeout=5, description='the listener to receive the COUNTER_INC')
    await settle()

    assert isinstance(sub, Subscription)
    assert len(events) == 1
    assert isinstance(events[0], InstanceSubscriptionEvent)
    assert isinstance(events[0].object, Instance)
    assert events[0].object.id == 'counter:score@1000'


# UTS: objects/unit/RTINS16c/subscribe-primitive-throws-0
async def test_rtins16c_subscribe_primitive_throws():
    client, channel, root, mock_ws = await setup_synced_channel('test')

    name_inst = root.instance().get('name')

    # S-5: the specification calls `name_inst.subscribe(...)` and expects 92007 (RTINS16c).
    # A primitive instance has no `subscribe` (RTTS7b, RTTS10c), and the two views that do
    # have one refuse a primitive with 92007 (RTTS9d)
    assert isinstance(name_inst, PrimitiveInstance)
    assert name_inst.type is ValueType.STRING
    assert not hasattr(name_inst, 'subscribe')
    assert_view_refused(name_inst.as_live_map)
    assert_view_refused(name_inst.as_live_counter)


# UTS: objects/unit/RTINS16e2/subscription-event-message-0
async def test_rtins16e2_subscription_event_message():
    client, channel, root, mock_ws = await setup_synced_channel('test')
    root_inst = root.instance()
    events = []
    root_inst.as_live_map().subscribe(events.append)

    map_set = build_map_set('root', 'name', {'string': 'Bob'}, remote_serial(0), 'remote')
    mock_ws.send_to_client(build_object_message('test', [map_set]))
    await poll_until(lambda: len(events) >= 1, timeout=5, description='the listener to receive the MAP_SET')

    assert isinstance(events[0].object, Instance)
    assert events[0].object.id == 'root'
    assert events[0].message is not None
    assert isinstance(events[0].message, publicmessage.ObjectMessage)
    assert events[0].message.channel == 'test'
    assert events[0].message.operation.action == ObjectOperationAction.MAP_SET
    assert events[0].message.operation.object_id == 'root'
    assert events[0].message.operation.map_set.key == 'name'
    # The whole message is the one PAOM3 derives from the MAP_SET as it arrived
    assert events[0].message == build_public_object_message(map_set, 'test')


# UTS: objects/unit/RTINS16f/subscribe-returns-subscription-0
async def test_rtins16f_subscribe_returns_subscription():
    client, channel, root, mock_ws = await setup_synced_channel('test')
    counter_inst = root.get('score').instance()
    events = []
    sub = counter_inst.as_live_counter().subscribe(events.append)
    sub.unsubscribe()

    # Quiescence control: a listener still subscribed to the same counter, which the
    # same dispatch reaches
    control_events = []
    counter_inst.as_live_counter().subscribe(control_events.append)

    mock_ws.send_to_client(build_object_message('test', [
        build_counter_inc('counter:score@1000', 7, '99', 'remote'),
    ]))

    await assert_unchanged_after_quiescence(
        lambda: len(events), lambda: len(control_events) >= 1,
        description='the control listener receives the COUNTER_INC')
    assert len(events) == 0


# UTS: objects/unit/RTINS16g/subscription-follows-identity-0
async def test_rtins16g_subscription_follows_identity():
    client, channel, root, mock_ws = await setup_synced_channel('test')
    counter_inst = root.get('score').instance()
    events = []
    counter_inst.as_live_counter().subscribe(events.append)

    mock_ws.send_to_client(build_object_message('test', [
        build_map_set('root', 'score', {'objectId': 'counter:new@2000'}, remote_serial(0), 'remote'),
    ]))

    mock_ws.send_to_client(build_object_message('test', [
        build_counter_inc('counter:score@1000', 10, '100', 'remote'),
    ]))
    await poll_until(lambda: len(events) >= 1, timeout=5, description='the listener to receive the COUNTER_INC')

    assert len(events) >= 1
    # RTINS16e1: the delivered event carries the Instance wrapping the object that fired,
    # so the assertion reads the event rather than the `counter_inst` handle
    assert isinstance(events[0].object, Instance)
    assert events[0].object.id == 'counter:score@1000'
    # The frames are processed in order, so `score` already pointed at the new counter
    # when the original one was incremented, and the event is that increment
    assert root.get('score').instance().id == 'counter:new@2000'
    assert events[0].message.operation.counter_inc.number == 10
    assert events[0].object.as_live_counter().value() == 110


# UTS: objects/unit/RTINS16h/subscribe-no-side-effects-0
async def test_rtins16h_subscribe_no_side_effects():
    client, channel, root, mock_ws = await setup_synced_channel('test')
    counter_inst = root.get('score').instance()
    channel_state_before = channel.state
    sent_before = len(mock_ws.messages_from_client)
    assert channel_state_before == ChannelState.ATTACHED

    sub = counter_inst.as_live_counter().subscribe(lambda event: None)
    await settle()

    assert isinstance(sub, Subscription)
    assert channel.state == channel_state_before
    # Nothing was sent to the server either, such as an attach or a detach
    assert len(mock_ws.messages_from_client) == sent_before
