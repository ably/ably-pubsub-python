"""Derived from uts/objects/unit/parent_references.md in ably/specification.

Spec points: RTLO3f, RTLO3f2, RTLO4g, RTLO4g1, RTLO4g2, RTLO4h, RTLO4h1, RTLO4h2, RTLO4h3,
RTLO4f, RTLO4f1, RTLO4f2, RTLO4f3, RTLO4f4, RTO5c10, RTO5c10a, RTO5c10b

A pure unit specification: nothing is mocked and nothing is connected. Objects are built on
their own and then put in a pool with `pool[object_id] = obj`, which adopts them, so
`get_full_paths()` resolves their parents' ids through that pool. A path is a list of keys,
so the specification's `paths CONTAINS ["a", "x"]` is `['a', 'x'] in paths`.

The three RTO5c10 cases drive a sync, which the specification does through
`ObjectsPool.processAttached` and `processObjectSync`. The sync state machine is
`RealtimeObject`'s (shape deviation S-2), so those cases work on the pool a standalone
`RealtimeObject()` holds and drive the `RealtimeObject`, through the helpers below; they are
coroutines only so that an implementation is free to touch the event loop.
"""

from ably.pubsub.objects.enums import ObjectsSyncState
from ably.pubsub.objects.livecounter import InternalLiveCounter
from ably.pubsub.objects.livemap import InternalLiveMap
from ably.pubsub.objects.objectmessage import ObjectsMapSemantics
from ably.pubsub.objects.objectspool import ObjectsPool
from ably.pubsub.objects.realtimeobject import RealtimeObject
from test.uts.objects.helpers.standard_test_pool import (
    HAS_OBJECTS,
    LWW,
    build_object_state,
    build_object_sync_message,
    object_messages,
    objects_attached_message,
)


def _driven_pool():
    """The specification's `pool = ObjectsPool()`, in a test that then drives the sync state machine.

    S-2: the state machine is `RealtimeObject`'s, so the pool is the one a standalone
    `RealtimeObject` holds. Returns `(realtime_object, pool)`.
    """
    realtime_object = RealtimeObject()
    return realtime_object, realtime_object._objects_pool


def _process_attached(realtime_object, attached):
    """The specification's `pool.processAttached(attached)` (S-2).

    `RealtimeObject` is given the ATTACHED's HAS_OBJECTS flag and nothing else (RTO4).
    """
    realtime_object._on_attached(has_objects=bool(attached.get('flags', 0) & HAS_OBJECTS))


def _process_object_sync(realtime_object, protocol_message):
    """The specification's `pool.processObjectSync(protocol_message)` (S-2)."""
    realtime_object._handle_object_sync_messages(
        object_messages(protocol_message), protocol_message.get('channelSerial'))


# UTS: objects/unit/RTLO3f2/init-empty-counter-0
def test_rtlo3f2_init_empty_counter():
    counter = InternalLiveCounter('counter:abc@1000')

    assert counter.parent_references == {}


# UTS: objects/unit/RTLO3f2/init-empty-map-0
def test_rtlo3f2_init_empty_map():
    live_map = InternalLiveMap('map:abc@1000', ObjectsMapSemantics.LWW)

    assert live_map.parent_references == {}


# UTS: objects/unit/RTLO4g2/first-reference-new-entry-0
def test_rtlo4g2_first_reference_new_entry():
    child = InternalLiveCounter('counter:child@1000')
    parent = InternalLiveMap('map:parent@1000', ObjectsMapSemantics.LWW)

    child.add_parent_reference(parent, 'score')

    assert 'map:parent@1000' in child.parent_references
    assert child.parent_references['map:parent@1000'] == {'score'}


# UTS: objects/unit/RTLO4g1/second-key-same-parent-0
def test_rtlo4g1_second_key_same_parent():
    child = InternalLiveCounter('counter:child@1000')
    parent = InternalLiveMap('map:parent@1000', ObjectsMapSemantics.LWW)
    child.parent_references = {'map:parent@1000': {'score'}}

    child.add_parent_reference(parent, 'points')

    assert child.parent_references['map:parent@1000'] == {'score', 'points'}


# UTS: objects/unit/RTLO4g/different-parent-separate-entry-0
def test_rtlo4g_different_parent_separate_entry():
    child = InternalLiveCounter('counter:child@1000')
    parent_a = InternalLiveMap('map:a@1000', ObjectsMapSemantics.LWW)
    parent_b = InternalLiveMap('map:b@1000', ObjectsMapSemantics.LWW)

    child.add_parent_reference(parent_a, 'x')
    child.add_parent_reference(parent_b, 'y')

    assert child.parent_references['map:a@1000'] == {'x'}
    assert child.parent_references['map:b@1000'] == {'y'}


