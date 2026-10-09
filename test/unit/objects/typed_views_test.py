"""The typed views: `type()` and `exists()`, the unchecked path views and the checked instance views.

Spec points: RTTS2-RTTS10 (ably/specification#491), as LODR-061 binds them: one
`PrimitivePathObject` and `PrimitiveInstance` whose `value(expected)` stands for the six
per-primitive classes (RTTS6h), and `ValueType.UNKNOWN` for a value in none of the known
categories. No UTS specification covers the typed views, so these tests are written against
the features specification and LODR-061.

Each test drives the standard synced pool over the mock websocket.
"""

import typing

import pytest

from ably.pubsub.objects.liveobject import LiveObject, LiveObjectUpdate
from ably.pubsub.server import (
    Instance,
    LiveCounterInstance,
    LiveCounterPathObject,
    LiveMapInstance,
    LiveMapPathObject,
    PathObject,
    PrimitiveInstance,
    PrimitivePathObject,
    ValueType,
)
from ably.pubsub.types.channelstate import ChannelState
from ably.pubsub.util.exceptions import AblyException
from test.uts.helpers.client import poll_until
from test.uts.objects.helpers.standard_test_pool import (
    build_map_set,
    build_object_message,
    remote_serial,
    setup_synced_channel,
)

# The type of each value in the standard pool, and of the JSON array each test adds to it
POOL_VALUE_TYPES = {
    '': ValueType.LIVE_MAP,
    'name': ValueType.STRING,
    'age': ValueType.NUMBER,
    'active': ValueType.BOOLEAN,
    'avatar': ValueType.BINARY,
    'data': ValueType.JSON_OBJECT,
    'tags': ValueType.JSON_ARRAY,
    'score': ValueType.LIVE_COUNTER,
    'profile': ValueType.LIVE_MAP,
    'profile.prefs.theme': ValueType.STRING,
}


async def _synced_root():
    """The standard synced root, with a JSON array added at `tags`."""
    client, channel, root, mock_ws = await setup_synced_channel('test')
    await root.set('tags', ['a', 'b'])
    return root


def _at(root, path):
    """The path object at the dotted `path` from `root`, `root` itself for the empty path."""
    return root.at(path) if path else root


def _assert_error(excinfo, code):
    assert excinfo.value.code == code
    assert excinfo.value.status_code == 400


class _FutureLiveObject(LiveObject):
    """A live object of a type this SDK does not know, standing in for one a later protocol adds."""

    def apply_operation(self, object_message, source):
        return False

    def replace_data(self, object_message):
        return LiveObjectUpdate(noop=True)

    def clear_data(self):
        pass

    @staticmethod
    def diff(previous_data, new_data, *, for_tombstone=False):
        return LiveObjectUpdate(noop=True)


# --- type() and exists() ------------------------------------------------------------------

@pytest.mark.parametrize('path, value_type', POOL_VALUE_TYPES.items(), ids=[p or 'root' for p in POOL_VALUE_TYPES])
async def test_rtts4b_type_is_the_type_of_the_resolved_value(path, value_type):
    """RTTS4a, RTTS4b, RTTS2a1-RTTS2a8: `type()` is the `ValueType` of the value the path resolves to,
    and `exists()` is True for it."""
    root = await _synced_root()

    assert _at(root, path).type() is value_type
    assert _at(root, path).exists() is True


@pytest.mark.parametrize('path', ['missing', 'name.first', 'score.value', 'data.tags', 'profile.prefs.missing'])
async def test_rtts4b_type_is_none_where_nothing_resolves(path):
    """RTTS4a3, RTTS4b3: `type()` is None and `exists()` False for a path that does not resolve,
    including one that continues below a primitive or a counter."""
    root = await _synced_root()

    assert root.at(path).type() is None
    assert root.at(path).exists() is False


