"""Derived from uts/objects/unit/path_object_subscribe.md in ably/specification.

Spec points: RTPO19, RTPO19b, RTPO19c1, RTPO19c1a, RTPO19d, RTPO19e1, RTPO19e2, RTPO19f, RTPO19g,
RTO24b1, RTO24b2, RTO24b2a, RTO24b2a1, RTO24b2a2, RTO24b2b, RTO24b2b2, RTO24b2c, RTO24c1, RTO24c2a,
RTO24c2b, RTO24c2c, RTO24c2d, RTO25b, RTLM24

`subscribe` is on the base `PathObject` (LODR-061, RTTS3d) and is synchronous; the specification's
`{ depth: n }` option is the keyword argument `depth=n`. The listener receives a
`PathObjectSubscriptionEvent` whose `object` is a base `PathObject`, so the counter value RTPO19e1
reads is `event.object.as_live_counter().value()`, and whose `message` is the public `ObjectMessage`
with snake_case fields (`site_code`, `operation.object_id`, `operation.counter_inc`) and the action as
an `ObjectOperationAction`.

Each stimulus is an inbound OBJECT or OBJECT_SYNC message, which the client applies on the
transport's read task, so every positive expectation is reached with `poll_until`. Where the
specification then asserts an exact count, or that a listener stayed silent, the test first awaits
the delivery of a control (a further event, or an unlimited-depth listener on the same dispatch) and
settles, so that a late or spurious callback would already have run. Where the specification
subscribes straight after sending a seeding message, the test waits for the seed to be applied
first, since a seed applied after the subscription would itself be delivered to it.
"""

import pytest

from ably.pubsub.objects.objectmessage import ObjectOperationAction
from ably.pubsub.objects.pathobject import PathObject
from ably.pubsub.objects.subscription import Subscription
from ably.pubsub.types.channelstate import ChannelState
from ably.pubsub.util.exceptions import AblyException
from test.uts.helpers.client import await_channel_state, poll_until
from test.uts.helpers.clock import settle
from test.uts.objects.helpers.standard_test_pool import (
    build_counter_inc,
    build_map_clear,
    build_map_set,
    build_object_message,
    build_object_state,
    build_object_sync_message,
    objects_channel_options,
    objects_client,
    remote_serial,
    setup_synced_channel,
    standard_mock_websocket,
)


# UTS: objects/unit/RTPO19/subscribe-receives-events-0
async def test_rtpo19_subscribe_receives_events():
    client, channel, root, mock_ws = await setup_synced_channel('test')
    events = []
    sub = root.get('score').subscribe(events.append)

    mock_ws.send_to_client(build_object_message('test', [
        build_counter_inc('counter:score@1000', 7, '99', 'remote'),
    ]))
    await poll_until(lambda: len(events) >= 1, description='the COUNTER_INC event')
    await settle()

    assert isinstance(sub, Subscription)
    assert len(events) == 1
    assert isinstance(events[0].object, PathObject)
    assert events[0].object.path() == 'score'
    assert events[0].message is not None
    assert events[0].message.serial == '99'
    assert events[0].message.site_code == 'remote'
    assert events[0].message.operation is not None
    assert events[0].message.operation.action == ObjectOperationAction.COUNTER_INC
    assert events[0].message.channel == 'test'


# UTS: objects/unit/RTPO19b/subscribe-precondition-detached-0
async def test_rtpo19b_subscribe_precondition_detached():
    # The specification's hand-written mock is the standard one: CONNECTED with siteCode and
    # objectsGCGracePeriod, ATTACH answered with ATTACHED and the standard pool's OBJECT_SYNC,
    # DETACH answered with DETACHED
    mock_ws = standard_mock_websocket()
    client = objects_client(mock_ws)
    channel = client.channels.get('test', objects_channel_options())
    root = await channel.object.get()

    await channel.detach()
    await await_channel_state(channel, ChannelState.DETACHED)

    with pytest.raises(AblyException) as excinfo:
        root.subscribe(lambda event: None)

    assert excinfo.value.code == 90001
    assert excinfo.value.status_code == 400


