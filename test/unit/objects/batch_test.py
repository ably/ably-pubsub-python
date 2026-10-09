"""Batched writes: `batch()` on the typed path and instance views, and the batch contexts.

Spec points: RTPO20, RTINS17 and RTBC1-RTBC16 (ably/specification#471), with RTO26 as the
precondition a batch checks. No UTS specification covers batch, so these tests are
written against the features specification and LODR-061.

Each test drives the standard synced pool over the mock websocket, which ACKs every OBJECT
message, so a batch's writes have been applied locally (RTO20) by the time its block exits.
"""

import json
from typing import NamedTuple

import pytest

from ably.pubsub.objects.objectmessage import ObjectOperationAction
from ably.pubsub.server import (
    LiveCounter,
    LiveCounterBatchContext,
    LiveMap,
    LiveMapBatchContext,
    PrimitiveBatchContext,
)
from ably.pubsub.transport.websockettransport import ProtocolMessageAction
from ably.pubsub.types.channelmode import ChannelMode
from ably.pubsub.types.channelstate import ChannelState
from ably.pubsub.util.exceptions import AblyException
from test.uts.helpers.client import poll_until
from test.uts.helpers.clock import FakeClock, settle
from test.uts.objects.helpers.standard_test_pool import (
    HAS_OBJECTS,
    OBJECT,
    OBJECT_SUBSCRIBE_FLAG,
    build_map_set,
    build_object_message,
    remote_serial,
    setup_synced_channel,
    standard_mock_websocket,
    time_mock_http,
)

MAP_CREATE = ObjectOperationAction.MAP_CREATE
MAP_SET = ObjectOperationAction.MAP_SET
MAP_REMOVE = ObjectOperationAction.MAP_REMOVE
COUNTER_CREATE = ObjectOperationAction.COUNTER_CREATE
COUNTER_INC = ObjectOperationAction.COUNTER_INC

# The server time a test with a fake clock creates objects at
SERVER_TIME_MS = 1_700_000_123_000


async def _synced(**client_options):
    """The standard synced channel, and a list of each OBJECT ProtocolMessage the client sends on it."""
    published = []
    mock_ws = standard_mock_websocket(on_object=published.append)
    synced = await setup_synced_channel('test', mock_ws=mock_ws, **client_options)
    return synced, published


def _operations(protocol_message):
    """The wire operations of an OBJECT ProtocolMessage the client sent, in order."""
    return [object_message['operation'] for object_message in protocol_message['state']]


def _map_set(object_id, key, value):
    return {'action': MAP_SET, 'objectId': object_id, 'mapSet': {'key': key, 'value': value}}


def _counter_inc(object_id, number):
    return {'action': COUNTER_INC, 'objectId': object_id, 'counterInc': {'number': number}}


def _assert_error(excinfo, code):
    assert excinfo.value.code == code
    assert excinfo.value.status_code == 400


# --- Publishing ---------------------------------------------------------------------------

async def test_rtpo20f_batch_publishes_one_object_message():
    """RTPO20f, RTBC16d: the writes queued in a batch are published in order as one OBJECT
    ProtocolMessage, then applied locally."""
    (client, channel, root, mock_ws), published = await _synced()

    async with root.batch() as ctx:
        ctx.set('name', 'Bob')
        ctx.remove('age')
        ctx.get('score').as_live_counter().increment(5)
        ctx.get('profile').as_live_map().set('email', 'bob@example.com')

    assert len(published) == 1
    assert published[0]['action'] == OBJECT
    assert published[0]['channel'] == 'test'
    assert _operations(published[0]) == [
        _map_set('root', 'name', {'string': 'Bob'}),
        {'action': MAP_REMOVE, 'objectId': 'root', 'mapRemove': {'key': 'age'}},
        _counter_inc('counter:score@1000', 5),
        _map_set('map:profile@1000', 'email', {'string': 'bob@example.com'}),
    ]

    assert root.get('name').as_primitive().value() == 'Bob'
    assert root.get('age').exists() is False
    assert root.get('score').as_live_counter().value() == 105
    assert root.at('profile.email').as_primitive().value() == 'bob@example.com'