# UTS: objects/unit/RTLO4g/multiple-parents-multiple-keys-0
def test_rtlo4g_multiple_parents_multiple_keys():
    child = InternalLiveCounter('counter:child@1000')
    parent_a = InternalLiveMap('map:a@1000', ObjectsMapSemantics.LWW)
    parent_b = InternalLiveMap('map:b@1000', ObjectsMapSemantics.LWW)

    child.add_parent_reference(parent_a, 'x')
    child.add_parent_reference(parent_a, 'y')
    child.add_parent_reference(parent_b, 'p')
    child.add_parent_reference(parent_b, 'q')

    assert child.parent_references['map:a@1000'] == {'x', 'y'}
    assert child.parent_references['map:b@1000'] == {'p', 'q'}


# UTS: objects/unit/RTLO4h1/nonexistent-parent-noop-0
def test_rtlo4h1_nonexistent_parent_noop():
    child = InternalLiveCounter('counter:child@1000')
    parent = InternalLiveMap('map:parent@1000', ObjectsMapSemantics.LWW)

    child.remove_parent_reference(parent, 'score')

    assert child.parent_references == {}


# UTS: objects/unit/RTLO4h2/remove-key-leaves-others-0
def test_rtlo4h2_remove_key_leaves_others():
    child = InternalLiveCounter('counter:child@1000')
    parent = InternalLiveMap('map:parent@1000', ObjectsMapSemantics.LWW)
    child.parent_references = {'map:parent@1000': {'score', 'points'}}

    child.remove_parent_reference(parent, 'score')

    assert child.parent_references['map:parent@1000'] == {'points'}


# UTS: objects/unit/RTLO4h3/remove-last-key-removes-entry-0
def test_rtlo4h3_remove_last_key_removes_entry():
    child = InternalLiveCounter('counter:child@1000')
    parent = InternalLiveMap('map:parent@1000', ObjectsMapSemantics.LWW)
    child.parent_references = {'map:parent@1000': {'score'}}

    child.remove_parent_reference(parent, 'score')

    assert 'map:parent@1000' not in child.parent_references
    assert child.parent_references == {}


# UTS: objects/unit/RTLO4h/remove-nonexistent-key-0
def test_rtlo4h_remove_nonexistent_key():
    child = InternalLiveCounter('counter:child@1000')
    parent = InternalLiveMap('map:parent@1000', ObjectsMapSemantics.LWW)
    child.parent_references = {'map:parent@1000': {'score'}}

    child.remove_parent_reference(parent, 'nonexistent')

    assert child.parent_references['map:parent@1000'] == {'score'}


# UTS: objects/unit/RTLO4f2/root-returns-empty-path-0
def test_rtlo4f2_root_returns_empty_path():
    pool = ObjectsPool()
    root = pool['root']

    paths = root.get_full_paths()
    assert len(paths) == 1
    assert [] in paths


# UTS: objects/unit/RTLO4f/direct-child-single-path-0
def test_rtlo4f_direct_child_single_path():
    pool = ObjectsPool()
    counter = InternalLiveCounter('counter:score@1000')
    pool['counter:score@1000'] = counter

    root = pool['root']
    counter.add_parent_reference(root, 'score')

    paths = counter.get_full_paths()
    assert len(paths) == 1
    assert ['score'] in paths


# UTS: objects/unit/RTLO4f/deep-nesting-0
def test_rtlo4f_deep_nesting():
    # root --'profile'--> map:profile --'prefs'--> map:prefs --'theme_counter'--> counter:theme
    pool = ObjectsPool()
    root = pool['root']

    profile = InternalLiveMap('map:profile@1000', ObjectsMapSemantics.LWW)
    pool['map:profile@1000'] = profile
    profile.add_parent_reference(root, 'profile')

    prefs = InternalLiveMap('map:prefs@1000', ObjectsMapSemantics.LWW)
    pool['map:prefs@1000'] = prefs
    prefs.add_parent_reference(profile, 'prefs')

    theme_counter = InternalLiveCounter('counter:theme@1000')
    pool['counter:theme@1000'] = theme_counter
    theme_counter.add_parent_reference(prefs, 'theme_counter')

    paths = theme_counter.get_full_paths()
    assert len(paths) == 1
    assert ['profile', 'prefs', 'theme_counter'] in paths


