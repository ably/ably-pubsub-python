"""The fixtures every LiveObjects specification shares.

Derived from uts/objects/helpers/standard_test_pool.md in ably/specification: the
standard pool of objects, the canonical serials, the ObjectMessage and ProtocolMessage
builders, the synced-channel setup the mock-backed specifications open with, the
negative-assertion quiescence pattern, and REST provisioning for the integration tier.

Every builder returns the JSON-wire dictionary the specification describes, ready for
`mock_ws.send_to_client(...)`: camelCase keys, numeric operation actions and map
semantics, `json` values as JSON-encoded strings and `bytes` values as base64 strings.
The specifications write actions and semantics by name; here they are the numbers the
wire carries, so pass `LWW` where a specification writes `semantics: "LWW"`. Templates
shared at module level (`STANDARD_POOL_OBJECTS`) must not be mutated; build a variant
instead. A test that drives the msgpack wire converts a dictionary first with
`ObjectMessage.from_dict(d).to_dict('msgpack')`.

The pure unit specifications construct internal objects rather than wire messages;
`object_message()` and `object_messages()` decode a builder's output into the internal
`ObjectMessage` they take, and `capture_updates()` records the updates an object emits,
since `apply_operation` returns whether it applied rather than the update itself.
"""

import base64
import copy
import json
from typing import NamedTuple
from urllib.parse import quote

from ably.pubsub.objects import publicmessage
from ably.pubsub.objects.objectmessage import (
    WIRE_FORMAT_JSON,
    ObjectMessage,
    ObjectOperationAction,
    ObjectsMapSemantics,
)
from ably.pubsub.transport.websockettransport import ProtocolMessageAction
from ably.pubsub.types.channelmode import ChannelMode
from ably.pubsub.types.channeloptions import ChannelOptions
from ably.pubsub.types.flags import Flag
from ably.pubsub.util.clock import Clock
from test.uts.helpers.client import poll_until, realtime_client, sandbox_rest_client
from test.uts.helpers.clock import settle
from test.uts.helpers.mock_http import MockHttpClient
from test.uts.helpers.mock_websocket import MockWebSocket

# --- Canonical constants ---------------------------------------------------------------

# The siteCode of the harness connection, under which the client applies its own
# operations on ACK
SITE_CODE = 'test-site'

# The timeserial every standard-pool object and entry is seeded with. Serials compare
# lexicographically (RTLM9e), so every synthetic serial below is defined relative to it.
POOL_SERIAL = 't:0'

CONNECTION_ID = 'conn-1'
CONNECTION_KEY = 'conn-key-1'

# RTO10b3's default, which the harness CONNECTED message states explicitly
GC_GRACE_PERIOD = 86400000

# The wire values the specifications write by name
HAS_OBJECTS = int(Flag.HAS_OBJECTS)
OBJECT_SUBSCRIBE_FLAG = int(Flag.OBJECT_SUBSCRIBE)
OBJECT_PUBLISH_FLAG = int(Flag.OBJECT_PUBLISH)
LWW = int(ObjectsMapSemantics.LWW)

ACK = int(ProtocolMessageAction.ACK)
ATTACH = int(ProtocolMessageAction.ATTACH)
ATTACHED = int(ProtocolMessageAction.ATTACHED)
CONNECTED = int(ProtocolMessageAction.CONNECTED)
DETACH = int(ProtocolMessageAction.DETACH)
DETACHED = int(ProtocolMessageAction.DETACHED)
ERROR = int(ProtocolMessageAction.ERROR)
OBJECT = int(ProtocolMessageAction.OBJECT)
OBJECT_SYNC = int(ProtocolMessageAction.OBJECT_SYNC)

# The modes every standard channel requests
OBJECTS_MODES = (ChannelMode.OBJECT_SUBSCRIBE, ChannelMode.OBJECT_PUBLISH)

# The X-Ably-Version the objects REST endpoint is called with: protocol v6, whose
# operation payloads (`mapSet`, `counterInc` and the rest) are what the specification's
# provisioning operations are written in
OBJECTS_REST_API_VERSION = '6'


# --- Serials ----------------------------------------------------------------------------

def ack_serial(msg_serial, index):
    """The serial the harness ACKs operation `index` of the publish `msg_serial` with.

    The first publish's first operation is `ack_serial(0, 0) == 't:1:0'`, which sorts after
    `POOL_SERIAL`. These serials are recorded in appliedOnAckSerials (RTO9a2a4) and an echo
    carrying one is discarded (RTO9a3), so never reuse one as an inbound serial meant to apply.
    """
    return f't:{msg_serial + 1}:{index}'