# UTS: objects/unit/RTPO19c1a/subscribe-non-positive-depth-throws-0
async def test_rtpo19c1a_subscribe_non_positive_depth_throws():
    client, channel, root, mock_ws = await setup_synced_channel('test')

    with pytest.raises(AblyException) as excinfo:
        root.subscribe(lambda event: None, depth=0)

    assert excinfo.value.code == 40003


# UTS: objects/unit/RTPO19c1a/subscribe-negative-depth-throws-0
async def test_rtpo19c1a_subscribe_negative_depth_throws():
    client, channel, root, mock_ws = await setup_synced_channel('test')

    with pytest.raises(AblyException) as excinfo:
        root.subscribe(lambda event: None, depth=-1)

    assert excinfo.value.code == 40003


# UTS: objects/unit/RTPO19c1/subscribe-depth-1-self-only-0
async def test_rtpo19c1_subscribe_depth_1_self_only():
    client, channel, root, mock_ws = await setup_synced_channel('test')
    events = []
    root.subscribe(events.append, depth=1)
    # Quiescence control: an unlimited-depth root listener covers the out-of-scope child path
    control = []
    root.subscribe(control.append)

    mock_ws.send_to_client(build_object_message('test', [
        build_map_set('root', 'name', {'string': 'Bob'}, remote_serial(0), 'remote'),
    ]))
    await poll_until(lambda: len(events) >= 1, description='the self event')
    await settle()

    control_before = len(control)
    mock_ws.send_to_client(build_object_message('test', [
        build_counter_inc('counter:score@1000', 7, '100', 'remote'),
    ]))
    await poll_until(lambda: len(control) > control_before, description='the control to see the child event')
    await settle()

    assert len(events) == 1


# UTS: objects/unit/RTPO19c1/subscribe-depth-2-children-0
async def test_rtpo19c1_subscribe_depth_2_children():
    client, channel, root, mock_ws = await setup_synced_channel('test')
    events = []
    root.subscribe(events.append, depth=2)
    # Quiescence control: an unlimited-depth root listener covers the out-of-scope grandchild path
    control = []
    root.subscribe(control.append)

    # Self event (root map update): the candidate [] is covered at depth 2
    mock_ws.send_to_client(build_object_message('test', [
        build_map_set('root', 'name', {'string': 'Bob'}, remote_serial(0), 'remote'),
    ]))
    await poll_until(lambda: len(events) >= 1, description='the self event')

    # Child event (the counter at ["score"]): relative depth 1 - 0 + 1 = 2 <= 2, covered
    mock_ws.send_to_client(build_object_message('test', [
        build_counter_inc('counter:score@1000', 7, '100', 'remote'),
    ]))
    await poll_until(lambda: len(events) >= 2, description='the child event')
    await settle()

    # Grandchild event (the counter at ["profile", "nested_counter"]): relative depth
    # 2 - 0 + 1 = 3 > 2, not covered. A COUNTER_INC yields this single candidate only.
    control_before = len(control)
    mock_ws.send_to_client(build_object_message('test', [
        build_counter_inc('counter:nested@1000', 1, '101', 'remote'),
    ]))
    await poll_until(lambda: len(control) > control_before, description='the control to see the grandchild event')
    await settle()

    assert len(events) == 2


# UTS: objects/unit/RTPO19c1/subscribe-unlimited-depth-0
async def test_rtpo19c1_subscribe_unlimited_depth():
    client, channel, root, mock_ws = await setup_synced_channel('test')
    events = []
    root.subscribe(events.append)

    mock_ws.send_to_client(build_object_message('test', [
        build_map_set('root', 'name', {'string': 'Bob'}, remote_serial(0), 'remote'),
    ]))
    await poll_until(lambda: len(events) >= 1, description='the root event')

    mock_ws.send_to_client(build_object_message('test', [
        build_counter_inc('counter:score@1000', 7, '100', 'remote'),
    ]))
    await poll_until(lambda: len(events) >= 2, description='the child event')

    mock_ws.send_to_client(build_object_message('test', [
        build_map_set('map:prefs@1000', 'theme', {'string': 'light'}, remote_serial(1), 'remote'),
    ]))
    await poll_until(lambda: len(events) >= 3, description='the descendant event')

    assert len(events) >= 3


