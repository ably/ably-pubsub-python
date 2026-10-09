"""The internal object message types and their wire encoding.

These are the `ObjectMessage` (OM*), `ObjectOperation` (OOP*), `ObjectState` (OST*)
and `ObjectData` (OD*) types of features.md, with the protocol v6 operation payloads
(`MapCreate`, `MapSet`, `MapRemove`, `CounterCreate`, `CounterInc`, `ObjectDelete`,
`MapClear`, `MapCreateWithObjectId`, `CounterCreateWithObjectId`) and the `ObjectsMap`,
`ObjectsMapEntry` and `ObjectsCounter` state types.

Every type decodes from a wire dictionary with `from_dict(obj, format)` and encodes to
one with `to_dict(format)`, where `format` is `'json'` or `'msgpack'`. The two forms
differ only in how values are carried:

- `ObjectData.bytes` is a base64 string on the JSON wire and raw binary on msgpack
  (OD2d, OD4c2, OD4d2, OD5a1, OD5b2).
- `ObjectData.json` is a JSON-encoded string on both wires (OD2g), and a decoded `dict`
  or `list` here.
- Numbers are float64 (OD4c3) and decode to `float`.
- Enums are carried as their integer wire values (OOP2, OMP2).

Decoded values are what the rest of the package works with: `ObjectData.bytes` holds
`bytes`, `ObjectData.json` holds the parsed value, and wire names are snake_cased.
Fields that are only ever held locally (`ObjectsMapEntry.tombstoned_at`, RTLM3a1, and
the `derived_from` of the `*CreateWithObjectId` payloads, RTLMV4j5 and RTLCV4g5) are
never encoded.
"""

from __future__ import annotations

import base64
import json
from dataclasses import dataclass, field
from enum import IntEnum
from typing import Any

WIRE_FORMAT_JSON = 'json'
WIRE_FORMAT_MSGPACK = 'msgpack'


class ObjectOperationAction(IntEnum):
    """OOP2: the operation an `ObjectOperation` describes, by its wire value.

    `UNKNOWN` stands for a wire value this library does not recognise (OOP2a). Such an
    operation decodes without error, is never applied and is never encoded.
    """

    UNKNOWN = -1
    MAP_CREATE = 0
    MAP_SET = 1
    MAP_REMOVE = 2
    COUNTER_CREATE = 3
    COUNTER_INC = 4
    OBJECT_DELETE = 5
    MAP_CLEAR = 6

    @classmethod
    def from_wire(cls, value: Any) -> ObjectOperationAction:
        """The member for a wire value, or `UNKNOWN` for one that is not recognised (OOP2a)."""
        if isinstance(value, bool):
            return cls.UNKNOWN
        try:
            return cls(value)
        except ValueError:
            return cls.UNKNOWN


class ObjectsMapSemantics(IntEnum):
    """OMP2: the conflict-resolution semantics of a map, by its wire value.

    `UNKNOWN` stands for a wire value this library does not recognise (OMP2a).
    """

    UNKNOWN = -1
    LWW = 0

    @classmethod
    def from_wire(cls, value: Any) -> ObjectsMapSemantics:
        """The member for a wire value, or `UNKNOWN` for one that is not recognised (OMP2a)."""
        if isinstance(value, bool):
            return cls.UNKNOWN
        try:
            return cls(value)
        except ValueError:
            return cls.UNKNOWN


def _check_format(format: str) -> None:
    if format not in (WIRE_FORMAT_JSON, WIRE_FORMAT_MSGPACK):
        raise ValueError(f"Unknown wire format {format!r}; expected 'json' or 'msgpack'")


def _decode_number(value: Any) -> Any:
    # OD4c3: numbers are float64 on the wire, so a decoded number is always a float
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    return value


def _encode_number(value: Any, format: str) -> Any:
    if format == WIRE_FORMAT_MSGPACK and isinstance(value, int) and not isinstance(value, bool):
        return float(value)
    return value


def _decode_bytes(value: Any) -> Any:
    # OD5a1, OD5b2: raw binary on msgpack, a base64 string on JSON
    if isinstance(value, (bytes, bytearray)):
        return bytes(value)
    if isinstance(value, str):
        return base64.b64decode(value)
    return value


