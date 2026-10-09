"""Derived from uts/objects/unit/live_object_subscribe.md in ably/specification.

Spec points: RTLO4b, RTLO4b3, RTLO4b4c1, RTLO4b4c3a, RTLO4b4c3c, RTLO4b4d, RTLO4b4e,
RTLO4b6, RTLO4b7, RTINS16e, RTLC14c

`LiveObject#subscribe` is exercised through `Instance#subscribe` (RTINS16), as the
specification does. ably-python partitions `Instance` by type (RTTS) and only the live
object views have `subscribe`, so a counter's instance is subscribed through
`as_live_counter()` and the root map's through `as_live_map()`. Each listener receives an
`InstanceSubscriptionEvent`, whose `message` is the public `ObjectMessage`.

Inbound frames are processed on the transport's read task, so a positive is awaited with
`poll_until`, and an exact count or a "listener did not fire" is asserted only once a
control listener on a later dispatch has fired and the loop has settled (the
specification's negative-assertion quiescence pattern).
"""

from ably.pubsub.objects import publicmessage
from ably.pubsub.objects.objectmessage import ObjectOperationAction
from ably.pubsub.objects.subscription import Subscription
from test.uts.helpers.client import poll_until
from test.uts.helpers.clock import settle
from test.uts.objects.helpers.standard_test_pool import (
    assert_unchanged_after_quiescence,
    build_counter_inc,
    build_map_set,
    build_object_delete,
    build_object_message,
    build_public_object_message,
    remote_serial,
    setup_synced_channel,
)


# UTS: objects/unit/RTLO4b/subscribe-receives-updates-0
async def test_rtlo4b_subscribe_receives_updates():
    ctx = await setup_synced_channel('test')
    updates = []
    instance = ctx.root.get('score').instance()
    sub = instance.as_live_counter().subscribe(lambda event: updates.append(event))

    ctx.mock_ws.send_to_client(build_object_message('test', [
        build_counter_inc('counter:score@1000', 7, '99', 'remote'),
    ]))
    await poll_until(lambda: len(updates) >= 1, timeout=5, description='the counter update to be delivered')
    await settle()

    assert isinstance(sub, Subscription)
    assert len(updates) == 1


# UTS: objects/unit/RTLO4b7/subscribe-returns-subscription-0
async def test_rtlo4b7_subscribe_returns_subscription():
    ctx = await setup_synced_channel('test')
    instance = ctx.root.get('score').instance()

    sub = instance.as_live_counter().subscribe(lambda event: None)

    assert isinstance(sub, Subscription)
    assert callable(sub.unsubscribe)


# UTS: objects/unit/RTLO4b7/subscription-unsubscribe-stops-delivery-0
async def test_rtlo4b7_subscription_unsubscribe_stops_delivery():
    ctx = await setup_synced_channel('test')
    updates = []
    control = []
    instance = ctx.root.get('score').instance()
    sub = instance.as_live_counter().subscribe(lambda event: updates.append(event))

    ctx.mock_ws.send_to_client(build_object_message('test', [
        build_counter_inc('counter:score@1000', 5, '01', 'remote'),
    ]))
    await poll_until(lambda: len(updates) >= 1, timeout=5, description='the first update to be delivered')

    sub.unsubscribe()

    # A control listener fires on the same dispatch as the message under test, so once it
    # has fired the unsubscribed listener would also have run had it still been registered
    instance.as_live_counter().subscribe(lambda event: control.append(event))
    ctx.mock_ws.send_to_client(build_object_message('test', [
        build_counter_inc('counter:score@1000', 10, '02', 'remote'),
    ]))
    await assert_unchanged_after_quiescence(lambda: len(updates), lambda: len(control) >= 1,
                                            description='the control listener received the second update')

    assert len(updates) == 1


# UTS: objects/unit/RTLO4b7/subscription-unsubscribe-idempotent-0
async def test_rtlo4b7_subscription_unsubscribe_idempotent():
    ctx = await setup_synced_channel('test')
    instance = ctx.root.get('score').instance()
    sub = instance.as_live_counter().subscribe(lambda event: None)

    # Neither call raises
    sub.unsubscribe()
    sub.unsubscribe()