def remote_serial(index):
    """A serial for a remote MAP_SET or MAP_REMOVE that wins LWW against a pool entry.

    0-based: `remote_serial(0) == 't:1'`. A bare number such as `'99'` sorts before `'t:0'`
    and would be rejected as stale.
    """
    return f't:{index + 1}'


def below_ack_serial(index):
    """A serial that is not an ACK serial, sorting after `POOL_SERIAL` but before `ack_serial(0, 0)`.

    0-based: `below_ack_serial(9) == 't:0:9'`.
    """
    return f't:0:{index}'


# --- Values -----------------------------------------------------------------------------

def json_value(value):
    """An `ObjectData` wire dictionary carrying `value` as JSON (OD2g)."""
    return {'json': json.dumps(value)}


def bytes_value(value):
    """An `ObjectData` wire dictionary carrying `value` as binary (OD2d)."""
    return {'bytes': base64.b64encode(value).decode('ascii')}


# --- ProtocolMessage builders -----------------------------------------------------------

def build_object_sync_message(channel, channel_serial, object_messages):
    """An OBJECT_SYNC ProtocolMessage. A `channel_serial` of None leaves it out (RTO5a5)."""
    message = {'action': OBJECT_SYNC, 'channel': channel, 'state': list(object_messages)}
    if channel_serial is not None:
        message['channelSerial'] = channel_serial
    return message


def build_object_message(channel, object_messages):
    """An OBJECT ProtocolMessage."""
    return {'action': OBJECT, 'channel': channel, 'state': list(object_messages)}


def build_ack_message(msg_serial, serials):
    """An ACK for one ProtocolMessage, carrying a `PublishResult` with `serials` (TR4s)."""
    return {'action': ACK, 'msgSerial': msg_serial, 'count': 1, 'res': [{'serials': list(serials)}]}


# --- ObjectMessage builders: operations -------------------------------------------------

def _operation_message(serial, site_code, operation, serial_timestamp=None):
    message = {'serial': serial, 'siteCode': site_code, 'operation': operation}
    if serial_timestamp is not None:
        message['serialTimestamp'] = serial_timestamp
    return message


def build_counter_inc(object_id, number, serial, site_code):
    return _operation_message(serial, site_code, {
        'action': int(ObjectOperationAction.COUNTER_INC),
        'objectId': object_id,
        'counterInc': {'number': number},
    })


def build_map_set(object_id, key, value, serial, site_code):
    """A MAP_SET; `value` is an `ObjectData` wire dictionary, such as `{'string': 'Bob'}`."""
    return _operation_message(serial, site_code, {
        'action': int(ObjectOperationAction.MAP_SET),
        'objectId': object_id,
        'mapSet': {'key': key, 'value': value},
    })


def build_map_remove(object_id, key, serial, site_code, serial_timestamp=None):
    return _operation_message(serial, site_code, {
        'action': int(ObjectOperationAction.MAP_REMOVE),
        'objectId': object_id,
        'mapRemove': {'key': key},
    }, serial_timestamp)


def build_map_clear(object_id, serial, site_code):
    return _operation_message(serial, site_code, {
        'action': int(ObjectOperationAction.MAP_CLEAR),
        'objectId': object_id,
    })


def build_object_delete(object_id, serial, site_code, serial_timestamp=None):
    return _operation_message(serial, site_code, {
        'action': int(ObjectOperationAction.OBJECT_DELETE),
        'objectId': object_id,
    }, serial_timestamp)


def build_counter_create(object_id, counter_create, serial, site_code):
    """A COUNTER_CREATE; `counter_create` is the wire payload, such as `{'count': 42}`."""
    return _operation_message(serial, site_code, {
        'action': int(ObjectOperationAction.COUNTER_CREATE),
        'objectId': object_id,
        'counterCreate': counter_create,
    })


def build_map_create(object_id, map_create, serial, site_code):
    """A MAP_CREATE; `map_create` is the wire payload, `{'semantics': LWW, 'entries': {...}}`."""
    return _operation_message(serial, site_code, {
        'action': int(ObjectOperationAction.MAP_CREATE),
        'objectId': object_id,
        'mapCreate': map_create,
    })


# --- ObjectMessage builders: state ------------------------------------------------------

