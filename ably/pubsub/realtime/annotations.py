from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from ably.pubsub.http.annotations import HttpAnnotations, construct_validate_annotation
from ably.pubsub.transport.websockettransport import ProtocolMessageAction
from ably.pubsub.types.annotation import Annotation, AnnotationAction
from ably.pubsub.types.channelmode import ChannelMode
from ably.pubsub.types.channelstate import ChannelState
from ably.pubsub.util.eventemitter import EventEmitter
from ably.pubsub.util.helper import is_callable_or_coroutine

if TYPE_CHECKING:
    from ably.pubsub.realtime.channel import RealtimeChannel
    from ably.pubsub.realtime.connectionmanager import ConnectionManager

log = logging.getLogger(__name__)


class RealtimeAnnotations:
    """
    Provides realtime methods for managing annotations on messages,
    including publishing annotations and subscribing to annotation events.
    """

    __connection_manager: ConnectionManager
    __channel: RealtimeChannel

    def __init__(self, channel: RealtimeChannel, connection_manager: ConnectionManager):
        """
        Initialize RealtimeAnnotations.

        Args:
            channel: The Realtime Channel this annotations instance belongs to
        """
        self.__channel = channel
        self.__connection_manager = connection_manager
        self.__subscriptions = EventEmitter()
        self.__http_annotations = HttpAnnotations(channel)

    async def __send_annotation(self, annotation: Annotation, params: dict | None = None):
        """
        Internal method to send an annotation via the realtime connection.

        Args:
            annotation: Validated Annotation object with action and message_serial set
            params: Optional dict of query parameters
        """
        # Check if channel and connection are in publishable state
        self.__channel._throw_if_unpublishable_state()

        log.info(
            f'RealtimeAnnotations: sending annotation, channelName = {self.__channel.name}, '
            f'messageSerial = {annotation.message_serial}, '
            f'type = {annotation.type}, action = {annotation.action}'
        )

        # RSAN1c3: encrypt the data payload on an encrypted channel
        if self.__channel.cipher:
            annotation.encrypt(self.__channel.cipher)

        # Convert to wire format (array of annotations)
        wire_annotation = annotation.as_dict(binary=self.__channel.ably.options.use_binary_protocol)

        # Build protocol message
        protocol_message = {
            "action": ProtocolMessageAction.ANNOTATION,
            "channel": self.__channel.name,
            "annotations": [wire_annotation],
        }

        if params:
            # Stringify boolean params
            stringified_params = {k: str(v).lower() if isinstance(v, bool) else v for k, v in params.items()}
            protocol_message["params"] = stringified_params

        # Send via WebSocket
        await self.__connection_manager.send_protocol_message(protocol_message)

    async def publish(self, msg_or_serial, annotation: Annotation, params: dict | None = None):
        """
        Publish an annotation on a message via the realtime connection.

        Args:
            msg_or_serial: Either a message serial (string) or a Message object
            annotation: Annotation object
            params: Optional dict of query parameters

        Returns:
            None

        Raises:
            AblyException: If the request fails, inputs are invalid, or channel is in unpublishable state
        """
        annotation = construct_validate_annotation(msg_or_serial, annotation)

        # RSAN1c1/RTAN1a: Explicitly set action to ANNOTATION_CREATE
        annotation = annotation._copy_with(action=AnnotationAction.ANNOTATION_CREATE)

        await self.__send_annotation(annotation, params)

    async def delete(
        self,
        msg_or_serial,
        annotation: Annotation,
        params: dict | None = None,
    ):
        """
        Delete an annotation on a message.

        Args:
            msg_or_serial: Either a message serial (string) or a Message object
            annotation: Annotation containing annotation properties
            params: Optional dict of query parameters

        Returns:
            None

        Raises:
            AblyException: If the request fails or inputs are invalid
        """
        annotation = construct_validate_annotation(msg_or_serial, annotation)

        # RSAN2a/RTAN2a: Explicitly set action to ANNOTATION_DELETE
        annotation = annotation._copy_with(action=AnnotationAction.ANNOTATION_DELETE)

        await self.__send_annotation(annotation, params)

    async def subscribe(self, *args):
        """
        Subscribe to annotation events on this channel.

        Parameters
        ----------
        *args: type_or_types, listener
            Subscribe type(s) and listener

            arg1(type_or_types): str or list[str], optional
                Subscribe to annotations of the given type or types (RTAN4c)

            arg2(listener): callable
                Subscribe to all annotations on the channel

            When no type is provided, arg1 is used as the listener.

        Raises
        ------
        ValueError
            If no valid subscribe arguments are passed
        """
        # Parse arguments similar to channel.subscribe
        if len(args) == 0:
            raise ValueError("annotations.subscribe called without arguments")

        annotation_types = None

        # RTAN4c: Support string or list of strings as first argument
        if len(args) >= 2 and isinstance(args[0], (str, list)):
            if isinstance(args[0], list):
                annotation_types = args[0]
            else:
                annotation_types = [args[0]]
            if not args[1]:
                raise ValueError("annotations.subscribe called without listener")
            if not is_callable_or_coroutine(args[1]):
                raise ValueError("subscribe listener must be function or coroutine function")
            listener = args[1]
        elif is_callable_or_coroutine(args[0]):
            listener = args[0]
        else:
            raise ValueError('invalid subscribe arguments')

        # RTAN4d: Implicitly attach channel on subscribe
        await self.__channel.attach()

        # RTAN4e: Check if ANNOTATION_SUBSCRIBE mode is enabled (log warning per spec),
        # only when server explicitly sent modes (non-empty list)
        if self.__channel.state == ChannelState.ATTACHED and self.__channel.modes:
            if ChannelMode.ANNOTATION_SUBSCRIBE not in self.__channel.modes:
                log.warning(
                    "You are trying to add an annotation listener, but the "
                    "ANNOTATION_SUBSCRIBE channel mode was not included in the ATTACHED flags. "
                    "This subscription may not receive annotations. Ensure you request the "
                    "annotation_subscribe channel mode in ChannelOptions."
                )

        # Register subscription after successful attach
        if annotation_types is not None:
            for t in annotation_types:
                self.__subscriptions.on(t, listener)
        else:
            self.__subscriptions.on(listener)

    def unsubscribe(self, *args):
        """
        Unsubscribe from annotation events on this channel.

        Parameters
        ----------
        *args: type_or_types, listener
            Unsubscribe type(s) and listener

            arg1(type_or_types): str or list[str], optional
                Unsubscribe from annotations of the given type or types

            arg2(listener): callable
                Unsubscribe from all annotations on the channel

            When no type is provided, arg1 is used as the listener.
            When no arguments are provided, unsubscribes all annotation listeners (RTAN5).

        Raises
        ------
        ValueError
            If invalid unsubscribe arguments are passed
        """
        # RTAN5: Support no arguments to unsubscribe all annotation listeners
        if len(args) == 0:
            self.__subscriptions.off()
        elif len(args) >= 2 and isinstance(args[0], (str, list)):
            # RTAN5a: Support string or list of strings for type(s)
            if isinstance(args[0], list):
                annotation_types = args[0]
            else:
                annotation_types = [args[0]]
            listener = args[1]
            for t in annotation_types:
                self.__subscriptions.off(t, listener)
        elif is_callable_or_coroutine(args[0]):
            listener = args[0]
            self.__subscriptions.off(listener)
        else:
            raise ValueError('invalid unsubscribe arguments')

    def _process_incoming(self, incoming_annotations):
        """
        Process incoming annotations from the server.

        This is called internally when ANNOTATION protocol messages are received.

        Args:
            incoming_annotations: List of Annotation objects received from the server
        """
        for annotation in incoming_annotations:
            # Emit to type-specific listeners and catch-all listeners
            annotation_type = annotation.type or ''
            self.__subscriptions._emit(annotation_type, annotation)

    async def get(self, msg_or_serial, params: dict | None = None):
        """
        Retrieve annotations for a message with pagination support.

        This delegates to the REST implementation.

        Args:
            msg_or_serial: Either a message serial (string) or a Message object
            params: Optional dict of query parameters (limit, start, end, direction)

        Returns:
            PaginatedResult: A paginated result containing Annotation objects

        Raises:
            AblyException: If the request fails or serial is invalid
        """
        # Delegate to REST implementation
        return await self.__http_annotations.get(msg_or_serial, params)