async def test_rtbc12e_nested_value_types_published_in_the_batch():
    """RTBC12e, RTLM20e7g: a `LiveMap` value is published as the creates it evaluates to, nested
    ones first, ahead of the MAP_SET that references it, all in the batch's one message. Their
    object ids carry the server time (RTO16), which the mock answers from the client's clock."""
    (client, channel, root, mock_ws), published = await _synced(clock=FakeClock(epoch_ms=SERVER_TIME_MS))

    async with root.batch() as ctx:
        ctx.set('team', LiveMap.create({'lead': 'Carol', 'points': LiveCounter.create(10)}))
        ctx.get('score').as_live_counter().increment(1)

    assert len(published) == 1
    counter_create, map_create, map_set, counter_inc = _operations(published[0])

    assert counter_create['action'] == COUNTER_CREATE
    assert counter_create['objectId'].startswith('counter:')
    assert counter_create['objectId'].endswith(f'@{SERVER_TIME_MS}')
    assert json.loads(counter_create['counterCreateWithObjectId']['initialValue']) == {'count': 10}

    assert map_create['action'] == MAP_CREATE
    assert map_create['objectId'].startswith('map:')
    assert map_create['objectId'].endswith(f'@{SERVER_TIME_MS}')
    assert json.loads(map_create['mapCreateWithObjectId']['initialValue'])['entries'] == {
        'lead': {'data': {'string': 'Carol'}},
        'points': {'data': {'objectId': counter_create['objectId']}},
    }

    assert map_set == _map_set('root', 'team', {'objectId': map_create['objectId']})
    assert counter_inc == _counter_inc('counter:score@1000', 1)

    assert root.get('team').instance().id == map_create['objectId']
    assert root.at('team.lead').as_primitive().value() == 'Carol'
    assert root.at('team.points').as_live_counter().value() == 10


async def test_rtbc12e_value_type_set_twice_creates_two_objects():
    """RTBC12e, RTLMV4d1: each write of a `LiveCounter` value is evaluated on its own, so one
    value set at two keys creates two counters."""
    (client, channel, root, mock_ws), published = await _synced()
    counter = LiveCounter.create(3)

    async with root.batch() as ctx:
        ctx.set('first', counter)
        ctx.set('second', counter)

    first_create, first_set, second_create, second_set = _operations(published[0])
    assert first_create['objectId'] != second_create['objectId']
    assert first_set == _map_set('root', 'first', {'objectId': first_create['objectId']})
    assert second_set == _map_set('root', 'second', {'objectId': second_create['objectId']})
    assert root.get('first').as_live_counter().value() == 3
    assert root.get('second').as_live_counter().value() == 3


async def test_rtbc16d_empty_batch_publishes_nothing():
    """RTBC16d: a batch that queues nothing publishes nothing."""
    (client, channel, root, mock_ws), published = await _synced()

    async with root.batch() as ctx:
        assert ctx.get('name').as_primitive().value() == 'Alice'

    assert published == []


async def test_rtbc16b_reads_inside_the_block_see_the_state_before_the_batch():
    """RTBC4-RTBC9, RTBC16b: the writes in a block only queue, so reads inside it resolve against
    the objects as they were, and nothing is sent until the block exits."""
    (client, channel, root, mock_ws), published = await _synced()

    async with root.batch() as ctx:
        score = ctx.get('score').as_live_counter()
        ctx.set('name', 'Bob')
        ctx.set('city', 'Paris')
        ctx.remove('age')
        score.increment(5)

        assert ctx.get('name').as_primitive().value() == 'Alice'
        assert ctx.get('city') is None
        assert ctx.get('age').as_primitive().value() == 30
        assert ctx.keys() == ['name', 'age', 'active', 'score', 'profile', 'data', 'avatar']
        assert ctx.size() == 7
        assert score.value() == 100
        assert root.get('name').as_primitive().value() == 'Alice'

        # Nothing is sent while the block runs, however long it yields to the event loop
        await settle()
        assert published == []

    assert root.get('name').as_primitive().value() == 'Bob'
    assert root.get('city').as_primitive().value() == 'Paris'
    assert root.get('age').exists() is False
    assert root.get('score').as_live_counter().value() == 105


