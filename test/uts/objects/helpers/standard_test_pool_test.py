"""Tests for the `standard_test_pool` helper and the object wire types it builds on.

These are not derived from a specification. They pin the builders to the wire shapes
`standard_test_pool.md` describes, the canonical serials to the ordering the
specifications rely on, the wire types to a lossless round trip on both protocols, and
the mock to the synced-channel conversation, which it can hold before any LiveObjects
behaviour exists.
"""

import json

import msgpack

from ably.pubsub.objects import publicmessage
from ably.pubsub.objects.objectmessage import (
    WIRE_FORMAT_MSGPACK,
    CounterCreate,
    MapCreate,
    MapCreateWithObjectId,
    ObjectData,
    ObjectMessage,
    ObjectOperation,
    ObjectOperationAction,
    ObjectsMapSemantics,
)
from ably.pubsub.objects.realtimeobject import RealtimeObject
from ably.pubsub.realtime.connection import ConnectionState
from ably.pubsub.types.channelmode import ChannelMode, decode_channel_mode
from ably.pubsub.types.channelstate import ChannelState
from test.uts.helpers.client import await_channel_state, await_connection_state, poll_until, rest_client
from test.uts.helpers.clock import settle
from test.uts.helpers.mock_http import MockHttpClient
from test.uts.helpers.mock_websocket import MockEventType
from test.uts.objects.helpers.standard_test_pool import (
    GC_GRACE_PERIOD,
    HAS_OBJECTS,
    LWW,
    OBJECT_SUBSCRIBE_FLAG,
    OBJECT_SYNC,
    POOL_SERIAL,
    SITE_CODE,
    STANDARD_POOL_OBJECTS,
    ack_serial,
    assert_unchanged_after_quiescence,
    below_ack_serial,
    build_ack_message,
    build_counter_inc,
    build_map_remove,
    build_map_set,
    build_object_delete,
    build_object_message,
    build_object_state,
    build_object_sync_message,
    build_public_object_message,
    bytes_value,
    capture_updates,
    json_value,
    object_message,
    object_messages,
    objects_channel_options,
    objects_client,
    provision_objects_via_rest,
    remote_serial,
    standard_mock_websocket,
)


def msgpack_round_trip(message):
    """`message` encoded for the msgpack wire, sent through msgpack and decoded again."""
    raw = msgpack.packb(message.to_dict(WIRE_FORMAT_MSGPACK), use_bin_type=True)
    return ObjectMessage.from_dict(msgpack.unpackb(raw, raw=False), WIRE_FORMAT_MSGPACK)


def test_serials_sort_as_the_specification_requires():
    assert ack_serial(0, 0) == 't:1:0'
    assert remote_serial(0) == 't:1'
    assert below_ack_serial(9) == 't:0:9'
    # A remote write and the first ACK both beat the pool, and the probe sits between them
    assert POOL_SERIAL < below_ack_serial(9) < ack_serial(0, 0)
    assert remote_serial(0) > POOL_SERIAL


def test_operation_builders_produce_the_json_wire_shape():
    assert build_counter_inc('counter:a@1', 5, '01', 'site1') == {
        'serial': '01', 'siteCode': 'site1',
        'operation': {'action': 4, 'objectId': 'counter:a@1', 'counterInc': {'number': 5}},
    }
    assert build_map_set('root', 'k', {'string': 'v'}, '02', 'site1')['operation'] == {
        'action': 1, 'objectId': 'root', 'mapSet': {'key': 'k', 'value': {'string': 'v'}},
    }
    assert 'serialTimestamp' not in build_map_remove('root', 'k', '03', 'site1')
    assert build_object_delete('counter:a@1', '04', 'site1', 1700000000000)['serialTimestamp'] == 1700000000000


def test_protocol_message_builders():
    sync = build_object_sync_message('test', 'sync1:', STANDARD_POOL_OBJECTS)
    assert sync['action'] == OBJECT_SYNC
    assert sync['channelSerial'] == 'sync1:'
    assert len(sync['state']) == 5
    # RTO5a5: a sync with no channelSerial carries no key at all
    assert 'channelSerial' not in build_object_sync_message('test', None, [])
    assert build_object_message('test', [])['action'] == 19
    assert build_ack_message(3, ['a', None]) == {'action': 1, 'msgSerial': 3, 'count': 1,
                                                 'res': [{'serials': ['a', None]}]}