# UTS: objects/unit/RTPO19d/subscribe-returns-subscription-0
async def test_rtpo19d_subscribe_returns_subscription():
    client, channel, root, mock_ws = await setup_synced_channel('test')
    events = []
    sub = root.get('score').subscribe(events.append)
    # Quiescence control: a separate listener at the same path, which stays subscribed
    control = []
    root.get('score').subscribe(control.append)

    assert isinstance(sub, Subscription)
    sub.unsubscribe()

    mock_ws.send_to_client(build_object_message('test', [
        build_counter_inc('counter:score@1000', 7, '99', 'remote'),
    ]))
    await poll_until(lambda: len(control) >= 1, description='the control listener to fire')
    await settle()

    assert len(events) == 0


# UTS: objects/unit/RTPO19e1/event-path-object-correct-0
async def test_rtpo19e1_event_path_object_correct():
    client, channel, root, mock_ws = await setup_synced_channel('test')
    events = []
    root.subscribe(events.append)

    mock_ws.send_to_client(build_object_message('test', [
        build_counter_inc('counter:score@1000', 7, '99', 'remote'),
    ]))
    await poll_until(lambda: len(events) >= 1, description='the COUNTER_INC event')

    assert isinstance(events[0].object, PathObject)
    assert events[0].object.path() == 'score'
    assert events[0].object.as_live_counter().value() == 107


# UTS: objects/unit/RTPO19e2/event-message-delivery-0
async def test_rtpo19e2_event_message_delivery():
    client, channel, root, mock_ws = await setup_synced_channel('test')
    events = []
    root.get('score').subscribe(events.append)

    mock_ws.send_to_client(build_object_message('test', [
        build_counter_inc('counter:score@1000', 42, 'serial-1', 'site-a'),
    ]))
    await poll_until(lambda: len(events) >= 1, description='the COUNTER_INC event')

    assert events[0].message is not None
    assert events[0].message.channel == 'test'
    assert events[0].message.serial == 'serial-1'
    assert events[0].message.site_code == 'site-a'
    assert events[0].message.operation is not None
    assert events[0].message.operation.action == ObjectOperationAction.COUNTER_INC
    assert events[0].message.operation.object_id == 'counter:score@1000'
    assert events[0].message.operation.counter_inc.number == 42


# UTS: objects/unit/RTPO19e2/event-message-omitted-no-operation-0
async def test_rtpo19e2_event_message_omitted_no_operation():
    client, channel, root, mock_ws = await setup_synced_channel('test')
    events = []
    root.subscribe(events.append)

    # An OBJECT_SYNC that moves counter:score@1000 from 100 to 200 through replaceData (RTLC6), so
    # the update's ObjectMessage has no operation. It omits root, which is never removed from the
    # pool (RTO5c2a) and still references "score", so the counter stays reachable from the root
    # subscription.
    mock_ws.send_to_client(build_object_sync_message('test', 'sync2:', [
        build_object_state('counter:score@1000', {'aaa': 't:1'}, counter={'count': 0},
                           create_op={'counterCreate': {'count': 200}}),
    ]))
    await poll_until(lambda: len(events) >= 1, description='the sync-triggered event')
    await settle()

    # Events from sync-triggered updates carry no message
    for event in events:
        assert event.message is None