async def test_rtpo20g_exception_in_the_block_publishes_nothing():
    """RTPO20g: an exception raised in the block propagates, nothing queued is published, and the
    batch is closed."""
    (client, channel, root, mock_ws), published = await _synced()

    with pytest.raises(ValueError, match='abandoned'):
        async with root.batch() as ctx:
            ctx.set('name', 'Bob')
            ctx.get('score').as_live_counter().increment(5)
            raise ValueError('abandoned')

    assert published == []
    assert root.get('name').as_primitive().value() == 'Alice'
    assert root.get('score').as_live_counter().value() == 100

    with pytest.raises(AblyException) as excinfo:
        ctx.keys()
    _assert_error(excinfo, 40000)


async def test_rtbc12_invalid_value_inside_a_value_type_raises_at_the_call():
    """RTBC12, RTLMV4c: a `LiveMap` value is evaluated when the batch is flushed, but its
    contents are validated when it is set, so an unsupported value inside one raises from the
    `set` call, before the server time is fetched, and queues nothing; the batch's other writes
    are published."""
    mock_http = time_mock_http()
    (client, channel, root, mock_ws), published = await _synced(mock_http=mock_http)

    async with root.batch() as ctx:
        with pytest.raises(AblyException) as excinfo:
            ctx.set('team', LiveMap.create({'lead': object()}))
        ctx.set('name', 'Bob')

    _assert_error(excinfo, 40013)
    assert len(published) == 1
    assert _operations(published[0]) == [_map_set('root', 'name', {'string': 'Bob'})]
    assert [request for request in mock_http.captured_requests if request.path == '/time'] == []


async def test_rtpo20f_batch_checks_preconditions_again_before_publishing():
    """RTPO20f, RTO26b: a block can await after its writes, so the batch checks the write
    preconditions again before publishing; a channel detached in the meantime makes the end of
    the block raise 90001, with nothing published."""
    (client, channel, root, mock_ws), published = await _synced()

    with pytest.raises(AblyException) as excinfo:
        async with root.batch() as ctx:
            ctx.set('name', 'Bob')
            await channel.detach()

    _assert_error(excinfo, 90001)
    assert published == []


async def test_rtpo20f_rejected_publish_raises_from_the_end_of_the_block():
    """RTPO20f, RTPO20g, RTO20b: when the batch's publish is rejected, the end of the block raises
    the rejection's error, nothing is applied locally, and the batch is closed."""
    published = []

    def reject(message):
        published.append(message)
        mock_ws.send_to_client({
            'action': int(ProtocolMessageAction.NACK),
            'msgSerial': message['msgSerial'],
            'count': 1,
            'error': {'code': 40160, 'statusCode': 401, 'message': 'Operation not permitted'},
        })

    mock_ws = standard_mock_websocket(auto_ack=False, on_object=reject)
    client, channel, root, mock_ws = await setup_synced_channel('test', mock_ws=mock_ws)

    with pytest.raises(AblyException) as excinfo:
        async with root.batch() as ctx:
            ctx.set('name', 'Bob')
            ctx.get('score').as_live_counter().increment(5)

    assert excinfo.value.code == 40160
    assert len(published) == 1
    assert len(_operations(published[0])) == 2
    assert root.get('name').as_primitive().value() == 'Alice'
    assert root.get('score').as_live_counter().value() == 100

    with pytest.raises(AblyException) as closed:
        ctx.keys()
    _assert_error(closed, 40000)


# --- Entering -----------------------------------------------------------------------------

@pytest.mark.parametrize('open_batch', [
    lambda root: root.get('name').as_live_map().batch(),
    lambda root: root.get('missing').as_live_map().batch(),
    lambda root: root.get('name').get('first').as_live_counter().batch(),
    lambda root: root.get('score').as_live_map().batch(),
    lambda root: root.as_live_counter().batch(),
], ids=['primitive', 'missing-key', 'below-primitive', 'counter-as-map', 'map-as-counter'])
async def test_rtpo20c_batch_on_a_path_without_the_live_object_raises(open_batch):
    """RTPO20c: entering a batch on a path that does not resolve to a live object of the view's
    type raises 92007, and publishes nothing."""
    (client, channel, root, mock_ws), published = await _synced()
    batch = open_batch(root)

    with pytest.raises(AblyException) as excinfo:
        async with batch:
            pytest.fail('the batch was entered')

    _assert_error(excinfo, 92007)
    assert published == []


