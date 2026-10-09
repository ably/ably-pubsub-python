"""The creation blueprints `LiveCounter` and `LiveMap` (RTLCV*, RTLMV*), and the value unions.

A blueprint is an inert, immutable description of an object to create. It becomes
ObjectMessages only when a mutation evaluates it (RTLCV4, RTLMV4), so `create` performs
no validation (RTLCV3c, RTLMV3c).

Evaluation is pure: the caller fetches the server time (RTO16) and passes it in, and
each evaluation generates a fresh nonce, so a blueprint used twice creates two objects.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from typing import Any, TypeVar, Union

from ably.pubsub.objects.objectid import generate_nonce, generate_object_id
from ably.pubsub.objects.objectmessage import (
    WIRE_FORMAT_JSON,
    CounterCreate,
    CounterCreateWithObjectId,
    MapCreate,
    MapCreateWithObjectId,
    ObjectData,
    ObjectMessage,
    ObjectOperation,
    ObjectOperationAction,
    ObjectsMapEntry,
    ObjectsMapSemantics,
)
from ably.pubsub.util.exceptions import AblyException

# The primitive values a map entry can hold: String, Number, Boolean, Binary, JsonArray
# and JsonObject (RTLM20a3)
Primitive = Union[str, float, bool, bytes, list, dict]

T = TypeVar('T', bound=Primitive)


@dataclass(frozen=True)
class LiveCounter:
    """RTLCV1: the intent to create a counter with an initial count."""

    _count: Any = 0  # RTLCV2a

    @staticmethod
    def create(initial_count: float = 0) -> LiveCounter:
        """RTLCV3: a blueprint for a counter starting at `initial_count`."""
        return LiveCounter(initial_count)


@dataclass(frozen=True)
class LiveMap:
    """RTLMV1: the intent to create a map with initial entries."""

    _entries: Any = None  # RTLMV2a

    @staticmethod
    def create(entries: dict[str, LiveMapValue] | None = None) -> LiveMap:
        """RTLMV3: a blueprint for a map holding `entries`.

        A dict is copied, along with each JSON object, JSON array and binary value in it, so
        the blueprint does not change when the caller's values do (RTLMV3d); anything else is
        kept for evaluation to reject (RTLMV3c).
        """
        if not isinstance(entries, dict):
            return LiveMap(entries)
        return LiveMap({key: _snapshot(value) for key, value in entries.items()})


# The values `set` accepts: a primitive, or a blueprint for a new object (RTTS11)
LiveMapValue = Union[Primitive, LiveMap, LiveCounter]


def validate_key(key: Any) -> None:
    """RTLMV4b: raises AblyException 40003 unless `key` is a string.

    A map's `set` and `remove` validate their key the same way (RTLM20e1, RTLM21e1).
    """
    if not isinstance(key, str):
        raise AblyException('Map key should be string', 400, 40003)


def validate_value(value: Any) -> None:
    """RTLM20e1: raises the AblyException a map's `set` raises for `value`, without evaluating it.

    That is 40013 unless `value` is a primitive or a blueprint (RTLMV4c), and for a blueprint,
    whatever evaluating it raises (RTLCV4a, RTLMV4a-RTLMV4c), so that a write can reject one
    before fetching the server time its object ids are generated from (RTO16).
    """
    if isinstance(value, LiveCounter):
        _counter_create(value)
    elif isinstance(value, LiveMap):
        entries, _ = _map_entries_data(value)
        for entry in entries.values():
            if isinstance(entry, (LiveCounter, LiveMap)):
                validate_value(entry)
    else:
        primitive_to_object_data(value)


def validate_amount(amount: Any) -> float:
    """RTLC12e1: `amount` as a float, raising AblyException 40003 unless it is a finite number.

    A bool is not a number, and None is not an omitted amount. A counter's `increment` and
    `decrement` validate their amount this way (RTLC12e1, RTLC13c).
    """
    number = _finite_number(amount)
    if number is None:
        raise AblyException('Counter value increment should be a valid number', 400, 40003)
    return number


def primitive_to_object_data(value: Any) -> ObjectData:
    """RTLMV4d3-RTLMV4d7: the `ObjectData` holding the primitive `value`.

    It holds the value as it decodes on receipt: a number as a float (OD4c3), binary as
    `bytes`, and a JSON object or array as a copy parsed back from its JSON encoding.
    Raises AblyException 40013 for any other value (RTLMV4c, OD4a), which includes a
    number that is not finite, a dict or list that is not JSON-encodable, a blueprint,
    and a live object or a `PathObject` or `Instance` wrapping one (RTLMV4c1).
    """
    if isinstance(value, bool):
        return ObjectData(boolean=value)  # RTLMV4d6
    if isinstance(value, (int, float)):
        number = _finite_number(value)
        if number is not None:
            return ObjectData(number=number)  # RTLMV4d5
    elif isinstance(value, str):
        return ObjectData(string=value)  # RTLMV4d4
    elif isinstance(value, (bytes, bytearray)):
        return ObjectData(bytes=bytes(value))  # RTLMV4d7
    elif isinstance(value, (dict, list)):
        try:
            encoded = json.dumps(value, allow_nan=False)
        except (TypeError, ValueError, RecursionError):
            pass
        else:
            return ObjectData(json=json.loads(encoded))  # RTLMV4d3
    raise AblyException('Map value data type is unsupported', 400, 40013)


def evaluate_live_counter(value: LiveCounter, timestamp_ms: int) -> ObjectMessage:
    """RTLCV4: the COUNTER_CREATE `ObjectMessage` a `LiveCounter` evaluates to.

    `timestamp_ms` is the server time the object id is generated with (RTLCV4e). The
    operation carries `counter_create_with_object_id`, whose `derived_from` is the
    `CounterCreate` it was built from (RTLCV4g5). Raises AblyException 40003 for a count
    that is not a finite number (RTLCV4a).
    """
    counter_create = _counter_create(value)  # RTLCV4a, RTLCV4b
    initial_value = _initial_value(counter_create)  # RTLCV4c
    nonce = generate_nonce()  # RTLCV4d
    object_id = generate_object_id('counter', initial_value, nonce, timestamp_ms)  # RTLCV4f
    return ObjectMessage(operation=ObjectOperation(
        action=ObjectOperationAction.COUNTER_CREATE,  # RTLCV4g1
        object_id=object_id,  # RTLCV4g2
        counter_create_with_object_id=CounterCreateWithObjectId(
            initial_value=initial_value,  # RTLCV4g4
            nonce=nonce,  # RTLCV4g3
            derived_from=counter_create,  # RTLCV4g5
        ),
    ))


def evaluate_live_map(value: LiveMap, timestamp_ms: int) -> list[ObjectMessage]:
    """RTLMV4: the ObjectMessages a `LiveMap` evaluates to, nested creates first, depth-first,
    and this map's MAP_CREATE last (RTLMV4k).

    The MAP_CREATE carries `map_create_with_object_id`, whose `derived_from` is the
    `MapCreate` it was built from (RTLMV4j5). Raises AblyException 40003 for entries that
    are not a dict or a key that is not a string (RTLMV4a, RTLMV4b), and 40013 for a
    value of an unsupported type (RTLMV4c).
    """
    # Every value at this level is validated (RTLMV4c) before any blueprint is evaluated
    entries, data = _map_entries_data(value)

    messages: list[ObjectMessage] = []
    for key, entry in entries.items():
        if isinstance(entry, LiveCounter):
            counter_create_message = evaluate_live_counter(entry, timestamp_ms)  # RTLMV4d1
            messages.append(counter_create_message)
            data[key] = ObjectData(object_id=counter_create_message.operation.object_id)
        elif isinstance(entry, LiveMap):
            nested_messages = evaluate_live_map(entry, timestamp_ms)  # RTLMV4d2
            messages.extend(nested_messages)
            data[key] = ObjectData(object_id=nested_messages[-1].operation.object_id)

    map_create = MapCreate(  # RTLMV4e
        semantics=ObjectsMapSemantics.LWW,
        entries={key: ObjectsMapEntry(data=entry_data) for key, entry_data in data.items()},
    )
    initial_value = _initial_value(map_create)  # RTLMV4f
    nonce = generate_nonce()  # RTLMV4g
    object_id = generate_object_id('map', initial_value, nonce, timestamp_ms)  # RTLMV4i
    messages.append(ObjectMessage(operation=ObjectOperation(
        action=ObjectOperationAction.MAP_CREATE,  # RTLMV4j1
        object_id=object_id,  # RTLMV4j2
        map_create_with_object_id=MapCreateWithObjectId(
            initial_value=initial_value,  # RTLMV4j4
            nonce=nonce,  # RTLMV4j3
            derived_from=map_create,  # RTLMV4j5
        ),
    )))
    return messages  # RTLMV4k


def evaluate(value: LiveCounter | LiveMap, timestamp_ms: int) -> list[ObjectMessage]:
    """The ObjectMessages a blueprint evaluates to, the create for `value` itself last."""
    if isinstance(value, LiveCounter):
        return [evaluate_live_counter(value, timestamp_ms)]
    if isinstance(value, LiveMap):
        return evaluate_live_map(value, timestamp_ms)
    raise TypeError(f'Expected a LiveCounter or LiveMap, got {type(value).__name__}')


def _counter_create(value: LiveCounter) -> CounterCreate:
    """RTLCV4a, RTLCV4b: the `CounterCreate` a `LiveCounter` describes, raising AblyException 40003
    for a count that is not a finite number."""
    count = _finite_number(value._count)
    if count is None:
        raise AblyException('Counter value should be a valid number', 400, 40003)  # RTLCV4a
    return CounterCreate(count=count)  # RTLCV4b


def _map_entries_data(value: LiveMap) -> tuple[dict, dict[str, ObjectData | None]]:
    """RTLMV4a-RTLMV4c: a `LiveMap`'s entries, and the `ObjectData` of each, None for a blueprint.

    Raises AblyException 40003 for entries that are not a dict or a key that is not a string,
    and 40013 for a value of an unsupported type at this level; a blueprint among the entries
    is not looked into.
    """
    # `LiveMap.create()` and `LiveMap.create(None)` both leave the entries unset
    entries = {} if value._entries is None else value._entries
    if not isinstance(entries, dict):
        raise AblyException('Map entries should be a dict', 400, 40003)  # RTLMV4a
    for key in entries:
        validate_key(key)  # RTLMV4b
    # RTLMV4c
    data: dict[str, ObjectData | None] = {
        key: None if isinstance(entry, (LiveCounter, LiveMap)) else primitive_to_object_data(entry)
        for key, entry in entries.items()
    }
    return entries, data


def _snapshot(value: Any) -> Any:
    """A copy of a map entry's value that later changes to `value` do not reach (RTLMV3d).

    A JSON object or array is copied through its JSON encoding, which evaluation applies to
    it anyway (RTLMV4d3), and binary is copied to `bytes`. A value that does not encode is
    kept as it is, as no validation is done at creation (RTLMV3c); evaluation rejects it.
    """
    if isinstance(value, bytearray):
        return bytes(value)
    if isinstance(value, (dict, list)):
        try:
            return json.loads(json.dumps(value, allow_nan=False))
        except (TypeError, ValueError, RecursionError):
            return value
    return value


def _finite_number(value: Any) -> float | None:
    """`value` as a float if it is a finite number, else None. A boolean is not a number."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    try:
        number = float(value)
    except OverflowError:
        return None
    return number if math.isfinite(number) else None


def _initial_value(create: CounterCreate | MapCreate) -> str:
    """RTLCV4c, RTLMV4f: the JSON string of `create` in its JSON-wire encoding (OD4d), whatever
    protocol the connection uses.

    The object id is the hash of this exact string (RTO14b1), and it is sent unchanged as
    the `initialValue`. Keys keep the order `to_dict` builds them in, with no whitespace
    between tokens, non-ASCII characters escaped, and numbers in Python's shortest
    round-trip form.
    """
    return json.dumps(create.to_dict(WIRE_FORMAT_JSON), separators=(',', ':'), allow_nan=False)
