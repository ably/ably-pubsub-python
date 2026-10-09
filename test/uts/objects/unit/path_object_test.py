"""Derived from uts/objects/unit/path_object.md in ably/specification.

Spec points: RTPO3, RTPO3a1, RTPO3b, RTPO3c1, RTPO4, RTPO4a, RTPO4b, RTPO4c, RTPO5, RTPO5b, RTPO5c,
RTPO5d, RTPO6, RTPO6b, RTPO6d, RTPO7, RTPO7a, RTPO7c, RTPO7d, RTPO7e, RTPO7f, RTPO8, RTPO8a, RTPO8c,
RTPO8f, RTPO9, RTPO9a, RTPO9c, RTPO9d, RTPO10, RTPO10a, RTPO10c, RTPO10d, RTPO11, RTPO11a, RTPO11c,
RTPO11d, RTPO12, RTPO12a, RTPO12c, RTPO12d, RTPO13, RTPO13a, RTPO13c1, RTPO13c2, RTPO13c3, RTPO13c4,
RTPO13c5, RTPO13d, RTPO14, RTPO14a, RTPO14b1, RTPO14b2, RTINS3b, RTINS4c, RTTS5d1

The specification reads through the untyped `PathObject`, which carries every method. ably-python
partitions it (LODR-061, RTTS3-RTTS6): navigation, `instance`, `compact` and `compact_json` are on the
base `PathObject`, and the type-specific reads are reached through the unchecked view helpers, so
`po.value()` on a counter is `po.as_live_counter().value()`, on a primitive `po.as_primitive().value()`,
and `po.keys()` is `po.as_live_map().keys()`. A view whose type does not match what the path resolves
to answers None, or `[]` for the collection reads (RTTS5d1), which is what the specification's
null and empty-array expectations become. Where the specification expects the untyped `value()` to
be null, neither value view may answer, so both are asserted.

Every test opens with the standard synced channel; the module issues no writes, so no ACK is involved.
"""

import pytest

from ably.pubsub.objects.instance import Instance
from ably.pubsub.util.exceptions import AblyException
from test.uts.helpers.client import poll_until
from test.uts.objects.helpers.standard_test_pool import (
    build_map_set,
    build_object_message,
    setup_synced_channel,
)


async def _apply_back_ref(root, mock_ws):
    """Sends the specification's `prefs.back_ref -> profile` MAP_SET, closing a cycle, and waits for it.

    The MAP_SET is an inbound OBJECT message, applied on the transport's read task, so the
    specification's quiescence barrier is a poll until the new key is visible.
    """
    mock_ws.send_to_client(build_object_message('test', [
        build_map_set('map:prefs@1000', 'back_ref', {'objectId': 'map:profile@1000'}, '99', 'remote'),
    ]))
    await poll_until(lambda: 'back_ref' in root.get('profile').get('prefs').as_live_map().keys(),
                     description='the back_ref MAP_SET to be applied')


# UTS: objects/unit/RTPO4/path-string-representation-0
async def test_rtpo4_path_string_representation():
    client, channel, root, mock_ws = await setup_synced_channel('test')

    assert root.path() == ''
    assert root.get('profile').path() == 'profile'
    assert root.get('profile').get('email').path() == 'profile.email'


# UTS: objects/unit/RTPO4b/path-escapes-dots-0
async def test_rtpo4b_path_escapes_dots():
    client, channel, root, mock_ws = await setup_synced_channel('test')

    po = root.get('a.b').get('c')

    # The specification's "a\\.b.c" is the string a\.b.c: one backslash before the dot in the segment
    assert po.path() == 'a\\.b.c'


# UTS: objects/unit/RTPO5/get-appends-key-0
async def test_rtpo5_get_appends_key():
    client, channel, root, mock_ws = await setup_synced_channel('test')

    child = root.get('profile')
    grandchild = child.get('email')

    assert child.path() == 'profile'
    assert grandchild.path() == 'profile.email'
    assert child is not root


# UTS: objects/unit/RTPO5b/get-non-string-throws-0
async def test_rtpo5b_get_non_string_throws():
    client, channel, root, mock_ws = await setup_synced_channel('test')

    with pytest.raises(AblyException) as excinfo:
        root.get(123)

    assert excinfo.value.code == 40003


# UTS: objects/unit/RTPO6/at-parses-path-0
async def test_rtpo6_at_parses_path():
    client, channel, root, mock_ws = await setup_synced_channel('test')

    po = root.at('profile.email')

    assert po.path() == 'profile.email'
    assert po.as_primitive().value() == 'alice@example.com'