def _encode_bytes(value: Any, format: str) -> Any:
    # OD4c2, OD4d2
    if format == WIRE_FORMAT_MSGPACK:
        return bytes(value)
    return base64.b64encode(value).decode('ascii')


def _encode_json(value: Any) -> str:
    return json.dumps(value, separators=(',', ':'))


@dataclass
class ObjectData:
    """OD1: a value held in an object, either a primitive or a reference to another object.

    At most one of the value fields is set (OD2).
    """

    object_id: str | None = None  # OD2a
    encoding: str | None = None  # OD2b
    boolean: bool | None = None  # OD2c
    bytes: bytes | None = None  # OD2d
    number: float | None = None  # OD2e
    string: str | None = None  # OD2f
    json: dict | list | None = None  # OD2g

    @property
    def value(self) -> Any:
        """The primitive this data holds, or None when it holds a reference or nothing."""
        for candidate in (self.boolean, self.bytes, self.number, self.string, self.json):
            if candidate is not None:
                return candidate
        return None

    @staticmethod
    def from_dict(obj: dict, format: str = WIRE_FORMAT_JSON) -> ObjectData:
        """Decodes an `ObjectData` per OD5."""
        _check_format(format)
        json_value = obj.get('json')
        if isinstance(json_value, str):
            json_value = json.loads(json_value)
        string_value = obj.get('string')
        encoding = obj.get('encoding')
        # OD5a2, OD5b3: a JSON payload carried in `string` under the legacy `json` encoding
        if encoding == 'json' and string_value is not None and json_value is None:
            json_value = json.loads(string_value)
            string_value = None
            encoding = None
        return ObjectData(
            object_id=obj.get('objectId'),
            encoding=encoding,
            boolean=obj.get('boolean'),
            bytes=_decode_bytes(obj.get('bytes')),
            number=_decode_number(obj.get('number')),
            string=string_value,
            json=json_value,
        )

    def to_dict(self, format: str = WIRE_FORMAT_JSON) -> dict:
        """Encodes this `ObjectData` per OD4."""
        _check_format(format)
        result: dict = {}
        if self.object_id is not None:
            result['objectId'] = self.object_id
        if self.encoding is not None:
            result['encoding'] = self.encoding
        if self.boolean is not None:
            result['boolean'] = self.boolean
        if self.bytes is not None:
            result['bytes'] = _encode_bytes(self.bytes, format)
        if self.number is not None:
            result['number'] = _encode_number(self.number, format)
        if self.string is not None:
            result['string'] = self.string
        if self.json is not None:
            result['json'] = _encode_json(self.json)
        return result


@dataclass
class ObjectsMapEntry:
    """OME1: the value at one key of a map.

    `tombstoned_at` (RTLM3a1) is held locally by an `InternalLiveMap` and is never sent
    or received.
    """

    tombstone: bool = False  # OME2a
    timeserial: str | None = None  # OME2b
    serial_timestamp: int | None = None  # OME2d
    data: ObjectData | None = None  # OME2c
    tombstoned_at: int | None = None  # RTLM3a1

    @staticmethod
    def from_dict(obj: dict, format: str = WIRE_FORMAT_JSON) -> ObjectsMapEntry:
        _check_format(format)
        data = obj.get('data')
        return ObjectsMapEntry(
            tombstone=bool(obj.get('tombstone', False)),
            timeserial=obj.get('timeserial'),
            serial_timestamp=obj.get('serialTimestamp'),
            data=ObjectData.from_dict(data, format) if data is not None else None,
        )

    def to_dict(self, format: str = WIRE_FORMAT_JSON) -> dict:
        _check_format(format)
        result: dict = {}
        if self.tombstone:
            result['tombstone'] = True
        if self.timeserial is not None:
            result['timeserial'] = self.timeserial
        if self.serial_timestamp is not None:
            result['serialTimestamp'] = self.serial_timestamp
        if self.data is not None:
            result['data'] = self.data.to_dict(format)
        return result