async def test_rtts4b_type_follows_the_value_at_the_path():
    """RTTS4b, RTTS8a: a path's type is read when it is asked for, so it follows a change to the
    value at the path; an instance's type is fixed by the value it wraps."""
    root = await _synced_root()
    score = root.get('score')
    instance = score.instance()

    await root.set('score', 'retired')
    assert score.type() is ValueType.STRING
    assert instance.type is ValueType.LIVE_COUNTER

    await root.remove('score')
    assert score.type() is None
    assert score.exists() is False


async def test_rtts2a9_type_is_unknown_for_a_value_in_no_known_category():
    """RTTS2a9: a value that resolves but falls into none of the known categories is
    `ValueType.UNKNOWN`, which is distinct from None for no value, and the typed views read
    None from it."""
    client, channel, root, mock_ws = await setup_synced_channel('test')
    channel.object._objects_pool['future:thing@1000'] = _FutureLiveObject('future:thing@1000')
    mock_ws.send_to_client(build_object_message('test', [
        build_map_set('root', 'thing', {'objectId': 'future:thing@1000'}, remote_serial(0), 'remote'),
    ]))
    await poll_until(lambda: 'thing' in root.keys(), description='the reference to be applied')

    thing = root.get('thing')
    assert thing.type() is ValueType.UNKNOWN
    assert thing.exists() is True
    assert thing.as_primitive().value() is None
    assert thing.as_live_counter().value() is None
    assert thing.as_live_map().size() is None
    assert thing.as_live_map().keys() == []
    assert thing.instance().type is ValueType.UNKNOWN


async def test_rtts4a1_rtts4b1_type_and_exists_check_access_preconditions():
    """RTTS4a1, RTTS4b1, RTO25b: `type()` and `exists()` raise 90001 on a detached channel."""
    client, channel, root, mock_ws = await setup_synced_channel('test')

    await channel.detach()
    assert channel.state == ChannelState.DETACHED

    for read in (root.get('name').type, root.get('name').exists):
        with pytest.raises(AblyException) as excinfo:
            read()
        _assert_error(excinfo, 90001)


# --- The unchecked path views -------------------------------------------------------------

async def test_rtts5_path_views_rewrap_the_same_path():
    """RTTS5, RTTS6d: `channel.object.get()` is a `LiveMapPathObject`; navigation gives base
    `PathObject`s, and each view helper gives the typed view of the same path, without reading
    anything."""
    root = await _synced_root()
    assert isinstance(root, LiveMapPathObject)

    path = root.get('profile').get('prefs')
    assert type(path) is PathObject
    for view, view_type in ((path.as_live_map(), LiveMapPathObject),
                            (path.as_live_counter(), LiveCounterPathObject),
                            (path.as_primitive(), PrimitivePathObject)):
        assert type(view) is view_type
        assert view.path() == 'profile.prefs'

    assert path.as_live_map().get('theme').as_primitive().value() == 'dark'
    # A view of a path that does not resolve is still a view
    assert root.get('missing').as_live_counter().path() == 'missing'


async def test_rtts5d1_mismatched_path_views_read_none():
    """RTTS5d, RTTS5d1: a path view never raises for the type at its path; a read through a view
    that does not match it gives None, or [] for the collections."""
    root = await _synced_root()

    name_as_map = root.get('name').as_live_map()
    assert name_as_map.keys() == []
    assert name_as_map.entries() == []
    assert name_as_map.values() == []
    assert name_as_map.size() is None

    assert root.get('name').as_live_counter().value() is None
    assert root.get('score').as_primitive().value() is None
    assert root.get('score').as_live_map().size() is None
    assert root.as_primitive().value() is None
    assert root.as_live_counter().value() is None
    assert root.get('missing').as_primitive().value() is None


async def test_rtts5d2_writes_through_mismatched_path_views_raise():
    """RTTS5d2: a write through a path view raises 92007 when the path resolves to another type,
    and 92005 when it does not resolve."""
    root = await _synced_root()

    for write, code in ((lambda: root.get('name').as_live_map().set('k', 'v'), 92007),
                        (lambda: root.get('profile').as_live_counter().increment(), 92007),
                        (lambda: root.get('score').as_live_map().remove('k'), 92007),
                        (lambda: root.get('missing').as_live_counter().decrement(), 92005),
                        (lambda: root.at('name.first').as_live_map().set('k', 'v'), 92005)):
        with pytest.raises(AblyException) as excinfo:
            await write()
        _assert_error(excinfo, code)

    assert root.get('name').as_primitive().value() == 'Alice'


