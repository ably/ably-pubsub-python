"""Derived from uts/objects/unit/path_object_mutations.md in ably/specification.

Spec points: RTPO3c2, RTPO15, RTPO15a2, RTPO15b, RTPO15c, RTPO15d, RTPO15e, RTPO16, RTPO16b, RTPO16c,
RTPO16d, RTPO16e, RTPO17, RTPO17a1, RTPO17b, RTPO17c, RTPO17d, RTPO17e, RTPO18, RTPO18a1, RTPO18b,
RTPO18c, RTPO18d, RTPO18e, RTTS5d2

The specification writes through the untyped `PathObject`. ably-python partitions it (LODR-061,
RTTS3-RTTS6): `set` and `remove` are on `LiveMapPathObject` and `increment` and `decrement` on
`LiveCounterPathObject`, reached through the unchecked view helpers. `root` is already a
`LiveMapPathObject`, so `root.set(...)` needs no view; `root.get('score').increment(25)` is
`root.get('score').as_live_counter().increment(25)`. A view never raises for the type at the path;
the write through it raises 92007 for a path resolving to the wrong type and 92005 for one that does
not resolve (RTTS5d2), which is what the specification's failure cases assert.

Every write is awaited against the standard mock, which ACKs each OBJECT message, so the operation
has been applied locally (RTO20) by the time the write returns and the read that follows needs no
wait. Reads go through the view matching the type written: `as_primitive()` for map entries,
`as_live_counter()` for the counter.
"""

import pytest

from ably.pubsub.util.exceptions import AblyException
from test.uts.objects.helpers.standard_test_pool import setup_synced_channel


# UTS: objects/unit/RTPO15/set-delegates-to-map-0
async def test_rtpo15_set_delegates_to_map():
    client, channel, root, mock_ws = await setup_synced_channel('test')

    await root.set('name', 'Bob')

    assert root.get('name').as_primitive().value() == 'Bob'


# UTS: objects/unit/RTPO15/set-nested-path-0
async def test_rtpo15_set_nested_path():
    client, channel, root, mock_ws = await setup_synced_channel('test')

    await root.get('profile').as_live_map().set('email', 'bob@example.com')

    assert root.get('profile').get('email').as_primitive().value() == 'bob@example.com'


# UTS: objects/unit/RTPO15d/set-non-map-throws-0
async def test_rtpo15d_set_non_map_throws():
    client, channel, root, mock_ws = await setup_synced_channel('test')

    # The map view is unchecked (RTTS5d); `set` through it finds a counter at the path
    with pytest.raises(AblyException) as excinfo:
        await root.get('score').as_live_map().set('key', 'value')

    assert excinfo.value.code == 92007


# UTS: objects/unit/RTPO16/remove-delegates-to-map-0
async def test_rtpo16_remove_delegates_to_map():
    client, channel, root, mock_ws = await setup_synced_channel('test')

    await root.remove('name')

    assert root.get('name').as_primitive().value() is None


# UTS: objects/unit/RTPO16d/remove-non-map-throws-0
async def test_rtpo16d_remove_non_map_throws():
    client, channel, root, mock_ws = await setup_synced_channel('test')

    with pytest.raises(AblyException) as excinfo:
        await root.get('score').as_live_map().remove('key')

    assert excinfo.value.code == 92007


# UTS: objects/unit/RTPO17/increment-delegates-to-counter-0
async def test_rtpo17_increment_delegates_to_counter():
    client, channel, root, mock_ws = await setup_synced_channel('test')

    await root.get('score').as_live_counter().increment(25)

    assert root.get('score').as_live_counter().value() == 125


# UTS: objects/unit/RTPO17/increment-default-amount-0
async def test_rtpo17_increment_default_amount():
    client, channel, root, mock_ws = await setup_synced_channel('test')

    await root.get('score').as_live_counter().increment()

    assert root.get('score').as_live_counter().value() == 101


# UTS: objects/unit/RTPO17d/increment-non-counter-throws-0
async def test_rtpo17d_increment_non_counter_throws():
    client, channel, root, mock_ws = await setup_synced_channel('test')

    # `root` is a `LiveMapPathObject` and has no `increment`; the counter view over the root
    # path is the translation, and the root map is the wrong type for it
    with pytest.raises(AblyException) as excinfo:
        await root.as_live_counter().increment(5)

    assert excinfo.value.code == 92007


# UTS: objects/unit/RTPO18/decrement-delegates-to-counter-0
async def test_rtpo18_decrement_delegates_to_counter():
    client, channel, root, mock_ws = await setup_synced_channel('test')

    await root.get('score').as_live_counter().decrement(10)

    assert root.get('score').as_live_counter().value() == 90


# UTS: objects/unit/RTPO18/decrement-default-amount-0
async def test_rtpo18_decrement_default_amount():
    client, channel, root, mock_ws = await setup_synced_channel('test')

    await root.get('score').as_live_counter().decrement()

    assert root.get('score').as_live_counter().value() == 99


# UTS: objects/unit/RTPO18d/decrement-non-counter-throws-0
async def test_rtpo18d_decrement_non_counter_throws():
    client, channel, root, mock_ws = await setup_synced_channel('test')

    with pytest.raises(AblyException) as excinfo:
        await root.as_live_counter().decrement(5)

    assert excinfo.value.code == 92007


# UTS: objects/unit/RTPO3c2/set-unresolvable-throws-0
async def test_rtpo3c2_set_unresolvable_throws():
    client, channel, root, mock_ws = await setup_synced_channel('test')

    with pytest.raises(AblyException) as excinfo:
        await root.get('nonexistent').get('deep').as_live_map().set('key', 'value')

    assert excinfo.value.code == 92005
    assert excinfo.value.status_code == 400


# UTS: objects/unit/RTPO3c2/increment-unresolvable-throws-0
async def test_rtpo3c2_increment_unresolvable_throws():
    client, channel, root, mock_ws = await setup_synced_channel('test')

    with pytest.raises(AblyException) as excinfo:
        await root.get('nonexistent').as_live_counter().increment(5)

    assert excinfo.value.code == 92005
    assert excinfo.value.status_code == 400