def _decode_entries(entries: dict | None, format: str) -> dict[str, ObjectsMapEntry] | None:
    if entries is None:
        return None
    return {key: ObjectsMapEntry.from_dict(entry or {}, format) for key, entry in entries.items()}


def _encode_entries(entries: dict[str, ObjectsMapEntry], format: str) -> dict:
    return {key: entry.to_dict(format) for key, entry in entries.items()}


@dataclass
class ObjectsMap:
    """OMP1: the state of a map object, as an `ObjectState` carries it."""

    semantics: ObjectsMapSemantics | None = None  # OMP3a
    entries: dict[str, ObjectsMapEntry] | None = None  # OMP3b
    clear_timeserial: str | None = None  # OMP3c

    @staticmethod
    def from_dict(obj: dict, format: str = WIRE_FORMAT_JSON) -> ObjectsMap:
        _check_format(format)
        semantics = obj.get('semantics')
        return ObjectsMap(
            semantics=ObjectsMapSemantics.from_wire(semantics) if semantics is not None else None,
            entries=_decode_entries(obj.get('entries'), format),
            clear_timeserial=obj.get('clearTimeserial'),
        )

    def to_dict(self, format: str = WIRE_FORMAT_JSON) -> dict:
        _check_format(format)
        result: dict = {}
        if self.semantics is not None:
            result['semantics'] = int(self.semantics)
        if self.entries is not None:
            result['entries'] = _encode_entries(self.entries, format)
        if self.clear_timeserial is not None:
            result['clearTimeserial'] = self.clear_timeserial
        return result


@dataclass
class ObjectsCounter:
    """OCN1: the state of a counter object, as an `ObjectState` carries it."""

    count: float | None = None  # OCN2a

    @staticmethod
    def from_dict(obj: dict, format: str = WIRE_FORMAT_JSON) -> ObjectsCounter:
        _check_format(format)
        return ObjectsCounter(count=_decode_number(obj.get('count')))

    def to_dict(self, format: str = WIRE_FORMAT_JSON) -> dict:
        _check_format(format)
        return {} if self.count is None else {'count': _encode_number(self.count, format)}


@dataclass
class MapCreate:
    """MCR1: the payload of a MAP_CREATE operation."""

    semantics: ObjectsMapSemantics = ObjectsMapSemantics.LWW  # MCR2a
    entries: dict[str, ObjectsMapEntry] = field(default_factory=dict)  # MCR2b

    @staticmethod
    def from_dict(obj: dict, format: str = WIRE_FORMAT_JSON) -> MapCreate:
        _check_format(format)
        semantics = obj.get('semantics')
        return MapCreate(
            semantics=(ObjectsMapSemantics.from_wire(semantics) if semantics is not None
                       else ObjectsMapSemantics.LWW),
            entries=_decode_entries(obj.get('entries'), format) or {},
        )

    def to_dict(self, format: str = WIRE_FORMAT_JSON) -> dict:
        _check_format(format)
        return {'semantics': int(self.semantics), 'entries': _encode_entries(self.entries, format)}


@dataclass
class MapSet:
    """MST1: the payload of a MAP_SET operation."""

    key: str | None = None  # MST2a
    value: ObjectData | None = None  # MST2b

    @staticmethod
    def from_dict(obj: dict, format: str = WIRE_FORMAT_JSON) -> MapSet:
        _check_format(format)
        value = obj.get('value')
        return MapSet(key=obj.get('key'), value=ObjectData.from_dict(value, format) if value is not None else None)

    def to_dict(self, format: str = WIRE_FORMAT_JSON) -> dict:
        _check_format(format)
        result: dict = {}
        if self.key is not None:
            result['key'] = self.key
        if self.value is not None:
            result['value'] = self.value.to_dict(format)
        return result


@dataclass
class MapRemove:
    """MRM1: the payload of a MAP_REMOVE operation."""

    key: str | None = None  # MRM2a

    @staticmethod
    def from_dict(obj: dict, format: str = WIRE_FORMAT_JSON) -> MapRemove:
        _check_format(format)
        return MapRemove(key=obj.get('key'))

    def to_dict(self, format: str = WIRE_FORMAT_JSON) -> dict:
        _check_format(format)
        return {} if self.key is None else {'key': self.key}