# UTS: objects/unit/RTLO4f/diamond-graph-0
def test_rtlo4f_diamond_graph():
    # root --'a'--> map:A --'x'--> counter:leaf, and root --'b'--> map:B --'y'--> counter:leaf
    pool = ObjectsPool()
    root = pool['root']

    map_a = InternalLiveMap('map:a@1000', ObjectsMapSemantics.LWW)
    pool['map:a@1000'] = map_a
    map_a.add_parent_reference(root, 'a')

    map_b = InternalLiveMap('map:b@1000', ObjectsMapSemantics.LWW)
    pool['map:b@1000'] = map_b
    map_b.add_parent_reference(root, 'b')

    leaf = InternalLiveCounter('counter:leaf@1000')
    pool['counter:leaf@1000'] = leaf
    leaf.add_parent_reference(map_a, 'x')
    leaf.add_parent_reference(map_b, 'y')

    paths = leaf.get_full_paths()
    assert len(paths) == 2
    assert ['a', 'x'] in paths
    assert ['b', 'y'] in paths


# UTS: objects/unit/RTLO4f/single-parent-multiple-keys-0
def test_rtlo4f_single_parent_multiple_keys():
    pool = ObjectsPool()
    root = pool['root']

    child = InternalLiveCounter('counter:child@1000')
    pool['counter:child@1000'] = child
    child.add_parent_reference(root, 'primary')
    child.add_parent_reference(root, 'alias')

    paths = child.get_full_paths()
    assert len(paths) == 2
    assert ['primary'] in paths
    assert ['alias'] in paths


# UTS: objects/unit/RTLO4f/orphan-returns-empty-0
def test_rtlo4f_orphan_returns_empty():
    pool = ObjectsPool()

    orphan = InternalLiveCounter('counter:orphan@1000')
    pool['counter:orphan@1000'] = orphan

    paths = orphan.get_full_paths()
    assert len(paths) == 0


# UTS: objects/unit/RTLO4f/cycle-suppression-0
def test_rtlo4f_cycle_suppression():
    # root --'a'--> map:A --'b'--> map:B --'a'--> map:A, a cycle. The only simple path to
    # map:B is ['a', 'b'].
    pool = ObjectsPool()
    root = pool['root']

    map_a = InternalLiveMap('map:a@1000', ObjectsMapSemantics.LWW)
    pool['map:a@1000'] = map_a
    map_a.add_parent_reference(root, 'a')

    map_b = InternalLiveMap('map:b@1000', ObjectsMapSemantics.LWW)
    pool['map:b@1000'] = map_b
    map_b.add_parent_reference(map_a, 'b')

    # The cycle: map:A also has map:B as a parent
    map_a.add_parent_reference(map_b, 'a')

    paths_b = map_b.get_full_paths()
    assert len(paths_b) == 1
    assert ['a', 'b'] in paths_b

    paths_a = map_a.get_full_paths()
    assert len(paths_a) == 1
    assert ['a'] in paths_a


# UTS: objects/unit/RTLO4f/complex-diamond-deep-0
def test_rtlo4f_complex_diamond_deep():
    # root --'left'--> map:L --'mid'--> map:M --'target'--> counter:T, and
    # root --'right'--> map:R --'target'--> counter:T
    pool = ObjectsPool()
    root = pool['root']

    map_l = InternalLiveMap('map:l@1000', ObjectsMapSemantics.LWW)
    pool['map:l@1000'] = map_l
    map_l.add_parent_reference(root, 'left')

    map_r = InternalLiveMap('map:r@1000', ObjectsMapSemantics.LWW)
    pool['map:r@1000'] = map_r
    map_r.add_parent_reference(root, 'right')

    map_m = InternalLiveMap('map:m@1000', ObjectsMapSemantics.LWW)
    pool['map:m@1000'] = map_m
    map_m.add_parent_reference(map_l, 'mid')

    target = InternalLiveCounter('counter:t@1000')
    pool['counter:t@1000'] = target
    target.add_parent_reference(map_m, 'target')
    target.add_parent_reference(map_r, 'target')

    paths = target.get_full_paths()
    assert len(paths) == 2
    assert ['left', 'mid', 'target'] in paths
    assert ['right', 'target'] in paths