def build_object_state(object_id, site_timeserials, map=None, counter=None, tombstone=None, create_op=None):
    """An OBJECT_SYNC ObjectMessage wrapping an `ObjectState`.

    `map`, `counter`, `tombstone` and `create_op` are the specification's `opts`, as wire
    dictionaries. A terse `create_op` such as `{'counterCreate': {...}}` has its mandatory
    `objectId` and `action` filled in (OOP2), as the specification's builder does.
    """
    state = {'objectId': object_id, 'siteTimeserials': dict(site_timeserials)}
    if map is not None:
        state['map'] = map
    if counter is not None:
        state['counter'] = counter
    if tombstone is not None:
        state['tombstone'] = tombstone
    if create_op is not None:
        create_op = dict(create_op)
        create_op.setdefault('objectId', object_id)
        if 'action' not in create_op:
            create_op['action'] = int(ObjectOperationAction.COUNTER_CREATE if 'counterCreate' in create_op
                                      else ObjectOperationAction.MAP_CREATE)
        state['createOp'] = create_op
    return {'object': state}


def build_object_message_with_state(object_state):
    """An ObjectMessage wrapping an existing `ObjectState` wire dictionary."""
    return {'object': object_state}


# The standard tree. Counters carry their value in the create operation, with
# `counter.count` 0, so that applying the state yields 100 and 5 rather than double that.
STANDARD_POOL_OBJECTS = (
    build_object_state('root', {'aaa': POOL_SERIAL}, map={
        'semantics': LWW,
        'entries': {
            'name': {'data': {'string': 'Alice'}, 'timeserial': POOL_SERIAL},
            'age': {'data': {'number': 30}, 'timeserial': POOL_SERIAL},
            'active': {'data': {'boolean': True}, 'timeserial': POOL_SERIAL},
            'score': {'data': {'objectId': 'counter:score@1000'}, 'timeserial': POOL_SERIAL},
            'profile': {'data': {'objectId': 'map:profile@1000'}, 'timeserial': POOL_SERIAL},
            'data': {'data': json_value({'tags': ['a', 'b']}), 'timeserial': POOL_SERIAL},
            'avatar': {'data': {'bytes': 'AQID'}, 'timeserial': POOL_SERIAL},
        },
    }, create_op={'mapCreate': {'semantics': LWW, 'entries': {}}}),
    build_object_state('counter:score@1000', {'aaa': POOL_SERIAL}, counter={'count': 0},
                       create_op={'counterCreate': {'count': 100}}),
    build_object_state('map:profile@1000', {'aaa': POOL_SERIAL}, map={
        'semantics': LWW,
        'entries': {
            'email': {'data': {'string': 'alice@example.com'}, 'timeserial': POOL_SERIAL},
            'nested_counter': {'data': {'objectId': 'counter:nested@1000'}, 'timeserial': POOL_SERIAL},
            'prefs': {'data': {'objectId': 'map:prefs@1000'}, 'timeserial': POOL_SERIAL},
        },
    }, create_op={'mapCreate': {'semantics': LWW, 'entries': {}}}),
    build_object_state('counter:nested@1000', {'aaa': POOL_SERIAL}, counter={'count': 0},
                       create_op={'counterCreate': {'count': 5}}),
    build_object_state('map:prefs@1000', {'aaa': POOL_SERIAL}, map={
        'semantics': LWW,
        'entries': {
            'theme': {'data': {'string': 'dark'}, 'timeserial': POOL_SERIAL},
        },
    }, create_op={'mapCreate': {'semantics': LWW, 'entries': {}}}),
)


# --- Internal objects for the pure unit specifications ----------------------------------

def object_message(wire, format=WIRE_FORMAT_JSON):
    """The internal `ObjectMessage` a builder's wire dictionary decodes to."""
    return ObjectMessage.from_dict(wire, format)


def object_messages(protocol_message, format=WIRE_FORMAT_JSON):
    """The internal ObjectMessages an OBJECT or OBJECT_SYNC ProtocolMessage's `state` decodes to."""
    return ObjectMessage.from_protocol_message(protocol_message, format)


def capture_updates(live_object):
    """Records every update `live_object` emits, the no-ops included, and returns the list.

    `apply_operation` returns whether the operation applied (RTLC7g, RTLM15g) and emits the
    resulting update through `notify_updated`, so a specification's
    `update = obj.applyOperation(...)` is `updates[-1]` after the call. The object's own
    `notify_updated` still runs.
    """
    updates = []
    original = live_object.notify_updated

    def notify_updated(update):
        updates.append(update)
        original(update)

    live_object.notify_updated = notify_updated
    return updates