async def test_rtpo20c_path_is_resolved_when_the_block_is_entered():
    """RTPO20c: a path batch resolves its path when the block is entered, not when `batch()` is
    called."""
    (client, channel, root, mock_ws), published = await _synced()
    batch = root.get('visits').as_live_counter().batch()

    await root.set('visits', LiveCounter.create(1))
    async with batch as visits:
        assert isinstance(visits, LiveCounterBatchContext)
        visits.increment(2)

    assert root.get('visits').as_live_counter().value() == 3


async def test_rtpo20b_batch_requires_publish_mode():
    """RTPO20b, RTO26a: entering a batch on a channel without the OBJECT_PUBLISH mode raises 40024."""
    mock_ws = standard_mock_websocket(attached_flags=HAS_OBJECTS | OBJECT_SUBSCRIBE_FLAG)
    client, channel, root, mock_ws = await setup_synced_channel('test', mock_ws=mock_ws,
                                                                modes=(ChannelMode.OBJECT_SUBSCRIBE,))

    with pytest.raises(AblyException) as excinfo:
        async with root.batch():
            pytest.fail('the batch was entered')

    _assert_error(excinfo, 40024)


async def test_rtpo20b_batch_requires_echo_messages():
    """RTPO20b, RTO26c: entering a batch on a client with `echo_messages` disabled raises 40000."""
    (client, channel, root, mock_ws), published = await _synced(echo_messages=False)

    with pytest.raises(AblyException) as excinfo:
        async with root.batch():
            pytest.fail('the batch was entered')

    _assert_error(excinfo, 40000)


async def test_rtpo20b_batch_checks_preconditions_before_resolving():
    """RTPO20b, RTO26b: entering a batch on a detached channel raises 90001, which is checked
    before the path is resolved."""
    (client, channel, root, mock_ws), published = await _synced()
    score = root.get('score').as_live_counter()

    await channel.detach()
    assert channel.state == ChannelState.DETACHED

    # The detach cleared the objects (RTO27a), so `score` no longer resolves: a 92007 here
    # would mean the path was resolved first
    with pytest.raises(AblyException) as excinfo:
        async with score.batch():
            pytest.fail('the batch was entered')

    _assert_error(excinfo, 90001)


async def test_rtins17b_instance_batch_checks_preconditions():
    """RTINS17b, RTO26b: entering a batch on an instance of a detached channel raises 90001."""
    (client, channel, root, mock_ws), published = await _synced()
    score = root.get('score').instance().as_live_counter()

    await channel.detach()

    with pytest.raises(AblyException) as excinfo:
        async with score.batch():
            pytest.fail('the batch was entered')

    _assert_error(excinfo, 90001)


async def test_rtpo20d_batch_can_be_entered_once():
    """RTPO20d: each `batch()` call opens one batch, so its block can only be entered once."""
    (client, channel, root, mock_ws), published = await _synced()
    batch = root.batch()

    async with batch as ctx:
        ctx.set('name', 'Bob')

    with pytest.raises(RuntimeError):
        async with batch:
            pytest.fail('the batch was entered again')

    assert len(published) == 1


# --- Instances ----------------------------------------------------------------------------

async def test_rtins17_batch_on_a_map_instance():
    """RTINS17d-RTINS17f: a batch on a map instance acts on the map it wraps, and is published as
    one message."""
    (client, channel, root, mock_ws), published = await _synced()
    profile = root.get('profile').instance().as_live_map()

    async with profile.batch() as ctx:
        assert isinstance(ctx, LiveMapBatchContext)
        assert ctx.id == 'map:profile@1000'
        ctx.set('email', 'carol@example.com')
        ctx.remove('prefs')
        ctx.get('nested_counter').as_live_counter().increment(3)

    assert len(published) == 1
    assert _operations(published[0]) == [
        _map_set('map:profile@1000', 'email', {'string': 'carol@example.com'}),
        {'action': MAP_REMOVE, 'objectId': 'map:profile@1000', 'mapRemove': {'key': 'prefs'}},
        _counter_inc('counter:nested@1000', 3),
    ]
    assert root.at('profile.email').as_primitive().value() == 'carol@example.com'
    assert root.at('profile.prefs').exists() is False
    assert root.at('profile.nested_counter').as_live_counter().value() == 8