# UTS: objects/unit/RTPO19f/subscribe-follows-path-0
async def test_rtpo19f_subscribe_follows_path():
    client, channel, root, mock_ws = await setup_synced_channel('test')
    events = []
    root.get('score').subscribe(events.append)

    # Replace the counter at "score" with a new counter
    mock_ws.send_to_client(build_object_message('test', [
        build_map_set('root', 'score', {'objectId': 'counter:new@2000'}, remote_serial(0), 'remote'),
    ]))

    # Increment the new counter at "score"
    mock_ws.send_to_client(build_object_message('test', [
        build_counter_inc('counter:new@2000', 10, '100', 'remote'),
    ]))
    await poll_until(lambda: len(events) >= 2, description='the MAP_SET and COUNTER_INC events')
    await settle()

    # The subscription follows the path, so it sees the new counter
    found_new = False
    for event in events:
        if event.object.path() == 'score':
            found_new = True
    assert found_new is True
    # The second dispatch is the increment on the new counter, which is what shows the
    # subscription followed the path to the replacement rather than staying bound to the old
    # object; the MAP_SET dispatch alone would satisfy found_new
    assert len(events) == 2
    assert events[1].object.path() == 'score'
    assert events[1].message.operation.action == ObjectOperationAction.COUNTER_INC
    assert events[1].message.operation.object_id == 'counter:new@2000'


# UTS: objects/unit/RTPO19g/subscribe-no-side-effects-0
async def test_rtpo19g_subscribe_no_side_effects():
    client, channel, root, mock_ws = await setup_synced_channel('test')
    state_before = channel.state
    # RTPO19g also rules out side effects on the RealtimeObject and on the channel itself, which
    # the channel state alone does not show while it is attached
    sync_state_before = channel.object._sync_state
    sent_before = len(mock_ws.messages_from_client)

    root.get('score').subscribe(lambda event: None)
    await settle()

    assert channel.state == state_before
    assert channel.object._sync_state == sync_state_before
    assert len(mock_ws.messages_from_client) == sent_before


# UTS: objects/unit/RTPO19/subscribe-primitive-path-0
async def test_rtpo19_subscribe_primitive_path():
    client, channel, root, mock_ws = await setup_synced_channel('test')
    events = []
    root.get('name').subscribe(events.append)

    mock_ws.send_to_client(build_object_message('test', [
        build_map_set('root', 'name', {'string': 'Bob'}, remote_serial(0), 'remote'),
    ]))
    await poll_until(lambda: len(events) >= 1, description='the MAP_SET event at "name"')
    await settle()

    assert len(events) == 1
    assert events[0].object.path() == 'name'


# UTS: objects/unit/RTPO19/map-clear-triggers-child-events-0
async def test_rtpo19_map_clear_triggers_child_events():
    client, channel, root, mock_ws = await setup_synced_channel('test')
    events = []
    root.subscribe(events.append)
    # UTS SPEC ERROR: the specification clears with serial "99", which sorts before the pool's
    # entry serial "t:0", so RTLM24e1 removes no entry and the update carries no key; and it
    # subscribes at the root only, which fires for any root update. Neither reaches the child
    # paths the test is named for. The clear uses a serial after the pool's, and a subscription
    # at the child path "name" is asserted as well.
    child_events = []
    root.get('name').subscribe(child_events.append)

    mock_ws.send_to_client(build_object_message('test', [
        build_map_clear('root', remote_serial(0), 'remote'),
    ]))
    await poll_until(lambda: len(events) >= 1, description='the MAP_CLEAR event at the root')

    assert len(events) >= 1
    await poll_until(lambda: len(child_events) >= 1, description='the MAP_CLEAR event at "name"')
    assert child_events[0].object.path() == 'name'


# UTS: objects/unit/RTPO19/child-events-bubble-0
async def test_rtpo19_child_events_bubble():
    client, channel, root, mock_ws = await setup_synced_channel('test')
    events = []
    root.get('profile').subscribe(events.append)

    mock_ws.send_to_client(build_object_message('test', [
        build_map_set('map:profile@1000', 'email', {'string': 'bob@example.com'}, remote_serial(0), 'remote'),
    ]))
    await poll_until(lambda: len(events) >= 1, description='the profile event')

    mock_ws.send_to_client(build_object_message('test', [
        build_counter_inc('counter:nested@1000', 3, '100', 'remote'),
    ]))
    await poll_until(lambda: len(events) >= 2, description='the nested counter event')

    assert len(events) >= 2