def build_public_object_message(message, channel_name):
    """The public `ObjectMessage` PAOM3 derives from `message` received on `channel_name`.

    `message` is an internal `ObjectMessage` or a builder's wire dictionary. This is the
    expected value a subscription test compares against, built here independently of the
    library's own derivation.
    """
    if isinstance(message, dict):
        message = object_message(message)
    operation = message.operation
    public_operation = publicmessage.ObjectOperation(
        action=operation.action,
        object_id=operation.object_id,
        map_create=operation.resolved_map_create,
        map_set=operation.map_set,
        map_remove=operation.map_remove,
        counter_create=operation.resolved_counter_create,
        counter_inc=operation.counter_inc,
        object_delete=operation.object_delete,
        map_clear=operation.map_clear,
    )
    return publicmessage.ObjectMessage(
        channel=channel_name,
        operation=public_operation,
        id=message.id,
        client_id=message.client_id,
        connection_id=message.connection_id,
        timestamp=message.timestamp,
        serial=message.serial,
        serial_timestamp=message.serial_timestamp,
        site_code=message.site_code,
        extras=message.extras,
    )


# --- The mock-backed client -------------------------------------------------------------

def objects_connected_message(site_code=SITE_CODE, objects_gc_grace_period=GC_GRACE_PERIOD,
                              connection_id=CONNECTION_ID, connection_key=CONNECTION_KEY):
    """The harness CONNECTED message, carrying `siteCode` and `objectsGCGracePeriod`.

    Passing None for either leaves it out. `connectionId` travels on the ProtocolMessage
    itself, which is where the library reads it, though the specification writes it among
    the `connectionDetails`. `maxIdleInterval` is 0 so that the transport schedules no
    idle timer, which a `FakeClock` test would otherwise fire.
    """
    details = {'connectionKey': connection_key, 'connectionStateTtl': 120000, 'maxIdleInterval': 0}
    if site_code is not None:
        details['siteCode'] = site_code
    if objects_gc_grace_period is not None:
        details['objectsGCGracePeriod'] = objects_gc_grace_period
    return {'action': CONNECTED, 'connectionId': connection_id, 'connectionDetails': details}


def objects_attached_message(channel, channel_serial='sync1:', flags=HAS_OBJECTS):
    """An ATTACHED for `channel`.

    The specifications write the modes a server grants as `modes: [...]`; on the wire they
    are bits of `flags`, so pass `HAS_OBJECTS | OBJECT_SUBSCRIBE_FLAG` for
    `flags: HAS_OBJECTS, modes: ["OBJECT_SUBSCRIBE"]`.
    """
    return {'action': ATTACHED, 'channel': channel, 'channelSerial': channel_serial, 'flags': flags}


def standard_mock_websocket(auto_ack=True, on_object=None, connected=None, attached_channel_serial='sync1:',
                            attached_flags=HAS_OBJECTS, sync_objects=STANDARD_POOL_OBJECTS,
                            sync_channel_serial='sync1:'):
    """The specification's synced-channel `MockWebSocket`.

    It accepts every connection with `connected` (by default `objects_connected_message()`);
    answers an ATTACH with an ATTACHED and then an OBJECT_SYNC of `sync_objects`, or no
    OBJECT_SYNC if `sync_objects` is None; answers a DETACH with a DETACHED; and passes each
    OBJECT the client sends to `on_object`, then, with `auto_ack`, ACKs it with
    `ack_serial(msgSerial, i)` for each of its operations.
    """
    connected_message = connected if connected is not None else objects_connected_message()
    mock_ws = MockWebSocket(on_connection_attempt=lambda conn: conn.respond_with_success(connected_message))

    def on_message_from_client(message):
        action = message.get('action')
        if action == ATTACH:
            channel = message.get('channel')
            mock_ws.send_to_client(objects_attached_message(channel, attached_channel_serial, attached_flags))
            if sync_objects is not None:
                mock_ws.send_to_client(build_object_sync_message(channel, sync_channel_serial, sync_objects))
        elif action == OBJECT:
            if on_object is not None:
                on_object(message)
            if auto_ack:
                msg_serial = message['msgSerial']
                serials = [ack_serial(msg_serial, i) for i in range(len(message.get('state') or []))]
                mock_ws.send_to_client(build_ack_message(msg_serial, serials))
        elif action == DETACH:
            mock_ws.send_to_client({'action': DETACHED, 'channel': message.get('channel')})

    mock_ws.on_message_from_client = on_message_from_client
    return mock_ws