async def test_rtts6b_counter_view_value_is_only_a_counters():
    """RTTS6b: `LiveCounterPathObject.value()` is the counter's value as a float, and None for
    anything else, a number included."""
    root = await _synced_root()

    score = root.get('score').as_live_counter().value()
    assert score == 100
    assert type(score) is float
    assert root.get('age').as_live_counter().value() is None
    assert root.as_live_counter().value() is None


@pytest.mark.parametrize('path, expected, value', [
    ('name', str, 'Alice'),
    ('name', float, None),
    ('age', float, 30.0),
    ('age', str, None),
    ('age', bool, None),
    ('active', bool, True),
    ('active', float, None),
    ('avatar', bytes, b'\x01\x02\x03'),
    ('avatar', str, None),
    ('data', dict, {'tags': ['a', 'b']}),
    ('data', list, None),
    ('tags', list, ['a', 'b']),
    ('tags', dict, None),
    ('score', float, None),
    ('profile', dict, None),
    ('missing', str, None),
], ids=lambda param: param.__name__ if isinstance(param, type) else None)
async def test_rtts6c_value_expected_filters_by_type(path, expected, value):
    """RTTS6c, RTTS6h: `value(expected)` is the primitive at the path only if it is of the expected
    type, judged by its wire type, so a boolean is never a number and a counter or map is never
    a primitive."""
    root = await _synced_root()

    result = root.get(path).as_primitive().value(expected)
    assert result == value
    assert type(result) is type(value)


async def test_rtts6c_value_without_expected_is_any_primitive():
    """RTTS6c, RTTS6h: `value()` with no `expected` is the primitive at the path whatever its type,
    and None for a live object."""
    root = await _synced_root()

    assert {path: _at(root, path).as_primitive().value() for path in POOL_VALUE_TYPES} == {
        '': None,
        'name': 'Alice',
        'age': 30.0,
        'active': True,
        'avatar': b'\x01\x02\x03',
        'data': {'tags': ['a', 'b']},
        'tags': ['a', 'b'],
        'score': None,
        'profile': None,
        'profile.prefs.theme': 'dark',
    }


async def test_rtts6c_value_rejects_an_unsupported_expected_type():
    """RTTS6c: `expected` is one of str, float, bool, bytes, list and dict; anything else, a
    subclass of one of them included, is a TypeError, raised before the preconditions are
    checked."""
    client, channel, root, mock_ws = await setup_synced_channel('test')
    age = root.get('age').as_primitive()
    name = root.get('name').as_primitive()

    for expected in (int, object, tuple, 'str', typing.List, type('Text', (str,), {})):
        with pytest.raises(TypeError):
            name.value(expected)

    await channel.detach()
    with pytest.raises(TypeError):
        age.value(int)
    with pytest.raises(AblyException) as excinfo:
        age.value(float)
    _assert_error(excinfo, 90001)


async def test_rtts6c_value_is_a_copy_of_a_json_value():
    """RTTS6c: a JSON value read through a view is the reader's own, so changing it leaves the
    object it was read from unchanged."""
    root = await _synced_root()

    data = root.get('data').as_primitive().value(dict)
    data['tags'].append('c')

    assert root.get('data').as_primitive().value(dict) == {'tags': ['a', 'b']}


# --- The checked instance views -----------------------------------------------------------