# UTS: objects/unit/RTO24c1/depth-filtering-formula-0
async def test_rto24c1_depth_filtering_formula():
    client, channel, root, mock_ws = await setup_synced_channel('test')
    # Seed a grandchild object under profile.prefs (path ["profile", "prefs", "deep"]), so the
    # grandchild stimulus below can be a COUNTER_INC yielding only that depth-3 candidate (RTO6
    # creates counter:deep@3000 at its zero value)
    mock_ws.send_to_client(build_object_message('test', [
        build_map_set('map:prefs@1000', 'deep', {'objectId': 'counter:deep@3000'}, '50', 'remote'),
    ]))
    # The specification subscribes straight after the send, relying on the seed not reaching
    # the listener under test; it is applied on the read task, and its ["profile", "prefs"]
    # candidate is covered at depth 2, so it must land before the subscription
    await poll_until(lambda: 'deep' in root.get('profile').get('prefs').as_live_map().keys(),
                     description='the seeding MAP_SET to be applied')
    events = []
    # Subscribed at "profile" with depth 2:
    # self (profile)          -> ["profile"],                  1 - 1 + 1 = 1 <= 2, covered
    # child (profile.nested)  -> ["profile", "nested_counter"], 2 - 1 + 1 = 2 <= 2, covered
    # grandchild (prefs.deep) -> ["profile", "prefs", "deep"],  3 - 1 + 1 = 3 > 2, not covered
    root.get('profile').subscribe(events.append, depth=2)
    # Quiescence control: an unlimited-depth root listener covers the out-of-scope grandchild path
    control = []
    root.subscribe(control.append)

    # Self event (profile map update): the first covered candidate is ["profile"]
    mock_ws.send_to_client(build_object_message('test', [
        build_map_set('map:profile@1000', 'email', {'string': 'bob@example.com'}, remote_serial(0), 'remote'),
    ]))
    await poll_until(lambda: len(events) >= 1, description='the self event')

    # Child event (the nested counter, relative depth 2): covered
    mock_ws.send_to_client(build_object_message('test', [
        build_counter_inc('counter:nested@1000', 3, '100', 'remote'),
    ]))
    await poll_until(lambda: len(events) >= 2, description='the child event')
    await settle()

    # Grandchild event (counter:deep, relative depth 3): not covered. A COUNTER_INC yields only
    # this candidate, where a MAP_SET on map:prefs would also yield the covered ["profile", "prefs"].
    control_before = len(control)
    mock_ws.send_to_client(build_object_message('test', [
        build_counter_inc('counter:deep@3000', 1, '101', 'remote'),
    ]))
    await poll_until(lambda: len(control) > control_before, description='the control to see the grandchild event')
    await settle()

    assert len(events) == 2


# UTS: objects/unit/RTO24c1/prefix-mismatch-0
async def test_rto24c1_prefix_mismatch():
    client, channel, root, mock_ws = await setup_synced_channel('test')
    profile_events = []
    root.get('profile').subscribe(profile_events.append)
    # Control listener at the root, which fires on both out-of-scope sends below
    control_events = []
    root.subscribe(control_events.append)

    # Change at "score": "profile" is not a prefix of "score"
    mock_ws.send_to_client(build_object_message('test', [
        build_counter_inc('counter:score@1000', 7, '99', 'remote'),
    ]))

    # Change at "name": "profile" is not a prefix of "name"
    mock_ws.send_to_client(build_object_message('test', [
        build_map_set('root', 'name', {'string': 'Bob'}, remote_serial(0), 'remote'),
    ]))
    await poll_until(lambda: len(control_events) >= 2, description='the control to see both events')
    await settle()

    assert len(profile_events) == 0