def test_object_state_builder_fills_in_the_create_op():
    counter = build_object_state('counter:a@1', {'s': '1'}, counter={'count': 0},
                                 create_op={'counterCreate': {'count': 7}})
    assert counter['object']['createOp'] == {'counterCreate': {'count': 7}, 'objectId': 'counter:a@1',
                                             'action': int(ObjectOperationAction.COUNTER_CREATE)}
    a_map = build_object_state('map:a@1', {}, map={'semantics': LWW, 'entries': {}},
                               create_op={'mapCreate': {'semantics': LWW, 'entries': {}}}, tombstone=True)
    assert a_map['object']['createOp']['action'] == int(ObjectOperationAction.MAP_CREATE)
    assert a_map['object']['tombstone'] is True
    assert 'tombstone' not in counter['object']


def test_standard_pool_decodes_to_the_specified_tree():
    root, score, profile, nested, prefs = (object_message(message).object for message in STANDARD_POOL_OBJECTS)

    assert root.object_id == 'root'
    assert root.site_timeserials == {'aaa': POOL_SERIAL}
    assert root.map.semantics is ObjectsMapSemantics.LWW
    entries = root.map.entries
    assert entries['name'].data == ObjectData(string='Alice')
    assert entries['age'].data == ObjectData(number=30.0)
    assert entries['active'].data == ObjectData(boolean=True)
    assert entries['score'].data == ObjectData(object_id='counter:score@1000')
    assert entries['data'].data.json == {'tags': ['a', 'b']}
    assert entries['avatar'].data.bytes == bytes([1, 2, 3])
    assert all(entry.timeserial == POOL_SERIAL and not entry.tombstone for entry in entries.values())
    assert root.create_op.action is ObjectOperationAction.MAP_CREATE
    assert root.create_op.object_id == 'root'

    assert score.counter.count == 0
    assert score.create_op.counter_create == CounterCreate(count=100.0)
    assert nested.create_op.counter_create.count == 5
    assert set(profile.map.entries) == {'email', 'nested_counter', 'prefs'}
    assert prefs.map.entries['theme'].data.string == 'dark'


def test_values_carry_json_and_binary_as_the_json_wire_does():
    assert json_value({'a': [1]}) == {'json': '{"a": [1]}'}
    assert bytes_value(bytes([1, 2, 3])) == {'bytes': 'AQID'}
    data = ObjectData.from_dict({'json': '{"a": [1]}'})
    assert data.json == {'a': [1]}
    assert data.to_dict() == {'json': '{"a":[1]}'}


def test_wire_types_round_trip_through_json():
    for wire in [*STANDARD_POOL_OBJECTS, build_counter_inc('counter:a@1', 5, '01', 'site1'),
                 build_map_set('root', 'k', bytes_value(b'\x00\xff'), '02', 'site1'),
                 build_map_remove('root', 'k', '03', 'site1', 1700000000000)]:
        decoded = object_message(wire)
        assert object_message(json.loads(json.dumps(decoded.to_dict()))) == decoded


def test_wire_types_round_trip_through_msgpack():
    for wire in [*STANDARD_POOL_OBJECTS, build_map_set('root', 'k', bytes_value(b'\x00\xff'), '02', 'site1')]:
        decoded = object_message(wire)
        assert msgpack_round_trip(decoded) == decoded
    # Binary is raw on the msgpack wire and base64 on the JSON one (OD2d)
    avatar = object_message(STANDARD_POOL_OBJECTS[0]).object.map.entries['avatar'].data
    assert avatar.to_dict(WIRE_FORMAT_MSGPACK) == {'bytes': bytes([1, 2, 3])}
    assert avatar.to_dict() == {'bytes': 'AQID'}


def test_local_only_fields_are_never_encoded():
    derived = MapCreate(semantics=ObjectsMapSemantics.LWW, entries={})
    operation = ObjectOperation(
        action=ObjectOperationAction.MAP_CREATE, object_id='map:a@1',
        map_create_with_object_id=MapCreateWithObjectId(initial_value='{}', nonce='n' * 16, derived_from=derived))
    assert operation.to_dict() == {
        'action': 0, 'objectId': 'map:a@1', 'mapCreateWithObjectId': {'initialValue': '{}', 'nonce': 'n' * 16},
    }
    assert operation.resolved_map_create is derived
    entry = object_message(STANDARD_POOL_OBJECTS[0]).object.map.entries['name']
    entry.tombstoned_at = 1700000000000
    assert 'tombstonedAt' not in json.dumps(entry.to_dict())


def test_unknown_action_decodes_without_failing():
    message = object_message({'serial': '01', 'siteCode': 's', 'operation': {'action': 99, 'objectId': 'x'}})
    assert message.operation.action is ObjectOperationAction.UNKNOWN