@pytest.mark.parametrize('path, value_type', POOL_VALUE_TYPES.items(), ids=[p or 'root' for p in POOL_VALUE_TYPES])
async def test_rtts8a_instance_type_is_the_type_of_the_wrapped_value(path, value_type):
    """RTTS7e, RTTS8a: every instance is the typed subclass matching the value it wraps, and its
    `type` property is that value's `ValueType`."""
    root = await _synced_root()

    instance = _at(root, path).instance()

    assert instance.type is value_type
    expected_class = {ValueType.LIVE_MAP: LiveMapInstance, ValueType.LIVE_COUNTER: LiveCounterInstance}.get(
        value_type, PrimitiveInstance)
    assert type(instance) is expected_class


async def test_rtts9d_instance_views_are_checked():
    """RTTS9, RTTS9d: an instance's view helper returns the instance for the type it wraps and
    raises 92007 for any other, where the same helper on a path never raises."""
    root = await _synced_root()
    instances = {
        'profile': (root.get('profile').instance(), 'as_live_map'),
        'score': (root.get('score').instance(), 'as_live_counter'),
        'name': (root.get('name').instance(), 'as_primitive'),
    }

    for path, (instance, matching_helper) in instances.items():
        assert getattr(instance, matching_helper)() is instance
        for helper in {'as_live_map', 'as_live_counter', 'as_primitive'} - {matching_helper}:
            with pytest.raises(AblyException) as excinfo:
                getattr(instance, helper)()
            _assert_error(excinfo, 92007)
            # The same request on the path is an unchecked expectation
            assert getattr(root.get(path), helper)().path() == path


async def test_rtts10_instance_id_is_a_property():
    """RTTS10a, RTTS10b, RTINS3: `id` is a property: the object id of a map or counter instance,
    and None for a primitive one."""
    root = await _synced_root()

    assert root.instance().id == 'root'
    assert root.get('profile').instance().id == 'map:profile@1000'
    assert root.get('score').instance().id == 'counter:score@1000'
    assert root.get('name').instance().id is None


@pytest.mark.parametrize('typed_class, present, absent', [
    (PathObject,
     {'path', 'type', 'exists', 'get', 'at', 'instance', 'compact', 'compact_json', 'subscribe',
      'as_live_map', 'as_live_counter', 'as_primitive'},
     {'value', 'entries', 'keys', 'values', 'size', 'set', 'remove', 'increment', 'decrement', 'batch'}),
    (LiveMapPathObject,
     {'entries', 'keys', 'values', 'size', 'set', 'remove', 'batch'},
     {'value', 'increment', 'decrement'}),
    (LiveCounterPathObject,
     {'value', 'increment', 'decrement', 'batch'},
     {'entries', 'keys', 'values', 'size', 'set', 'remove'}),
    (PrimitivePathObject,
     {'value'},
     {'entries', 'keys', 'values', 'size', 'set', 'remove', 'increment', 'decrement', 'batch'}),
    (Instance,
     {'id', 'type', 'get', 'compact', 'compact_json', 'as_live_map', 'as_live_counter', 'as_primitive'},
     {'value', 'entries', 'size', 'set', 'remove', 'increment', 'decrement', 'subscribe', 'batch'}),
    (LiveMapInstance,
     {'entries', 'keys', 'values', 'size', 'set', 'remove', 'subscribe', 'batch'},
     {'value', 'increment', 'decrement'}),
    (LiveCounterInstance,
     {'value', 'increment', 'decrement', 'subscribe', 'batch'},
     {'entries', 'keys', 'values', 'size', 'set', 'remove'}),
    (PrimitiveInstance,
     {'value'},
     {'entries', 'keys', 'values', 'size', 'set', 'remove', 'increment', 'decrement', 'subscribe', 'batch'}),
], ids=lambda param: param.__name__ if isinstance(param, type) else '')
def test_rtts3_rtts10_methods_are_partitioned_by_type(typed_class, present, absent):
    """RTTS3, RTTS6, RTTS7, RTTS10: each typed view carries the methods of its own type only, so
    `subscribe` is on map and counter instances alone and only live objects can be batched."""
    assert {name for name in present if not hasattr(typed_class, name)} == set()
    assert {name for name in absent if hasattr(typed_class, name)} == set()