def time_mock_http(clock=None):
    """A `MockHttpClient` answering `GET /time` with the time on `clock`.

    Creating an object reads the server time (RTLCV4e, RTLMV4h, RTO16), and a mock-backed
    client must not reach the network for it. Any other request is answered 404.
    """
    time_source = clock if clock is not None else Clock()

    def on_request(request):
        if request.method == 'GET' and request.path == '/time':
            request.respond_with(200, [time_source.now_ms()])
        else:
            request.respond_with(404, {'error': {'code': 40400, 'statusCode': 404, 'message': 'Not found'}})

    return MockHttpClient(on_connection_attempt=lambda conn: conn.respond_with_success(), on_request=on_request)


def objects_client(mock_ws, clock=None, mock_http=None, **kwargs):
    """A realtime client on `mock_ws`, as the specifications' `Realtime(options: {key: ...})`.

    It connects on its own, speaks JSON so that the builders' dictionaries go over the mock
    as they are, and has `GET /time` answered by `time_mock_http(clock)` unless `mock_http`
    is given. `clock` is a `FakeClock` for a specification's `enable_fake_timers()`.
    """
    kwargs.setdefault('auto_connect', True)
    kwargs.setdefault('use_binary_protocol', False)
    if mock_http is None:
        mock_http = time_mock_http(clock)
    return realtime_client(mock_ws, mock_http=mock_http, clock=clock, **kwargs)


def objects_channel_options(*modes):
    """`ChannelOptions` requesting `modes`, by default OBJECT_SUBSCRIBE and OBJECT_PUBLISH."""
    return ChannelOptions(modes=list(modes or OBJECTS_MODES))


class SyncedChannel(NamedTuple):
    """What `setup_synced_channel` returns. It unpacks as `client, channel, root, mock_ws`."""

    client: object
    channel: object
    root: object
    mock_ws: MockWebSocket


async def setup_synced_channel(channel_name='test', mock_ws=None, clock=None, modes=OBJECTS_MODES,
                               **client_options):
    """The specification's `setup_synced_channel(channel_name)`.

    Connects a client to `mock_ws` (by default `standard_mock_websocket()`), gets
    `channel_name` with `modes`, and awaits `channel.object.get()`, which attaches the
    channel and waits for the standard pool to sync. `clock` and `client_options` go to
    `objects_client`.
    """
    if mock_ws is None:
        mock_ws = standard_mock_websocket()
    client = objects_client(mock_ws, clock=clock, **client_options)
    channel = client.channels.get(channel_name, objects_channel_options(*modes))
    root = await channel.object.get()
    return SyncedChannel(client, channel, root, mock_ws)


async def setup_synced_channel_no_ack(channel_name='test', **kwargs):
    """The specification's `setup_synced_channel_no_ack`: OBJECT messages are recorded but not ACKed."""
    return await setup_synced_channel(channel_name, mock_ws=standard_mock_websocket(auto_ack=False), **kwargs)


# --- Negative-assertion quiescence ------------------------------------------------------

async def assert_unchanged_after_quiescence(count_under_test, control_delivered, timeout=5.0,
                                            description='the control to be delivered'):
    """The specification's `assert_unchanged_after_quiescence(count_under_test, control)`.

    Reads `count_under_test()`, waits until `control_delivered()` holds, which a control
    listener (or a follow-up message) on the same dispatch makes true, settles, and asserts
    the count has not moved. Send the message under test before calling this, and the
    control's stimulus after it.
    """
    before = count_under_test()
    await poll_until(control_delivered, timeout=timeout, description=description)
    await settle()
    after = count_under_test()
    assert after == before, f'expected the count to stay at {before} once {description}, but it was {after}'


# --- REST provisioning for the integration tier ----------------------------------------

async def provision_objects_via_rest(api_key, channel_name, operations, client=None):
    """POSTs `operations` to the channel's objects REST endpoint, before any realtime client connects.

    `operations` is one operation dictionary or a list of them, in the REST API's format:
    `{'mapSet': {'key': ..., 'value': {...}}, 'objectId': 'root'}` and so on. Returns the
    `objectIds` of every result, flattened in request order. The REST client goes straight
    to the sandbox and is closed when the test ends; `client` replaces it.
    """
    if client is None:
        client = sandbox_rest_client(api_key)
    path = f"/channels/{quote(channel_name, safe='')}/object"
    response = await client.request('POST', path, OBJECTS_REST_API_VERSION, body=copy.deepcopy(operations))
    if not response.success:
        raise AssertionError(
            f'Provisioning objects on {channel_name!r} failed: {response.status_code} '
            f'{response.error_code} {response.error_message}')
    return [object_id for result in response.items for object_id in (result.get('objectIds') or [])]