async def test_rtins17_batch_on_a_counter_instance():
    """RTINS17d-RTINS17f: a batch on a counter instance increments the counter it wraps."""
    (client, channel, root, mock_ws), published = await _synced()
    score = root.get('score').instance().as_live_counter()

    async with score.batch() as ctx:
        assert isinstance(ctx, LiveCounterBatchContext)
        ctx.increment(10)
        ctx.decrement(4)

    assert _operations(published[0]) == [
        _counter_inc('counter:score@1000', 10),
        _counter_inc('counter:score@1000', -4),
    ]
    assert score.value() == 106


async def test_rtins17d_instance_batch_follows_the_object_not_the_path():
    """RTINS17d, RTPO20c: an instance batch acts on the object the instance wraps wherever it
    sits, while a path batch acts on what the path resolves to when it is entered."""
    (client, channel, root, mock_ws), published = await _synced()
    profile = root.get('profile').instance().as_live_map()

    await root.remove('profile')

    with pytest.raises(AblyException) as excinfo:
        async with root.get('profile').as_live_map().batch():
            pytest.fail('the path batch was entered')
    _assert_error(excinfo, 92007)

    async with profile.batch() as ctx:
        ctx.set('email', 'dana@example.com')

    assert _operations(published[-1]) == [_map_set('map:profile@1000', 'email', {'string': 'dana@example.com'})]
    assert profile.get('email').as_primitive().value() == 'dana@example.com'


# --- Counter contexts ---------------------------------------------------------------------

async def test_rtbc14_rtbc15_counter_batch_increments_and_decrements():
    """RTBC14, RTBC15: a counter context queues a COUNTER_INC for each increment, and one of the
    negated amount for each decrement, the amount defaulting to 1."""
    (client, channel, root, mock_ws), published = await _synced()

    async with root.get('score').as_live_counter().batch() as score:
        assert isinstance(score, LiveCounterBatchContext)
        score.increment(5)
        score.decrement(2)
        score.increment()
        score.decrement()
        score.increment(0.5)
        assert score.value() == 100

    assert len(published) == 1
    assert _operations(published[0]) == [
        _counter_inc('counter:score@1000', number) for number in (5, -2, 1, -1, 0.5)
    ]
    assert root.get('score').as_live_counter().value() == 103.5


@pytest.mark.parametrize('write, code', [
    (lambda ctx, score: ctx.set(1, 'value'), 40003),
    (lambda ctx, score: ctx.set('key', object()), 40013),
    (lambda ctx, score: ctx.set('key', None), 40013),
    (lambda ctx, score: ctx.set('key', float('nan')), 40013),
    (lambda ctx, score: ctx.remove(None), 40003),
    (lambda ctx, score: score.increment('5'), 40003),
    (lambda ctx, score: score.increment(None), 40003),
    (lambda ctx, score: score.increment(float('inf')), 40003),
    (lambda ctx, score: score.decrement(True), 40003),
], ids=['key-not-str', 'value-object', 'value-none', 'value-nan', 'remove-key-none', 'amount-str',
        'amount-none', 'amount-inf', 'amount-bool'])
async def test_rtbc12_rtbc15_invalid_arguments_raise_at_the_call(write, code):
    """RTBC12-RTBC15, RTLM20e1, RTLM21e1, RTLC12e1: a write with an invalid key, value or amount
    raises where it is called, and queues nothing."""
    (client, channel, root, mock_ws), published = await _synced()

    async with root.batch() as ctx:
        with pytest.raises(AblyException) as excinfo:
            write(ctx, ctx.get('score').as_live_counter())
        _assert_error(excinfo, code)
        ctx.set('name', 'Bob')

    assert _operations(published[0]) == [_map_set('root', 'name', {'string': 'Bob'})]


# --- Reads and views ----------------------------------------------------------------------