# UTS: objects/unit/RTLO4b4c1/noop-no-trigger-0
async def test_rtlo4b4c1_noop_no_trigger():
    ctx = await setup_synced_channel('test')
    updates = []
    control = []
    instance = ctx.root.get('score').instance()
    instance.as_live_counter().subscribe(lambda event: updates.append(event))

    ctx.mock_ws.send_to_client(build_object_message('test', [
        build_counter_inc('counter:score@1000', 5, '01', 'remote'),
    ]))
    await poll_until(lambda: len(updates) >= 1, timeout=5, description='the first update to be delivered')

    # Serial "02" passes the newness check (RTLO4a6), and an increment with no `number` is
    # the no-op (RTLC9h). `number: 0` would be present per RTLC9g and give a real update of 0.
    ctx.mock_ws.send_to_client(build_object_message('test', [{
        'serial': '02',
        'siteCode': 'remote',
        'operation': {
            'action': int(ObjectOperationAction.COUNTER_INC),
            'objectId': 'counter:score@1000',
            'counterInc': {},
        },
    }]))
    # The follow-up "03" is dispatched after the no-op, so once its separate control
    # listener fires the no-op has certainly been processed
    control_sub = instance.as_live_counter().subscribe(lambda event: control.append(event))
    ctx.mock_ws.send_to_client(build_object_message('test', [
        build_counter_inc('counter:score@1000', 3, '03', 'remote'),
    ]))
    await poll_until(lambda: len(control) >= 1, timeout=5, description='the control listener to receive "03"')
    await settle()
    control_sub.unsubscribe()

    # The original listener fired for "01" and "03" only; had the no-op fired it would be 3
    assert len(updates) == 2


# UTS: objects/unit/RTLO4b6/subscribe-no-side-effects-0
async def test_rtlo4b6_subscribe_no_side_effects():
    ctx = await setup_synced_channel('test')
    state_before = ctx.channel.state
    sync_state_before = ctx.channel.object._sync_state
    sent_before = len(ctx.mock_ws.messages_from_client)
    instance = ctx.root.get('score').instance()

    instance.as_live_counter().subscribe(lambda event: None)
    await settle()

    assert ctx.channel.state == state_before
    # Nor does it change the objects' sync state or send anything on the channel
    assert ctx.channel.object._sync_state == sync_state_before
    assert len(ctx.mock_ws.messages_from_client) == sent_before


# UTS: objects/unit/RTLO4b/subscribe-map-update-0
async def test_rtlo4b_subscribe_map_update():
    ctx = await setup_synced_channel('test')
    updates = []
    instance = ctx.root.instance()
    instance.as_live_map().subscribe(lambda event: updates.append(event))

    ctx.mock_ws.send_to_client(build_object_message('test', [
        build_map_set('root', 'name', {'string': 'Bob'}, remote_serial(0), 'remote'),
    ]))
    await poll_until(lambda: len(updates) >= 1, timeout=5, description='the map update to be delivered')
    await settle()

    assert len(updates) == 1


# UTS: objects/unit/RTLO4b4c3c/tombstone-deregisters-listeners-0
async def test_rtlo4b4c3c_tombstone_deregisters_listeners():
    ctx = await setup_synced_channel('test')
    updates_a = []
    updates_b = []
    control = []
    instance = ctx.root.get('score').instance()
    instance.as_live_counter().subscribe(lambda event: updates_a.append(event))
    instance.as_live_counter().subscribe(lambda event: updates_b.append(event))

    # An OBJECT_DELETE tombstones the counter
    ctx.mock_ws.send_to_client(build_object_message('test', [
        build_object_delete('counter:score@1000', '50', 'remote'),
    ]))
    # Both listeners are awaited on this dispatch before either count is asserted
    await poll_until(lambda: len(updates_a) >= 1, timeout=5, description='listener A to receive the tombstone')
    await poll_until(lambda: len(updates_b) >= 1, timeout=5, description='listener B to receive the tombstone')
    await settle()

    # Both listeners received the tombstone update
    assert len(updates_a) == 1
    assert updates_a[0].message.operation.action == ObjectOperationAction.OBJECT_DELETE
    assert len(updates_b) == 1
    assert updates_b[0].message.operation.action == ObjectOperationAction.OBJECT_DELETE

    # A tombstoned object ignores further operations (RTLC7e), so no listener on the counter
    # can serve as the control. A listener on another live object can: the "52" MAP_SET on
    # the profile map is processed after the "51" increment, so once it fires "51" has been too.
    control_inst = ctx.root.get('profile').instance()
    control_inst.as_live_map().subscribe(lambda event: control.append(event))
    ctx.mock_ws.send_to_client(build_object_message('test', [
        build_counter_inc('counter:score@1000', 3, '51', 'remote'),
    ]))
    ctx.mock_ws.send_to_client(build_object_message('test', [
        build_map_set('map:profile@1000', 'quiescence_probe', {'string': 'x'}, '52', 'remote'),
    ]))
    await assert_unchanged_after_quiescence(lambda: (len(updates_a), len(updates_b)), lambda: len(control) >= 1,
                                            description='the control listener on the profile map fired')

    # The tombstone deregistered both listeners (RTLO4b4c3c)
    assert len(updates_a) == 1
    assert len(updates_b) == 1


