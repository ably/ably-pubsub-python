"""The object message delivered to subscription listeners (PAOM*, PAOOP*).

The specification calls these `PublicAPI::ObjectMessage` and `PublicAPI::ObjectOperation`.
They are exposed to users as `ObjectMessage` and `ObjectOperation`, sharing their names
with the internal wire types in `ably.pubsub.objects.objectmessage`; code that needs both
imports one of the pairs under a module-qualified name.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass
from typing import TYPE_CHECKING

from ably.pubsub.objects.objectmessage import (
    CounterCreate,
    CounterInc,
    MapClear,
    MapCreate,
    MapRemove,
    MapSet,
    ObjectDelete,
    ObjectOperationAction,
)

if TYPE_CHECKING:
    from ably.pubsub.objects import objectmessage


@dataclass
class ObjectOperation:
    """PAOOP1: the operation that caused an object change.

    Unlike the wire operation it never carries the `*CreateWithObjectId` payloads: a
    create sent with a client-generated object id is shown as the `MapCreate` or
    `CounterCreate` it was derived from.
    """

    action: ObjectOperationAction  # PAOOP2a
    object_id: str  # PAOOP2b
    map_create: MapCreate | None = None  # PAOOP2c
    map_set: MapSet | None = None  # PAOOP2d
    map_remove: MapRemove | None = None  # PAOOP2e
    counter_create: CounterCreate | None = None  # PAOOP2f
    counter_inc: CounterInc | None = None  # PAOOP2g
    object_delete: ObjectDelete | None = None  # PAOOP2h
    map_clear: MapClear | None = None  # PAOOP2i

    @staticmethod
    def _from_internal(operation: objectmessage.ObjectOperation) -> ObjectOperation:
        """PAOOP3: the public form of an internal `ObjectOperation`.

        The payloads are copies, so a listener that changes them leaves the objects the
        operation was applied to unchanged.
        """
        return ObjectOperation(
            action=operation.action,  # PAOOP3a
            object_id=operation.object_id,
            map_create=copy.deepcopy(operation.resolved_map_create),  # PAOOP3b
            map_set=copy.deepcopy(operation.map_set),
            map_remove=copy.deepcopy(operation.map_remove),
            counter_create=copy.deepcopy(operation.resolved_counter_create),  # PAOOP3c
            counter_inc=copy.deepcopy(operation.counter_inc),
            object_delete=copy.deepcopy(operation.object_delete),
            map_clear=copy.deepcopy(operation.map_clear),
        )


@dataclass
class ObjectMessage:
    """PAOM1: the inbound object message that caused an object change."""

    channel: str  # PAOM2e
    operation: ObjectOperation  # PAOM2f
    id: str | None = None  # PAOM2a
    client_id: str | None = None  # PAOM2b
    connection_id: str | None = None  # PAOM2c
    timestamp: int | None = None  # PAOM2d
    serial: str | None = None  # PAOM2g
    serial_timestamp: int | None = None  # PAOM2h
    site_code: str | None = None  # PAOM2i
    extras: dict | None = None  # PAOM2j

    @staticmethod
    def _from_internal(message: objectmessage.ObjectMessage, channel_name: str) -> ObjectMessage:
        """PAOM3: the public form of an internal `ObjectMessage` received on `channel_name`.

        The caller ensures `message.operation` is populated (PAOM3a1).
        """
        return ObjectMessage(
            channel=channel_name,  # PAOM3b
            operation=ObjectOperation._from_internal(message.operation),  # PAOM3d
            # PAOM3c
            id=message.id,
            client_id=message.client_id,
            connection_id=message.connection_id,
            timestamp=message.timestamp,
            serial=message.serial,
            serial_timestamp=message.serial_timestamp,
            site_code=message.site_code,
            extras=copy.deepcopy(message.extras),
        )