async def test_rtbc3_rtbc4_id_and_get():
    """RTBC3, RTBC4: `id` is the wrapped object's id, None for a primitive; `get` wraps the value
    at a key in the context of its type, and is None for a key with no value or on anything but
    a map."""
    (client, channel, root, mock_ws), published = await _synced()

    async with root.batch() as ctx:
        assert ctx.id == 'root'
        profile, score, name = ctx.get('profile'), ctx.get('score'), ctx.get('name')
        assert isinstance(profile, LiveMapBatchContext)
        assert isinstance(score, LiveCounterBatchContext)
        assert isinstance(name, PrimitiveBatchContext)
        assert profile.id == 'map:profile@1000'
        assert score.id == 'counter:score@1000'
        assert name.id is None

        assert ctx.get('missing') is None
        assert name.get('first') is None
        assert score.get('first') is None

        with pytest.raises(AblyException) as excinfo:
            ctx.get(1)
        _assert_error(excinfo, 40003)


async def test_rtbc5_value():
    """RTBC5: a counter context's value is the count; a primitive context's is the primitive,
    filtered by `expected` as `PrimitiveInstance.value` filters it."""
    (client, channel, root, mock_ws), published = await _synced()

    async with root.batch() as ctx:
        assert ctx.get('score').as_live_counter().value() == 100
        assert ctx.get('name').as_primitive().value() == 'Alice'
        assert ctx.get('name').as_primitive().value(str) == 'Alice'
        assert ctx.get('name').as_primitive().value(float) is None
        assert ctx.get('active').as_primitive().value(bool) is True
        assert ctx.get('active').as_primitive().value(float) is None
        assert ctx.get('avatar').as_primitive().value(bytes) == b'\x01\x02\x03'
        assert ctx.get('data').as_primitive().value(dict) == {'tags': ['a', 'b']}

        age = ctx.get('age').as_primitive().value(float)
        assert age == 30
        assert type(age) is float

        with pytest.raises(TypeError):
            ctx.get('age').as_primitive().value(int)


async def test_rtbc6_rtbc9_map_enumeration():
    """RTBC6-RTBC9: a map context's entries and values are contexts of each entry's type, its keys
    and size those of the map."""
    (client, channel, root, mock_ws), published = await _synced()

    async with root.get('profile').as_live_map().batch() as profile:
        entries = profile.entries()
        assert [key for key, _ in entries] == ['email', 'nested_counter', 'prefs']
        assert [type(context) for _, context in entries] == [
            PrimitiveBatchContext, LiveCounterBatchContext, LiveMapBatchContext]
        values = profile.values()
        assert [type(context) for context in values] == [type(context) for _, context in entries]
        # A live object has one context per batch (RTBC16c); a primitive gets a new one each time
        assert values[1:] == [context for _, context in entries[1:]]
        assert values[0].value() == 'alice@example.com'
        assert profile.keys() == ['email', 'nested_counter', 'prefs']
        assert profile.size() == 3
        assert entries[1][1].value() == 5
        assert entries[2][1].get('theme').as_primitive().value() == 'dark'


async def test_rtbc10_rtbc11_compact():
    """RTBC10, RTBC11: `compact` and `compact_json` snapshot the wrapped value as `Instance` does."""
    (client, channel, root, mock_ws), published = await _synced()

    async with root.batch() as ctx:
        assert ctx.get('profile').compact() == {
            'email': 'alice@example.com', 'nested_counter': 5, 'prefs': {'theme': 'dark'}}
        assert ctx.compact()['avatar'] == b'\x01\x02\x03'
        assert ctx.compact_json()['avatar'] == 'AQID'
        assert ctx.get('score').compact_json() == 100


async def test_rtbc1a_view_helpers_are_checked():
    """RTBC1a, RTTS9d: a context's view helpers return the context itself for the type it wraps,
    and raise 92007 for any other."""
    (client, channel, root, mock_ws), published = await _synced()

    async with root.batch() as ctx:
        score, name = ctx.get('score'), ctx.get('name')
        assert ctx.as_live_map() is ctx
        assert score.as_live_counter() is score
        assert name.as_primitive() is name

        for view_helper in (ctx.as_live_counter, ctx.as_primitive, score.as_live_map, score.as_primitive,
                            name.as_live_map, name.as_live_counter):
            with pytest.raises(AblyException) as excinfo:
                view_helper()
            _assert_error(excinfo, 92007)

    assert published == []