# UTS: objects/unit/RTLO4b4c3c/tombstone-zero-value-counter-tears-down-0
async def test_rtlo4b4c3c_tombstone_zero_value_counter_tears_down():
    ctx = await setup_synced_channel('test')
    updates_a = []
    updates_b = []
    control = []
    instance = ctx.root.get('score').instance()

    # The counter (100 in the standard pool) is driven to 0 before the listeners under test
    # are registered, so they observe only the tombstone
    ctx.mock_ws.send_to_client(build_object_message('test', [
        build_counter_inc('counter:score@1000', -100, '40', 'remote'),
    ]))
    await poll_until(lambda: ctx.root.get('score').as_live_counter().value() == 0, timeout=5,
                     description='the counter to reach 0')

    instance.as_live_counter().subscribe(lambda event: updates_a.append(event))
    instance.as_live_counter().subscribe(lambda event: updates_b.append(event))

    # The OBJECT_DELETE tombstones an already-zero counter: a zero-delta diff, which for a
    # tombstone is not a no-op (RTLC14c)
    ctx.mock_ws.send_to_client(build_object_message('test', [
        build_object_delete('counter:score@1000', '50', 'remote'),
    ]))
    await poll_until(lambda: len(updates_a) >= 1, timeout=5, description='listener A to receive the tombstone')
    await poll_until(lambda: len(updates_b) >= 1, timeout=5, description='listener B to receive the tombstone')
    await settle()

    # Both listeners received the tombstone update although the counter's data did not change
    assert len(updates_a) == 1
    assert updates_a[0].message.operation.action == ObjectOperationAction.OBJECT_DELETE
    assert len(updates_b) == 1
    assert updates_b[0].message.operation.action == ObjectOperationAction.OBJECT_DELETE

    # A separate live object is the quiescence barrier, as in the populated case
    control_inst = ctx.root.get('profile').instance()
    control_inst.as_live_map().subscribe(lambda event: control.append(event))
    ctx.mock_ws.send_to_client(build_object_message('test', [
        build_counter_inc('counter:score@1000', 3, '51', 'remote'),
    ]))
    ctx.mock_ws.send_to_client(build_object_message('test', [
        build_map_set('map:profile@1000', 'quiescence_probe', {'string': 'x'}, '52', 'remote'),
    ]))
    await assert_unchanged_after_quiescence(lambda: (len(updates_a), len(updates_b)), lambda: len(control) >= 1,
                                            description='the control listener on the profile map fired')

    # The tombstone deregistered both listeners (RTLO4b4c3c)
    assert len(updates_a) == 1
    assert len(updates_b) == 1


# UTS: objects/unit/RTLO4b4d/update-has-object-message-0
async def test_rtlo4b4d_update_has_object_message():
    ctx = await setup_synced_channel('test')
    updates = []
    instance = ctx.root.get('score').instance()
    instance.as_live_counter().subscribe(lambda event: updates.append(event))

    counter_inc = build_counter_inc('counter:score@1000', 7, '99', 'remote')
    ctx.mock_ws.send_to_client(build_object_message('test', [counter_inc]))
    await poll_until(lambda: len(updates) >= 1, timeout=5, description='the counter update to be delivered')
    await settle()

    assert len(updates) == 1
    assert updates[0].message is not None
    assert updates[0].message.serial == '99'
    assert updates[0].message.site_code == 'remote'
    assert updates[0].message.operation.action == ObjectOperationAction.COUNTER_INC
    assert updates[0].message.operation.object_id == 'counter:score@1000'
    # RTINS16e2: the message is the public ObjectMessage derived from the source per PAOM3
    assert isinstance(updates[0].message, publicmessage.ObjectMessage)
    assert updates[0].message == build_public_object_message(counter_inc, 'test')


# UTS: objects/unit/RTLO4b4e/tombstone-flag-true-0
async def test_rtlo4b4e_tombstone_flag_true():
    ctx = await setup_synced_channel('test')
    updates = []
    instance = ctx.root.get('score').instance()
    instance.as_live_counter().subscribe(lambda event: updates.append(event))

    ctx.mock_ws.send_to_client(build_object_message('test', [
        build_object_delete('counter:score@1000', '50', 'remote'),
    ]))
    await poll_until(lambda: len(updates) >= 1, timeout=5, description='the tombstone update to be delivered')
    await settle()

    assert len(updates) == 1
    assert updates[0].message.operation.action == ObjectOperationAction.OBJECT_DELETE


# UTS: objects/unit/RTLO4b4e/tombstone-flag-false-0
async def test_rtlo4b4e_tombstone_flag_false():
    ctx = await setup_synced_channel('test')
    updates = []
    instance = ctx.root.get('score').instance()
    instance.as_live_counter().subscribe(lambda event: updates.append(event))

    ctx.mock_ws.send_to_client(build_object_message('test', [
        build_counter_inc('counter:score@1000', 7, '99', 'remote'),
    ]))
    await poll_until(lambda: len(updates) >= 1, timeout=5, description='the counter update to be delivered')
    await settle()

    assert len(updates) == 1
    assert updates[0].message.operation.action == ObjectOperationAction.COUNTER_INC