# UTS: objects/unit/RTPO6/at-escaped-dots-0
async def test_rtpo6_at_escaped_dots():
    client, channel, root, mock_ws = await setup_synced_channel('test')

    po = root.at('a\\.b.c')

    assert po.path() == 'a\\.b.c'
    # UTS SPEC ERROR: the round trip through path() alone does not show that `\.` stayed inside
    # its segment: an `at` that split on every dot gives the segments ['a\\', 'b', 'c'], which
    # path() renders as the same string. RTPO6b makes `\.` a literal dot within a segment, so
    # the parsed segments are asserted as well.
    assert po._path == ['a.b', 'c']


# UTS: objects/unit/RTPO6b/at-non-string-throws-0
async def test_rtpo6b_at_non_string_throws():
    client, channel, root, mock_ws = await setup_synced_channel('test')

    # NOTE: the features spec's RTPO6 defines no error for a path that is not a string (RTPO5b
    # covers `get` only); 40003 is asserted as the specification has it, consistently with RTPO5b.
    # ably-python's `at` also takes a sequence of segments (LODR-061), and an int is neither.
    with pytest.raises(AblyException) as excinfo:
        root.at(123)

    assert excinfo.value.code == 40003


# UTS: objects/unit/RTPO7/value-counter-0
async def test_rtpo7_value_counter():
    client, channel, root, mock_ws = await setup_synced_channel('test')

    assert root.get('score').as_live_counter().value() == 100


# UTS: objects/unit/RTPO7/value-primitive-0
async def test_rtpo7_value_primitive():
    client, channel, root, mock_ws = await setup_synced_channel('test')

    assert root.get('name').as_primitive().value() == 'Alice'
    assert root.get('age').as_primitive().value() == 30
    assert root.get('active').as_primitive().value() is True


# UTS: objects/unit/RTPO7d/value-livemap-null-0
async def test_rtpo7d_value_livemap_null():
    client, channel, root, mock_ws = await setup_synced_channel('test')

    profile = root.get('profile')

    # value() on a map is null (RTPO7e); neither value view answers for a map (RTTS6b, RTTS6c)
    assert profile.as_primitive().value() is None
    assert profile.as_live_counter().value() is None


# UTS: objects/unit/RTPO7e/value-unresolvable-null-0
async def test_rtpo7e_value_unresolvable_null():
    client, channel, root, mock_ws = await setup_synced_channel('test')

    deep = root.get('nonexistent').get('deep')

    assert deep.as_primitive().value() is None
    assert deep.as_live_counter().value() is None


# UTS: objects/unit/RTPO8/instance-live-object-0
async def test_rtpo8_instance_live_object():
    client, channel, root, mock_ws = await setup_synced_channel('test')

    counter_inst = root.get('score').instance()
    assert isinstance(counter_inst, Instance)
    assert counter_inst.id == 'counter:score@1000'

    map_inst = root.get('profile').instance()
    assert isinstance(map_inst, Instance)
    assert map_inst.id == 'map:profile@1000'


# UTS: objects/unit/RTPO8f/instance-primitive-wrapped-0
async def test_rtpo8f_instance_primitive_wrapped():
    client, channel, root, mock_ws = await setup_synced_channel('test')

    name_inst = root.get('name').instance()

    assert isinstance(name_inst, Instance)
    assert name_inst.id is None
    assert name_inst.as_primitive().value() == 'Alice'


# UTS: objects/unit/RTPO9/entries-yields-pairs-0
async def test_rtpo9_entries_yields_pairs():
    client, channel, root, mock_ws = await setup_synced_channel('test')

    entries = {}
    for key, path_obj in root.entries():
        entries[key] = path_obj.path()

    assert entries['name'] == 'name'
    assert entries['profile'] == 'profile'
    assert len(entries) == 7


# UTS: objects/unit/RTPO9d/entries-non-map-empty-0
async def test_rtpo9d_entries_non_map_empty():
    client, channel, root, mock_ws = await setup_synced_channel('test')

    entries = root.get('score').as_live_map().entries()

    assert len(entries) == 0


# UTS: objects/unit/RTPO10/keys-returns-array-0
async def test_rtpo10_keys_returns_array():
    client, channel, root, mock_ws = await setup_synced_channel('test')

    keys = root.keys()

    assert isinstance(keys, list)
    assert len(keys) == 7
    assert 'name' in keys
    assert 'profile' in keys
    assert 'score' in keys


# UTS: objects/unit/RTPO10d/keys-non-map-empty-0
async def test_rtpo10d_keys_non_map_empty():
    client, channel, root, mock_ws = await setup_synced_channel('test')

    keys = root.get('score').as_live_map().keys()

    assert isinstance(keys, list)
    assert len(keys) == 0