# UTS: objects/unit/RTO5c10/rebuild-from-sync-0
async def test_rto5c10_rebuild_from_sync():
    realtime_object, pool = _driven_pool()
    _process_attached(realtime_object, objects_attached_message('test', 'sync1:cursor', flags=HAS_OBJECTS))

    _process_object_sync(realtime_object, build_object_sync_message('test', 'sync1:', [
        build_object_state('root', {'aaa': 't:0'}, map={
            'semantics': LWW,
            'entries': {
                'score': {'data': {'objectId': 'counter:score@1000'}, 'timeserial': 't:0'},
                'profile': {'data': {'objectId': 'map:profile@1000'}, 'timeserial': 't:0'},
            },
        }, create_op={'mapCreate': {'semantics': LWW, 'entries': {}}}),
        build_object_state('counter:score@1000', {'aaa': 't:0'}, counter={'count': 0},
                           create_op={'counterCreate': {'count': 100}}),
        build_object_state('map:profile@1000', {'aaa': 't:0'}, map={
            'semantics': LWW,
            'entries': {
                'nested': {'data': {'objectId': 'counter:nested@1000'}, 'timeserial': 't:0'},
            },
        }, create_op={'mapCreate': {'semantics': LWW, 'entries': {}}}),
        build_object_state('counter:nested@1000', {'aaa': 't:0'}, counter={'count': 0},
                           create_op={'counterCreate': {'count': 5}}),
    ]))

    assert realtime_object._sync_state == ObjectsSyncState.SYNCED

    # counter:score@1000 is referenced by root at key 'score'
    score = pool['counter:score@1000']
    assert score.parent_references['root'] == {'score'}

    # map:profile@1000 is referenced by root at key 'profile'
    profile = pool['map:profile@1000']
    assert profile.parent_references['root'] == {'profile'}

    # counter:nested@1000 is referenced by map:profile@1000 at key 'nested'
    nested = pool['counter:nested@1000']
    assert nested.parent_references['map:profile@1000'] == {'nested'}

    # root has no parent references
    assert pool['root'].parent_references == {}

    # get_full_paths resolves through the rebuilt references
    assert ['score'] in score.get_full_paths()
    assert ['profile', 'nested'] in nested.get_full_paths()


# UTS: objects/unit/RTO5c10a/rebuild-clears-stale-refs-0
async def test_rto5c10a_rebuild_clears_stale_refs():
    realtime_object, pool = _driven_pool()

    # First sync: root --'score'--> counter:abc@1000
    _process_attached(realtime_object, objects_attached_message('test', 'sync1:cursor', flags=HAS_OBJECTS))
    _process_object_sync(realtime_object, build_object_sync_message('test', 'sync1:', [
        build_object_state('root', {'aaa': 't:0'}, map={
            'semantics': LWW,
            'entries': {
                'score': {'data': {'objectId': 'counter:abc@1000'}, 'timeserial': 't:0'},
            },
        }, create_op={'mapCreate': {'semantics': LWW, 'entries': {}}}),
        build_object_state('counter:abc@1000', {'aaa': 't:0'}, counter={'count': 0},
                           create_op={'counterCreate': {'count': 10}}),
    ]))
    assert pool['counter:abc@1000'].parent_references['root'] == {'score'}

    # Second sync: root --'points'--> counter:abc@1000, the key changed from 'score' to 'points'
    _process_attached(realtime_object, objects_attached_message('test', 'sync2:cursor', flags=HAS_OBJECTS))
    _process_object_sync(realtime_object, build_object_sync_message('test', 'sync2:', [
        build_object_state('root', {'aaa': 't:1'}, map={
            'semantics': LWW,
            'entries': {
                'points': {'data': {'objectId': 'counter:abc@1000'}, 'timeserial': 't:1'},
            },
        }, create_op={'mapCreate': {'semantics': LWW, 'entries': {}}}),
        build_object_state('counter:abc@1000', {'aaa': 't:1'}, counter={'count': 0},
                           create_op={'counterCreate': {'count': 20}}),
    ]))

    counter = pool['counter:abc@1000']

    # The 'score' reference is gone, replaced by 'points'
    assert counter.parent_references['root'] == {'points'}
    assert ['points'] in counter.get_full_paths()

    paths = counter.get_full_paths()
    assert len(paths) == 1


# UTS: objects/unit/RTO5c10/unreferenced-empty-refs-0
async def test_rto5c10_unreferenced_empty_refs():
    realtime_object, pool = _driven_pool()
    _process_attached(realtime_object, objects_attached_message('test', 'sync1:cursor', flags=HAS_OBJECTS))

    _process_object_sync(realtime_object, build_object_sync_message('test', 'sync1:', [
        build_object_state('root', {'aaa': 't:0'}, map={
            'semantics': LWW,
            'entries': {
                'name': {'data': {'string': 'Alice'}, 'timeserial': 't:0'},
            },
        }, create_op={'mapCreate': {'semantics': LWW, 'entries': {}}}),
        build_object_state('counter:orphan@1000', {'aaa': 't:0'}, counter={'count': 0},
                           create_op={'counterCreate': {'count': 42}}),
    ]))

    assert realtime_object._sync_state == ObjectsSyncState.SYNCED

    # The counter is in the pool, but no InternalLiveMap entry refers to it
    orphan = pool['counter:orphan@1000']
    assert orphan.parent_references == {}

    # get_full_paths returns no key-path for an unreferenced object
    assert len(orphan.get_full_paths()) == 0