async def test_rtbc16c_one_context_per_object():
    """RTBC16c: a batch wraps each object in one context however it is reached, the object the
    batch was opened on included."""
    (client, channel, root, mock_ws), published = await _synced()
    # A reference from `profile.prefs` back to the root, so that the root is reachable from inside
    mock_ws.send_to_client(build_object_message('test', [
        build_map_set('map:prefs@1000', 'home', {'objectId': 'root'}, remote_serial(0), 'remote'),
    ]))
    await poll_until(lambda: 'home' in root.at('profile.prefs').as_live_map().keys(),
                     description='the back reference to be applied')

    async with root.batch() as ctx:
        profile = ctx.get('profile')
        assert ctx.get('profile') is profile
        assert dict(ctx.entries())['profile'] is profile
        assert ctx.get('score') is ctx.get('score')
        assert profile.get('prefs').get('home') is ctx


class _Contexts(NamedTuple):
    root: LiveMapBatchContext
    profile: LiveMapBatchContext
    score: LiveCounterBatchContext
    name: PrimitiveBatchContext


# A call of each context method that reads the objects, and of each that writes
_READS = {
    'get': lambda c: c.root.get('name'),
    'compact': lambda c: c.root.compact(),
    'compact_json': lambda c: c.root.compact_json(),
    'entries': lambda c: c.root.entries(),
    'keys': lambda c: c.root.keys(),
    'values': lambda c: c.root.values(),
    'size': lambda c: c.root.size(),
    'child-get': lambda c: c.profile.get('email'),
    'counter-value': lambda c: c.score.value(),
    'primitive-value': lambda c: c.name.value(),
}
_WRITES = {
    'set': lambda c: c.root.set('name', 'Bob'),
    'set-value-type': lambda c: c.root.set('team', LiveMap.create()),
    'remove': lambda c: c.root.remove('name'),
    'child-set': lambda c: c.profile.set('email', 'bob@example.com'),
    'increment': lambda c: c.score.increment(1),
    'decrement': lambda c: c.score.decrement(1),
}
# The calls that check whether the batch is open, but no channel preconditions
_VIEWS = {
    'id': lambda c: c.root.id,
    'primitive-id': lambda c: c.name.id,
    'as_live_map': lambda c: c.root.as_live_map(),
    'as_live_counter': lambda c: c.score.as_live_counter(),
    'as_primitive': lambda c: c.name.as_primitive(),
}


def _contexts(ctx):
    return _Contexts(ctx, ctx.get('profile'), ctx.get('score'), ctx.get('name'))


@pytest.mark.parametrize('call', [*_READS.values(), *_WRITES.values()], ids=[*_READS, *_WRITES])
async def test_rtbc4b_rtbc15b_contexts_check_preconditions_on_each_call(call):
    """RTBC4b-RTBC15b: the contexts check the channel preconditions on every read (RTO25) and
    write (RTO26), so once the channel detaches inside the block each of them raises 90001, and
    nothing is published."""
    (client, channel, root, mock_ws), published = await _synced()

    async with root.batch() as ctx:
        contexts = _contexts(ctx)
        await channel.detach()

        with pytest.raises(AblyException) as excinfo:
            call(contexts)
        _assert_error(excinfo, 90001)

    assert published == []


@pytest.mark.parametrize('call', [*_VIEWS.values(), *_READS.values(), *_WRITES.values()],
                         ids=[*_VIEWS, *_READS, *_WRITES])
async def test_rtbc16e_contexts_raise_once_the_batch_has_closed(call):
    """RTBC16e, RTBC3b-RTBC15c: once its block has exited, every method of a batch's contexts,
    those opened inside the block included, raises 40000."""
    (client, channel, root, mock_ws), published = await _synced()

    async with root.batch() as ctx:
        contexts = _contexts(ctx)

    with pytest.raises(AblyException) as excinfo:
        call(contexts)
    _assert_error(excinfo, 40000)