# UTS: objects/unit/RTPO11/values-returns-array-0
async def test_rtpo11_values_returns_array():
    client, channel, root, mock_ws = await setup_synced_channel('test')

    vals = root.values()

    assert isinstance(vals, list)
    assert len(vals) == 7
    # Each element is a PathObject whose path is the key
    paths = {}
    for v in vals:
        paths[v.path()] = True
    assert paths['name'] is True
    assert paths['profile'] is True
    assert paths['score'] is True


# UTS: objects/unit/RTPO11d/values-non-map-empty-0
async def test_rtpo11d_values_non_map_empty():
    client, channel, root, mock_ws = await setup_synced_channel('test')

    vals = root.get('score').as_live_map().values()

    assert isinstance(vals, list)
    assert len(vals) == 0


# UTS: objects/unit/RTPO12/size-count-0
async def test_rtpo12_size_count():
    client, channel, root, mock_ws = await setup_synced_channel('test')

    assert root.size() == 7
    assert root.get('profile').as_live_map().size() == 3


# UTS: objects/unit/RTPO12c/size-non-map-null-0
async def test_rtpo12c_size_non_map_null():
    client, channel, root, mock_ws = await setup_synced_channel('test')

    assert root.get('score').as_live_map().size() is None
    assert root.get('name').as_live_map().size() is None


# UTS: objects/unit/RTPO13/compact-recursive-0
async def test_rtpo13_compact_recursive():
    client, channel, root, mock_ws = await setup_synced_channel('test')

    result = root.compact()

    assert result['name'] == 'Alice'
    assert result['age'] == 30
    assert result['active'] is True
    assert result['score'] == 100
    assert result['data'] == {'tags': ['a', 'b']}
    assert result['avatar'] == bytes([1, 2, 3])
    assert result['profile']['email'] == 'alice@example.com'
    assert result['profile']['nested_counter'] == 5
    assert result['profile']['prefs']['theme'] == 'dark'


# UTS: objects/unit/RTPO13c5/compact-cycle-detection-0
async def test_rtpo13c5_compact_cycle_detection():
    client, channel, root, mock_ws = await setup_synced_channel('test')
    await _apply_back_ref(root, mock_ws)

    result = root.get('profile').compact()

    assert result['prefs']['back_ref'] is result


# UTS: objects/unit/RTPO13c/compact-counter-0
async def test_rtpo13c_compact_counter():
    client, channel, root, mock_ws = await setup_synced_channel('test')

    assert root.get('score').compact() == 100


# UTS: objects/unit/RTPO14/compact-json-0
async def test_rtpo14_compact_json():
    client, channel, root, mock_ws = await setup_synced_channel('test')
    await _apply_back_ref(root, mock_ws)

    result = root.get('profile').compact_json()

    assert result['prefs']['back_ref'] == {'objectId': 'map:profile@1000'}


# UTS: objects/unit/RTPO3/path-resolution-walk-0
async def test_rtpo3_path_resolution_walk():
    client, channel, root, mock_ws = await setup_synced_channel('test')

    # The empty path resolves to the root map (RTPO3b), for which value() is null (RTPO7e)
    assert root.as_primitive().value() is None
    assert root.as_live_counter().value() is None
    assert root.get('profile').get('prefs').get('theme').as_primitive().value() == 'dark'


# UTS: objects/unit/RTPO3a1/intermediate-not-map-0
async def test_rtpo3a1_intermediate_not_map():
    client, channel, root, mock_ws = await setup_synced_channel('test')

    something = root.get('score').get('something')

    assert something.as_primitive().value() is None
    assert something.as_live_counter().value() is None


# UTS: objects/unit/RTPO3c1/read-null-on-failure-0
async def test_rtpo3c1_read_null_on_failure():
    client, channel, root, mock_ws = await setup_synced_channel('test')

    nonexistent = root.get('nonexistent')

    assert nonexistent.as_primitive().value() is None
    assert nonexistent.as_live_counter().value() is None
    assert nonexistent.instance() is None
    assert nonexistent.as_live_map().size() is None
    assert nonexistent.compact() is None


# UTS: objects/unit/RTPO7/value-bytes-0
async def test_rtpo7_value_bytes():
    client, channel, root, mock_ws = await setup_synced_channel('test')

    assert root.get('avatar').as_primitive().value() == bytes([1, 2, 3])


# UTS: objects/unit/RTPO14/compact-json-bytes-0
async def test_rtpo14_compact_json_bytes():
    client, channel, root, mock_ws = await setup_synced_channel('test')

    result = root.compact_json()

    assert result['avatar'] == 'AQID'