# UTS: objects/unit/RTO24b2a/candidate-paths-map-keys-0
async def test_rto24b2a_candidate_paths_map_keys():
    client, channel, root, mock_ws = await setup_synced_channel('test')
    score_events = []
    root_events = []
    # Subscribed at the child path ["score"]
    root.get('score').subscribe(score_events.append)
    # Subscribed at the root path []
    root.subscribe(root_events.append)

    # A MAP_SET on root with key "score" yields the candidates [] (root itself) and ["score"]
    # (from the map update key), so both subscriptions fire
    mock_ws.send_to_client(build_object_message('test', [
        build_map_set('root', 'score', {'objectId': 'counter:new@2000'}, remote_serial(0), 'remote'),
    ]))
    await poll_until(lambda: len(score_events) >= 1, description='the event at "score"')
    await poll_until(lambda: len(root_events) >= 1, description='the event at the root')
    await settle()

    assert len(score_events) == 1
    assert score_events[0].object.path() == 'score'
    assert len(root_events) == 1


# UTS: objects/unit/RTO24b2c/listener-exception-caught-0
async def test_rto24b2c_listener_exception_caught():
    client, channel, root, mock_ws = await setup_synced_channel('test')
    events = []

    def boom(event):
        raise Exception('boom')

    root.subscribe(boom)
    root.subscribe(events.append)

    mock_ws.send_to_client(build_object_message('test', [
        build_map_set('root', 'name', {'string': 'Bob'}, remote_serial(0), 'remote'),
    ]))
    await poll_until(lambda: len(events) >= 1, description='the second listener to fire')
    await settle()

    assert len(events) == 1


# UTS: objects/unit/RTO24b1/multi-path-dispatch-0
async def test_rto24b1_multi_path_dispatch():
    client, channel, root, mock_ws = await setup_synced_channel('test')
    events_score = []
    events_alias = []

    # "score" already points to counter:score@1000; a second reference "alias" gives it two paths
    mock_ws.send_to_client(build_object_message('test', [
        build_map_set('root', 'alias', {'objectId': 'counter:score@1000'}, '98', 'remote'),
    ]))
    # The specification subscribes straight after the send; the MAP_SET is applied on the read
    # task, and its ["alias"] candidate would reach the "alias" subscription if it landed after it
    await poll_until(lambda: 'alias' in root.keys(), description='the alias MAP_SET to be applied')

    root.get('score').subscribe(events_score.append)
    root.get('alias').subscribe(events_alias.append)

    # Increment counter:score@1000, whose full paths are ["score"] and ["alias"]
    mock_ws.send_to_client(build_object_message('test', [
        build_counter_inc('counter:score@1000', 5, '99', 'remote'),
    ]))
    await poll_until(lambda: len(events_score) >= 1, description='the event at "score"')
    await poll_until(lambda: len(events_alias) >= 1, description='the event at "alias"')
    await settle()

    assert len(events_score) == 1
    assert events_score[0].object.path() == 'score'
    assert len(events_alias) == 1
    assert events_alias[0].object.path() == 'alias'


# UTS: objects/unit/RTO24b2b/fires-once-per-dispatch-0
async def test_rto24b2b_fires_once_per_dispatch():
    client, channel, root, mock_ws = await setup_synced_channel('test')
    events = []
    # Subscribed at the root with unlimited depth, covering both [] and ["score"]
    root.subscribe(events.append)

    # A MAP_SET on root with key "score" yields the candidates [] and ["score"]; the root
    # subscription covers both and fires once, with the first
    mock_ws.send_to_client(build_object_message('test', [
        build_map_set('root', 'score', {'objectId': 'counter:new@2000'}, remote_serial(0), 'remote'),
    ]))
    await poll_until(lambda: len(events) >= 1, description='the MAP_SET event')

    # Quiescence: a second, single-candidate dispatch is the control delivery, so a spurious
    # second callback from the first dispatch would already have run
    mock_ws.send_to_client(build_object_message('test', [
        build_counter_inc('counter:new@2000', 1, '100', 'remote'),
    ]))
    await poll_until(lambda: len(events) >= 2, description='the control COUNTER_INC event')
    await settle()

    # One event per dispatch, though the first had two covered candidates
    assert len(events) == 2