@dataclass
class CounterCreate:
    """CCR1: the payload of a COUNTER_CREATE operation."""

    count: float | None = None  # CCR2a

    @staticmethod
    def from_dict(obj: dict, format: str = WIRE_FORMAT_JSON) -> CounterCreate:
        _check_format(format)
        return CounterCreate(count=_decode_number(obj.get('count')))

    def to_dict(self, format: str = WIRE_FORMAT_JSON) -> dict:
        _check_format(format)
        return {} if self.count is None else {'count': _encode_number(self.count, format)}


@dataclass
class CounterInc:
    """CIN1: the payload of a COUNTER_INC operation."""

    number: float | None = None  # CIN2a

    @staticmethod
    def from_dict(obj: dict, format: str = WIRE_FORMAT_JSON) -> CounterInc:
        _check_format(format)
        return CounterInc(number=_decode_number(obj.get('number')))

    def to_dict(self, format: str = WIRE_FORMAT_JSON) -> dict:
        _check_format(format)
        return {} if self.number is None else {'number': _encode_number(self.number, format)}


@dataclass
class ObjectDelete:
    """ODE1: the payload of an OBJECT_DELETE operation, which has no attributes (ODE2)."""

    @staticmethod
    def from_dict(obj: dict, format: str = WIRE_FORMAT_JSON) -> ObjectDelete:
        _check_format(format)
        return ObjectDelete()

    def to_dict(self, format: str = WIRE_FORMAT_JSON) -> dict:
        _check_format(format)
        return {}


@dataclass
class MapClear:
    """MCL1: the payload of a MAP_CLEAR operation, which has no attributes (MCL2)."""

    @staticmethod
    def from_dict(obj: dict, format: str = WIRE_FORMAT_JSON) -> MapClear:
        _check_format(format)
        return MapClear()

    def to_dict(self, format: str = WIRE_FORMAT_JSON) -> dict:
        _check_format(format)
        return {}


@dataclass
class MapCreateWithObjectId:
    """MCRO1: the payload of a MAP_CREATE operation sent with a client-generated object id.

    `derived_from` is the `MapCreate` the payload was built from, kept for local
    application and size calculation (RTLMV4j5) and never sent.
    """

    initial_value: str | None = None  # MCRO2a
    nonce: str | None = None  # MCRO2b
    derived_from: MapCreate | None = None  # RTLMV4j5

    @staticmethod
    def from_dict(obj: dict, format: str = WIRE_FORMAT_JSON) -> MapCreateWithObjectId:
        _check_format(format)
        return MapCreateWithObjectId(initial_value=obj.get('initialValue'), nonce=obj.get('nonce'))

    def to_dict(self, format: str = WIRE_FORMAT_JSON) -> dict:
        _check_format(format)
        result: dict = {}
        if self.initial_value is not None:
            result['initialValue'] = self.initial_value
        if self.nonce is not None:
            result['nonce'] = self.nonce
        return result


@dataclass
class CounterCreateWithObjectId:
    """CCRO1: the payload of a COUNTER_CREATE operation sent with a client-generated object id.

    `derived_from` is the `CounterCreate` the payload was built from, kept for local
    application and size calculation (RTLCV4g5) and never sent.
    """

    initial_value: str | None = None  # CCRO2a
    nonce: str | None = None  # CCRO2b
    derived_from: CounterCreate | None = None  # RTLCV4g5

    @staticmethod
    def from_dict(obj: dict, format: str = WIRE_FORMAT_JSON) -> CounterCreateWithObjectId:
        _check_format(format)
        return CounterCreateWithObjectId(initial_value=obj.get('initialValue'), nonce=obj.get('nonce'))

    def to_dict(self, format: str = WIRE_FORMAT_JSON) -> dict:
        _check_format(format)
        result: dict = {}
        if self.initial_value is not None:
            result['initialValue'] = self.initial_value
        if self.nonce is not None:
            result['nonce'] = self.nonce
        return result