def test_object_messages_take_identity_from_the_protocol_message():
    protocol_message = build_object_message('test', [build_counter_inc('counter:a@1', 1, '01', 's'),
                                                     build_counter_inc('counter:a@1', 2, '02', 's')])
    protocol_message.update(id='pm-id', connectionId='conn-x', timestamp=1234)
    first, second = object_messages(protocol_message)
    assert (first.id, second.id) == ('pm-id:0', 'pm-id:1')
    assert first.connection_id == 'conn-x'
    assert second.timestamp == 1234


def test_public_object_message_follows_paom3():
    wire = build_counter_inc('counter:score@1000', 42, 'serial-1', 'site-a')
    wire['clientId'] = 'client-1'
    public = build_public_object_message(wire, 'test')
    assert isinstance(public, publicmessage.ObjectMessage)
    assert public.channel == 'test'
    assert public.serial == 'serial-1'
    assert public.site_code == 'site-a'
    assert public.client_id == 'client-1'
    assert public.operation.action is ObjectOperationAction.COUNTER_INC
    assert public.operation.counter_inc.number == 42
    assert public.operation.map_create is None


def test_capture_updates_records_and_delegates():
    delivered = []

    class Recorder:
        def notify_updated(self, update):
            delivered.append(update)

    recorder = Recorder()
    updates = capture_updates(recorder)
    recorder.notify_updated('first')
    recorder.notify_updated('second')
    assert updates == ['first', 'second']
    assert delivered == ['first', 'second']


async def test_quiescence_passes_when_only_the_control_moves():
    under_test = []
    control = ['delivered']
    await assert_unchanged_after_quiescence(lambda: len(under_test), lambda: len(control) >= 1)


async def test_standard_mock_holds_the_synced_channel_conversation():
    mock_ws = standard_mock_websocket()
    client = objects_client(mock_ws)
    await await_connection_state(client, ConnectionState.CONNECTED)

    details = client.connection.connection_details
    assert details.site_code == SITE_CODE
    assert details.objects_gc_grace_period == GC_GRACE_PERIOD

    channel = client.channels.get('test', objects_channel_options())
    await channel.attach()
    await poll_until(lambda: any(event.data.get('action') == OBJECT_SYNC
                                 for event in mock_ws.events_of_type(MockEventType.MESSAGE_TO_CLIENT)),
                     description='the OBJECT_SYNC to follow the ATTACHED')
    attach = next(m for m in mock_ws.messages_from_client if m.get('channel') == 'test')
    assert decode_channel_mode(attach['flags']) == [ChannelMode.OBJECT_SUBSCRIBE, ChannelMode.OBJECT_PUBLISH]

    await channel.detach()
    await await_channel_state(channel, ChannelState.DETACHED)


async def test_granted_modes_decode_from_the_attached_flags():
    mock_ws = standard_mock_websocket(attached_flags=HAS_OBJECTS | OBJECT_SUBSCRIBE_FLAG, sync_objects=None)
    client = objects_client(mock_ws)
    channel = client.channels.get('test', objects_channel_options())
    await channel.attach()
    assert channel.modes == [ChannelMode.OBJECT_SUBSCRIBE]
    await settle()
    assert not any(event.data.get('action') == OBJECT_SYNC
                   for event in mock_ws.events_of_type(MockEventType.MESSAGE_TO_CLIENT))


async def test_each_channel_has_one_realtime_object():
    client = objects_client(standard_mock_websocket(), auto_connect=False)
    channel = client.channels.get('test')
    assert isinstance(channel.object, RealtimeObject)
    assert channel.object is channel.object
    assert channel.object._channel is channel
    assert 'root' in channel.object._objects_pool


async def test_provisioning_posts_operations_and_flattens_object_ids():
    captured = []

    def on_request(request):
        captured.append(request)
        request.respond_with(201, [{'objectIds': ['root', 'counter:a@1']}, {'objectIds': ['map:b@2']}])

    mock_http = MockHttpClient(on_connection_attempt=lambda conn: conn.respond_with_success(),
                               on_request=on_request)
    client = rest_client(mock_http, use_binary_protocol=False)
    operations = [{'mapSet': {'key': 'k', 'value': {'string': 'v'}}, 'objectId': 'root'},
                  {'counterCreate': {'count': 1}}]

    object_ids = await provision_objects_via_rest(None, 'a channel:1', operations, client=client)

    assert object_ids == ['root', 'counter:a@1', 'map:b@2']
    assert captured[0].method == 'POST'
    assert captured[0].url.raw_path == '/channels/a%20channel%3A1/object'
    assert json.loads(captured[0].body) == operations
