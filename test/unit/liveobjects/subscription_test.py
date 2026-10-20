"""Which listeners a dispatch calls when listeners are added or removed during it.

Spec points: RTLO4b4c3a (`subscribe` listeners on a live object) and RTO24b (path
subscriptions). The specification does not say how a dispatch treats registrations changed
by its own listeners; the library takes one snapshot per dispatch, so that a listener added
during it is not called by it, and skips a listener removed during it, for both kinds.
"""

from test.uts.helpers.clock import settle
from test.uts.objects.helpers.standard_test_pool import (
    build_counter_inc,
    build_map_set,
    build_object_message,
    remote_serial,
    setup_synced_channel,
)

SCORE = 'counter:score@1000'


async def test_rtlo4b4c3a_a_listener_unsubscribed_during_a_dispatch_is_not_called():
    """RTLO4b4c3a: a listener that another listener unsubscribes earlier in the same dispatch
    is not called for that update."""
    client, channel, root, mock_ws = await setup_synced_channel('test')
    counter = root.get('score').instance().as_live_counter()
    calls = []
    second = None

    def first(event):
        calls.append('first')
        second.unsubscribe()

    counter.subscribe(first)
    second = counter.subscribe(lambda event: calls.append('second'))
    await counter.increment(1)
    await settle()

    assert calls == ['first']


async def test_rto24b_a_subscription_made_during_a_dispatch_is_not_called_by_it():
    """RTO24b: a path subscription made by a listener is not called by the dispatch that made
    it, even for a later path to the same object, and is called by the next update."""
    client, channel, root, mock_ws = await setup_synced_channel('test')
    # root.alias references the same counter as root.score, so the counter has two paths
    mock_ws.send_to_client(build_object_message('test', [
        build_map_set('root', 'alias', {'objectId': SCORE}, remote_serial(0), 'remote')]))
    await settle()
    assert root.get('alias').as_live_counter().value() == 100

    late_calls = []
    added = []

    def first(event):
        if not added:
            added.append(root.subscribe(lambda late_event: late_calls.append(late_event.object.path())))

    root.get('score').subscribe(first)
    root.get('alias').subscribe(first)
    mock_ws.send_to_client(build_object_message('test', [
        build_counter_inc(SCORE, 1, remote_serial(1), 'remote')]))
    await settle()
    assert added
    assert late_calls == []

    mock_ws.send_to_client(build_object_message('test', [
        build_counter_inc(SCORE, 1, remote_serial(2), 'remote')]))
    await settle()
    assert sorted(late_calls) == ['alias', 'score']