# The operation payloads, by the wire name each is carried under
_PAYLOADS = (
    ('map_create', 'mapCreate', MapCreate),
    ('map_set', 'mapSet', MapSet),
    ('map_remove', 'mapRemove', MapRemove),
    ('counter_create', 'counterCreate', CounterCreate),
    ('counter_inc', 'counterInc', CounterInc),
    ('object_delete', 'objectDelete', ObjectDelete),
    ('map_create_with_object_id', 'mapCreateWithObjectId', MapCreateWithObjectId),
    ('counter_create_with_object_id', 'counterCreateWithObjectId', CounterCreateWithObjectId),
    ('map_clear', 'mapClear', MapClear),
)


@dataclass
class ObjectOperation:
    """OOP1: an operation to apply to an object on a channel."""

    action: ObjectOperationAction  # OOP3a
    object_id: str  # OOP3b
    map_create: MapCreate | None = None  # OOP3j
    map_set: MapSet | None = None  # OOP3k
    map_remove: MapRemove | None = None  # OOP3l
    counter_create: CounterCreate | None = None  # OOP3m
    counter_inc: CounterInc | None = None  # OOP3n
    object_delete: ObjectDelete | None = None  # OOP3o
    map_create_with_object_id: MapCreateWithObjectId | None = None  # OOP3p
    counter_create_with_object_id: CounterCreateWithObjectId | None = None  # OOP3q
    map_clear: MapClear | None = None  # OOP3r

    @property
    def resolved_map_create(self) -> MapCreate | None:
        """`map_create` if present, else the `MapCreate` `map_create_with_object_id` was derived from.

        This is the `mapCreate` RTLM23 merges and PAOOP3b exposes.
        """
        if self.map_create is not None:
            return self.map_create
        if self.map_create_with_object_id is not None:
            return self.map_create_with_object_id.derived_from
        return None

    @property
    def resolved_counter_create(self) -> CounterCreate | None:
        """`counter_create` if present, else the `CounterCreate` `counter_create_with_object_id` was
        derived from.

        This is the `counterCreate` RTLC16 merges and PAOOP3c exposes.
        """
        if self.counter_create is not None:
            return self.counter_create
        if self.counter_create_with_object_id is not None:
            return self.counter_create_with_object_id.derived_from
        return None

    @staticmethod
    def from_dict(obj: dict, format: str = WIRE_FORMAT_JSON) -> ObjectOperation:
        _check_format(format)
        operation = ObjectOperation(
            action=ObjectOperationAction.from_wire(obj.get('action')),
            object_id=obj.get('objectId'),
        )
        for attribute, wire_name, payload_type in _PAYLOADS:
            payload = obj.get(wire_name)
            if payload is not None:
                setattr(operation, attribute, payload_type.from_dict(payload, format))
        return operation

    def to_dict(self, format: str = WIRE_FORMAT_JSON) -> dict:
        _check_format(format)
        if self.action is ObjectOperationAction.UNKNOWN:
            # OOP2a: an unrecognised action is never sent
            raise ValueError('An ObjectOperation with an unrecognised action cannot be encoded')
        result: dict = {'action': int(self.action)}
        if self.object_id is not None:
            result['objectId'] = self.object_id
        for attribute, wire_name, _ in _PAYLOADS:
            payload = getattr(self, attribute)
            if payload is not None:
                result[wire_name] = payload.to_dict(format)
        return result


@dataclass
class ObjectState:
    """OST1: the instantaneous state of an object, as an OBJECT_SYNC carries it."""

    object_id: str  # OST2a
    site_timeserials: dict[str, str] = field(default_factory=dict)  # OST2b
    tombstone: bool = False  # OST2c
    create_op: ObjectOperation | None = None  # OST2d
    map: ObjectsMap | None = None  # OST2e
    counter: ObjectsCounter | None = None  # OST2f

    @staticmethod
    def from_dict(obj: dict, format: str = WIRE_FORMAT_JSON) -> ObjectState:
        _check_format(format)
        create_op = obj.get('createOp')
        objects_map = obj.get('map')
        counter = obj.get('counter')
        return ObjectState(
            object_id=obj.get('objectId'),
            site_timeserials=dict(obj.get('siteTimeserials') or {}),
            tombstone=bool(obj.get('tombstone', False)),
            create_op=ObjectOperation.from_dict(create_op, format) if create_op is not None else None,
            map=ObjectsMap.from_dict(objects_map, format) if objects_map is not None else None,
            counter=ObjectsCounter.from_dict(counter, format) if counter is not None else None,
        )

    def to_dict(self, format: str = WIRE_FORMAT_JSON) -> dict:
        _check_format(format)
        result: dict = {'objectId': self.object_id, 'siteTimeserials': dict(self.site_timeserials)}
        if self.tombstone:
            result['tombstone'] = True
        if self.create_op is not None:
            result['createOp'] = self.create_op.to_dict(format)
        if self.map is not None:
            result['map'] = self.map.to_dict(format)
        if self.counter is not None:
            result['counter'] = self.counter.to_dict(format)
        return result


@dataclass
class ObjectMessage:
    """OM1: an object message sent or received over a channel.

    This is the internal type. The type delivered to listeners is the public
    `ably.pubsub.objects.publicmessage.ObjectMessage` (PAOM1).
    """

    id: str | None = None  # OM2a
    client_id: str | None = None  # OM2b
    connection_id: str | None = None  # OM2c
    extras: dict | None = None  # OM2d
    timestamp: int | None = None  # OM2e
    operation: ObjectOperation | None = None  # OM2f
    object: ObjectState | None = None  # OM2g
    serial: str | None = None  # OM2h
    serial_timestamp: int | None = None  # OM2j
    site_code: str | None = None  # OM2i

    @staticmethod
    def from_dict(obj: dict, format: str = WIRE_FORMAT_JSON) -> ObjectMessage:
        """Decodes one entry of a ProtocolMessage's `state` array (OM5)."""
        _check_format(format)
        operation = obj.get('operation')
        state = obj.get('object')
        return ObjectMessage(
            id=obj.get('id'),
            client_id=obj.get('clientId'),
            connection_id=obj.get('connectionId'),
            extras=obj.get('extras'),
            timestamp=obj.get('timestamp'),
            operation=ObjectOperation.from_dict(operation, format) if operation is not None else None,
            object=ObjectState.from_dict(state, format) if state is not None else None,
            serial=obj.get('serial'),
            serial_timestamp=obj.get('serialTimestamp'),
            site_code=obj.get('siteCode'),
        )

    @staticmethod
    def from_protocol_message(protocol_message: dict, format: str = WIRE_FORMAT_JSON) -> list[ObjectMessage]:
        """Decodes the `state` array of an OBJECT or OBJECT_SYNC ProtocolMessage.

        A message with no `id`, `connectionId` or `timestamp` takes them from the
        ProtocolMessage that carried it (OM2a, OM2c, OM2e).
        """
        messages = []
        protocol_id = protocol_message.get('id')
        for index, entry in enumerate(protocol_message.get('state') or []):
            message = ObjectMessage.from_dict(entry, format)
            if message.id is None and protocol_id is not None:
                message.id = f'{protocol_id}:{index}'
            if message.connection_id is None:
                message.connection_id = protocol_message.get('connectionId')
            if message.timestamp is None:
                message.timestamp = protocol_message.get('timestamp')
            messages.append(message)
        return messages

    def to_dict(self, format: str = WIRE_FORMAT_JSON) -> dict:
        """Encodes this message for the `state` array of a ProtocolMessage (OM4)."""
        _check_format(format)
        result: dict = {}
        for attribute, wire_name in (('id', 'id'), ('client_id', 'clientId'), ('connection_id', 'connectionId'),
                                     ('extras', 'extras'), ('timestamp', 'timestamp'), ('serial', 'serial'),
                                     ('serial_timestamp', 'serialTimestamp'), ('site_code', 'siteCode')):
            value = getattr(self, attribute)
            if value is not None:
                result[wire_name] = value
        if self.operation is not None:
            result['operation'] = self.operation.to_dict(format)
        if self.object is not None:
            result['object'] = self.object.to_dict(format)
        return result
