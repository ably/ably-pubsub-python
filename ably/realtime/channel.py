from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

from ably.realtime.annotations import RealtimeAnnotations
from ably.realtime.connection import ConnectionState
from ably.realtime.presence import RealtimePresence
from ably.rest.channel import Channel
from ably.rest.channel import Channels as RestChannels
from ably.transport.websockettransport import ProtocolMessageAction
from ably.types.annotation import Annotation
from ably.types.channelmode import ChannelMode, decode_channel_mode, encode_channel_mode
from ably.types.channeloptions import ChannelOptions
from ably.types.channelstate import ChannelState, ChannelStateChange
from ably.types.flags import Flag, has_flag
from ably.types.message import Message, MessageAction, MessageVersion
from ably.types.mixins import DecodingContext
from ably.types.operations import MessageOperation, PublishResult, UpdateDeleteResult
from ably.types.presence import PresenceMessage
from ably.util.eventemitter import EventEmitter
from ably.util.exceptions import AblyException, IncompatibleClientIdException
from ably.util.helper import Timer, is_callable_or_coroutine, select_timer, validate_message_size

if TYPE_CHECKING:
    from ably.realtime.realtime import AblyRealtime

log = logging.getLogger(__name__)


class RealtimeChannel(EventEmitter, Channel):
    """
    Ably Realtime Channel

    Attributes
    ----------
    name: str
        Channel name
    state: str
        Channel state
    error_reason: AblyException
        An AblyException instance describing the last error which occurred on the channel, if any.

    Methods
    -------
    attach()
        Attach to channel
    detach()
        Detach from channel
    subscribe(*args)
        Subscribe to messages on a channel
    unsubscribe(*args)
        Unsubscribe to messages from a channel
    """

    def __init__(self, realtime: AblyRealtime, name: str, channel_options: ChannelOptions | None = None):
        EventEmitter.__init__(self)
        self.__name = name
        self.__realtime = realtime
        self.__timer_func = select_timer(realtime.options)
        self.__state = ChannelState.INITIALIZED
        self.__message_emitter = EventEmitter()
        self.__state_timer: Timer | None = None
        self.__attach_resume = False
        self.__attach_serial: str | None = None
        self.__channel_serial: str | None = None
        self.__retry_timer: Timer | None = None
        self.__error_reason: AblyException | None = None
        self.__channel_options = channel_options or ChannelOptions()
        self.__params: dict[str, str] | None = None
        self.__modes: list[ChannelMode] = []  # Channel mode flags from ATTACHED message

        # Delta-specific fields for RTL19/RTL20 compliance
        vcdiff_decoder = self.__realtime.options.vcdiff_decoder if self.__realtime.options.vcdiff_decoder else None
        self.__decoding_context = DecodingContext(vcdiff_decoder=vcdiff_decoder)
        self.__decode_failure_recovery_in_progress = False

        # Used to listen to state changes internally, if we use the public event emitter interface then internals
        # will be disrupted if the user called .off() to remove all listeners
        self.__internal_state_emitter = EventEmitter()

        # Pass channel options as dictionary to parent Channel class
        Channel.__init__(self, realtime, name, self.__channel_options.to_dict())

        # Initialize presence for this channel

        self.__presence = RealtimePresence(self)

        # Initialize realtime annotations for this channel (override REST annotations)
        self._Channel__annotations = RealtimeAnnotations(self, realtime.connection.connection_manager)

    async def set_options(self, channel_options: ChannelOptions) -> None:
        """Set channel options"""
        should_reattach = self.should_reattach_to_set_options(channel_options)
        self.set_options_without_reattach(channel_options)

        if should_reattach:
            self._attach_impl()
            state_change = await self.__internal_state_emitter.once_async()
            if state_change.current in (ChannelState.SUSPENDED, ChannelState.FAILED):
                raise state_change.reason

    def set_options_without_reattach(self, channel_options: ChannelOptions) -> None:
        """Internal method"""
        self.__channel_options = channel_options
        # Update parent class options
        self.options = channel_options.to_dict()

    # RTL4
    async def attach(self) -> None:
        """Attach to channel

        Attach to this channel ensuring the channel is created in the Ably system and all messages published
        on the channel are received by any channel listeners registered using subscribe

        Raises
        ------
        AblyException
            If unable to attach channel
        """

        log.info(f'RealtimeChannel.attach() called, channel = {self.name}')

        # RTL4a - if channel is attached do nothing
        if self.state == ChannelState.ATTACHED:
            return

        self.__error_reason = None

        # RTL4b
        connection_state = self.__realtime.connection.state
        if connection_state not in [
            ConnectionState.CONNECTING,
            ConnectionState.CONNECTED,
            ConnectionState.DISCONNECTED
        ]:
            raise AblyException(
                message=f"Unable to attach channel; connection state = {connection_state}",
                code=90001,
                status_code=400
            )

        if self.state != ChannelState.ATTACHING:
            self._request_state(ChannelState.ATTACHING)

        state_change = await self.__internal_state_emitter.once_async()

        if state_change.current in (ChannelState.SUSPENDED, ChannelState.FAILED):
            raise state_change.reason

    def _attach_impl(self):
        log.debug("RealtimeChannel.attach_impl(): sending ATTACH protocol message")

        # RTL4c
        attach_msg = {
            "action": ProtocolMessageAction.ATTACH,
            "params": self.__channel_options.params,
            "channel": self.name,
        }

        flags = self._encode_flags()

        if flags:
            attach_msg["flags"] = flags
        if self.__channel_serial:
            attach_msg["channelSerial"] = self.__channel_serial

        self._send_message(attach_msg)

    # RTL5
    async def detach(self) -> None:
        """Detach from channel

        Any resulting channel state change is emitted to any listeners registered
        Once all clients globally have detached from the channel, the channel will be released
        in the Ably service within two minutes.

        Raises
        ------
        AblyException
            If unable to detach channel
        """

        log.info(f'RealtimeChannel.detach() called, channel = {self.name}')

        # RTL5g, RTL5b - raise exception if state invalid
        if self.__realtime.connection.state in [ConnectionState.CLOSING, ConnectionState.FAILED]:
            raise AblyException(
                message=f"Unable to detach; channel state = {self.state}",
                code=90001,
                status_code=400
            )

        # RTL5a - if channel already detached do nothing
        if self.state in [ChannelState.INITIALIZED, ChannelState.DETACHED]:
            return

        if self.state == ChannelState.SUSPENDED:
            self._notify_state(ChannelState.DETACHED)
            return
        elif self.state == ChannelState.FAILED:
            raise AblyException("Unable to detach; channel state = failed", 90001, 400)
        else:
            self._request_state(ChannelState.DETACHING)

        # RTL5h - wait for pending connection
        if self.__realtime.connection.state == ConnectionState.CONNECTING:
            self.__realtime.connect()

        state_change = await self.__internal_state_emitter.once_async()
        new_state = state_change.current

        if new_state == ChannelState.DETACHED:
            return
        elif new_state == ChannelState.ATTACHING:
            raise AblyException("Detach request superseded by a subsequent attach request", 90000, 409)
        else:
            raise state_change.reason

    def _detach_impl(self) -> None:
        log.debug("RealtimeChannel.detach_impl(): sending DETACH protocol message")

        # RTL5d
        detach_msg = {
            "action": ProtocolMessageAction.DETACH,
            "channel": self.__name,
        }

        self._send_message(detach_msg)

    # RTL7
    async def subscribe(self, *args) -> None:
        """Subscribe to a channel

        Registers a listener for messages on the channel.
        The caller supplies a listener function, which is called
        each time one or more messages arrives on the channel.

        The function resolves once the channel is attached.

        Parameters
        ----------
        *args: event, listener
            Subscribe event and listener

            arg1(event): str, optional
                Subscribe to messages with the given event name

            arg2(listener): callable
                Subscribe to all messages on the channel

            When no event is provided, arg1 is used as the listener.

        Raises
        ------
        AblyException
            If unable to subscribe to a channel due to invalid connection state
        ValueError
            If no valid subscribe arguments are passed
        """
        if isinstance(args[0], str):
            event = args[0]
            if not args[1]:
                raise ValueError("channel.subscribe called without listener")
            if not is_callable_or_coroutine(args[1]):
                raise ValueError("subscribe listener must be function or coroutine function")
            listener = args[1]
        elif is_callable_or_coroutine(args[0]):
            listener = args[0]
            event = None
        else:
            raise ValueError('invalid subscribe arguments')

        log.info(f'RealtimeChannel.subscribe called, channel = {self.name}, event = {event}')

        if event is not None:
            # RTL7b
            self.__message_emitter.on(event, listener)
        else:
            # RTL7a
            self.__message_emitter.on(listener)

        # RTL7c
        await self.attach()

    # RTL8
    def unsubscribe(self, *args) -> None:
        """Unsubscribe from a channel

        Deregister the given listener for (for any/all event names).
        This removes an earlier event-specific subscription.

        Parameters
        ----------
        *args: event, listener
            Unsubscribe event and listener

            arg1(event): str, optional
                Unsubscribe to messages with the given event name

            arg2(listener): callable
                Unsubscribe to all messages on the channel

            When no event is provided, arg1 is used as the listener.

        Raises
        ------
        ValueError
            If no valid unsubscribe arguments are passed, no listener or listener is not a function
            or coroutine
        """
        if len(args) == 0:
            event = None
            listener = None
        elif isinstance(args[0], str):
            event = args[0]
            if not args[1]:
                raise ValueError("channel.unsubscribe called without listener")
            if not is_callable_or_coroutine(args[1]):
                raise ValueError("unsubscribe listener must be a function or coroutine function")
            listener = args[1]
        elif is_callable_or_coroutine(args[0]):
            listener = args[0]
            event = None
        else:
            raise ValueError('invalid unsubscribe arguments')

        log.info(f'RealtimeChannel.unsubscribe called, channel = {self.name}, event = {event}')

        if listener is None:
            # RTL8c
            self.__message_emitter.off()
        elif event is not None:
            # RTL8b
            self.__message_emitter.off(event, listener)
        else:
            # RTL8a
            self.__message_emitter.off(listener)

    # RTL6
    async def publish(self, *args, **kwargs) -> PublishResult:
        """Publish a message or messages on this channel

        Publishes a single message or an array of messages to the channel.

        Parameters
        ----------
        *args: name and data, or message object(s)
            Either:
            - name (str) and data (any): publish a single message
            - message (Message or dict): publish a single message object
            - messages (list): publish multiple message objects

        Raises
        ------
        AblyException
            If the channel or connection state prevents publishing,
            if clientId validation fails, or if message size exceeds limits
        ValueError
            If invalid arguments are provided
        """
        messages = []

        # RTL6i: Parse arguments - expect Message object, array of Messages, or name and data
        if len(args) == 1:
            if isinstance(args[0], Message):
                # Single Message object
                messages = [args[0]]
            elif isinstance(args[0], dict):
                # Message as dict
                messages = [Message(**args[0])]
            elif isinstance(args[0], list):
                # RTL6i2: Array of Message objects
                messages = []
                for msg in args[0]:
                    if isinstance(msg, Message):
                        messages.append(msg)
                    elif isinstance(msg, dict):
                        messages.append(Message(**msg))
                    else:
                        raise ValueError("Array must contain Message objects or dicts")
            else:
                raise ValueError(
                    "The single-argument form of publish() expects a message object or an array of message objects"
                )
        elif len(args) == 2:
            # RTL6i1: name and data form
            # RTL6i3: Allow name and/or data to be None
            name = args[0]
            data = args[1]
            messages = [Message(name=name, data=data)]
        else:
            raise ValueError("publish() expects either (name, data) or a message object or array of messages")

        # RTL6g: Validate clientId for identified clients
        if self.ably.auth.client_id:
            for m in messages:
                # RTL6g3: Reject messages with different clientId
                if m.client_id == '*':
                    raise IncompatibleClientIdException(
                        'Wildcard client_id is reserved and cannot be used when publishing messages',
                        400, 40012)
                elif m.client_id is not None and not self.ably.auth.can_assume_client_id(m.client_id):
                    raise IncompatibleClientIdException(
                        f'Cannot publish with client_id \'{m.client_id}\' as it is incompatible with the '
                        f'current configured client_id \'{self.ably.auth.client_id}\'',
                        400, 40012)


        # Encode messages (RTL6a: same encoding as RestChannel#publish)
        encoded_messages = []
        for m in messages:
            # Encode the message with encryption if needed
            if self.cipher:
                m.encrypt(self.cipher)

            # Convert to dict representation
            msg_dict = m.as_dict(binary=self.ably.options.use_binary_protocol)
            encoded_messages.append(msg_dict)

        # RSL1i: Check message size limit
        max_message_size = getattr(self.ably.options, 'max_message_size', 65536)  # 64KB default
        validate_message_size(encoded_messages, self.ably.options.use_binary_protocol, max_message_size)

        # RTL6c: Check connection and channel state
        self._throw_if_unpublishable_state()

        log.info(
            f'RealtimeChannel.publish(): sending message; '
            f'channel = {self.name}, state = {self.state}, message count = {len(encoded_messages)}'
        )

        # Send protocol message
        protocol_message = {
            "action": ProtocolMessageAction.MESSAGE,
            "channel": self.name,
            "messages": encoded_messages,
        }

        # RTL6b: Await acknowledgment from server
        return await self.__realtime.connection.connection_manager.send_protocol_message(protocol_message)

    def _throw_if_unpublishable_state(self) -> None:
        """Check if the channel and connection are in a state that allows publishing

        Raises
        ------
        AblyException
            If the channel or connection state prevents publishing
        """
        # RTL6c4: Check connection state
        connection_state = self.__realtime.connection.state
        if connection_state not in [
            ConnectionState.INITIALIZED,
            ConnectionState.CONNECTED,
            ConnectionState.CONNECTING,
            ConnectionState.DISCONNECTED,
        ]:
            raise AblyException(
                f"Cannot publish message; connection state is {connection_state}",
                400,
                40001,
            )

        # RTL6c4: Check channel state
        if self.state in [ChannelState.SUSPENDED, ChannelState.FAILED]:
            raise AblyException(
                f"Cannot publish message; channel state is {self.state}",
                400,
                90001,
            )

    async def _send_update(
            self,
            message: Message,
            action: MessageAction,
            operation: MessageOperation | None = None,
            params: dict | None = None,
    ) -> UpdateDeleteResult:
        """Internal method to send update/delete/append operations via websocket.

        Parameters
        ----------
        message : Message
            Message object with serial field required
        action : MessageAction
            The action type (MESSAGE_UPDATE, MESSAGE_DELETE, MESSAGE_APPEND)
        operation : MessageOperation, optional
            Operation metadata (description, metadata)

        Returns
        -------
        UpdateDeleteResult
            Result containing version serial of the operation

        Raises
        ------
        AblyException
            If message serial is missing or connection/channel state prevents operation
        """
        # Check message has serial
        if not message.serial:
            raise AblyException(
                "Message serial is required for update/delete/append operations",
                status_code=400,
                code=40003,
            )

        # Check connection and channel state
        self._throw_if_unpublishable_state()

        # Create version from operation if provided
        if not operation:
            version = None
        else:
            version = MessageVersion(
                client_id=operation.client_id,
                description=operation.description,
                metadata=operation.metadata
            )

        # Create a new message with the operation fields
        update_message = Message(
            name=message.name,
            data=message.data,
            client_id=message.client_id,
            serial=message.serial,
            action=action,
            version=version,
            extras=message.extras,
            annotations=message.annotations,
        )

        # Encrypt if needed
        if self.cipher:
            update_message.encrypt(self.cipher)

        # Convert to dict representation
        msg_dict = update_message.as_dict(binary=self.ably.options.use_binary_protocol)

        log.info(
            f'RealtimeChannel._send_update(): sending {action.name} message; '
            f'channel = {self.name}, state = {self.state}, serial = {message.serial}'
        )

        stringified_params = {k: str(v).lower() if isinstance(v, bool) else v for k, v in params.items()} \
            if params else None

        # Send protocol message
        protocol_message = {
            "action": ProtocolMessageAction.MESSAGE,
            "channel": self.name,
            "messages": [msg_dict],
            "params": stringified_params,
        }

        # Send and await acknowledgment
        result = await self.__realtime.connection.connection_manager.send_protocol_message(protocol_message)

        # Return UpdateDeleteResult - we don't have version_serial from the result yet
        # The server will send ACK with the result
        if result and hasattr(result, 'serials') and result.serials:
            return UpdateDeleteResult(version_serial=result.serials[0])
        return UpdateDeleteResult()

    async def update_message(
            self,
            message: Message,
            operation: MessageOperation | None = None,
            params: dict | None = None,
    ) -> UpdateDeleteResult:
        """Updates an existing message on this channel.

        Parameters
        ----------
        message : Message
            Message object to update. Must have a serial field.
        operation : MessageOperation, optional
            Optional MessageOperation containing description and metadata for the update.

        Returns
        -------
        UpdateDeleteResult
            Result containing the version serial of the updated message.

        Raises
        ------
        AblyException
            If message serial is missing or connection/channel state prevents the update
        """
        return await self._send_update(message, MessageAction.MESSAGE_UPDATE, operation, params)

    async def delete_message(
            self,
            message: Message,
            operation: MessageOperation | None = None,
            params: dict | None = None
    ) -> UpdateDeleteResult:
        """Deletes a message on this channel.

        Parameters
        ----------
        message : Message
            Message object to delete. Must have a serial field.
        operation : MessageOperation, optional
            Optional MessageOperation containing description and metadata for the delete.

        Returns
        -------
        UpdateDeleteResult
            Result containing the version serial of the deleted message.

        Raises
        ------
        AblyException
            If message serial is missing or connection/channel state prevents the delete
        """
        return await self._send_update(message, MessageAction.MESSAGE_DELETE, operation, params)

    async def append_message(
            self,
            message: Message,
            operation: MessageOperation | None = None,
            params: dict | None = None,
    ) -> UpdateDeleteResult:
        """Appends data to an existing message on this channel.

        Parameters
        ----------
        message : Message
            Message object with data to append. Must have a serial field.
        operation : MessageOperation, optional
            Optional MessageOperation containing description and metadata for the append.

        Returns
        -------
        UpdateDeleteResult
            Result containing the version serial of the appended message.

        Raises
        ------
        AblyException
            If message serial is missing or connection/channel state prevents the append
        """
        return await self._send_update(message, MessageAction.MESSAGE_APPEND, operation, params)

    async def get_message(self, serial_or_message, timeout=None):
        """Retrieves a single message by its serial using the REST API.

        Parameters
        ----------
        serial_or_message : str or Message
            Either a string serial or a Message object with a serial field.
        timeout : float, optional
            Timeout for the request.

        Returns
        -------
        Message
            Message object for the requested serial.

        Raises
        ------
        AblyException
            If the serial is missing or the message cannot be retrieved.
        """
        # Delegate to parent Channel (REST) implementation
        return await Channel.get_message(self, serial_or_message, timeout=timeout)

    async def get_message_versions(self, serial_or_message, params=None):
        """Retrieves version history for a message using the REST API.

        Parameters
        ----------
        serial_or_message : str or Message
            Either a string serial or a Message object with a serial field.
        params : dict, optional
            Optional dict of query parameters for pagination.

        Returns
        -------
        PaginatedResult
            PaginatedResult containing Message objects representing each version.

        Raises
        ------
        AblyException
            If the serial is missing or versions cannot be retrieved.
        """
        # Delegate to parent Channel (REST) implementation
        return await Channel.get_message_versions(self, serial_or_message, params=params)

    def _on_message(self, proto_msg: dict) -> None:
        action = proto_msg.get('action')
        # RTL4c1
        channel_serial = proto_msg.get('channelSerial')
        # TM2a, TM2c, TM2f
        Message.update_inner_message_fields(proto_msg)

        if action == ProtocolMessageAction.ATTACHED:
            flags = proto_msg.get('flags')
            error = proto_msg.get("error")
            exception = None
            resumed = False
            has_presence = False

            self.__attach_serial = channel_serial
            self.__channel_serial = channel_serial
            self.__params = proto_msg.get('params')

            if error:
                exception = AblyException.from_dict(error)

            if flags:
                resumed = has_flag(flags, Flag.RESUMED)
                # RTP1: Check for HAS_PRESENCE flag
                has_presence = has_flag(flags, Flag.HAS_PRESENCE)
                # Store channel attach flags
                self.__modes = decode_channel_mode(flags)

            #  RTL12
            if self.state == ChannelState.ATTACHED:
                if not resumed:
                    state_change = ChannelStateChange(self.state, ChannelState.ATTACHED, resumed, exception)
                    self._emit("update", state_change)
            elif self.state == ChannelState.ATTACHING:
                self._notify_state(ChannelState.ATTACHED, resumed=resumed, has_presence=has_presence)
            else:
                log.warn("RealtimeChannel._on_message(): ATTACHED received while not attaching")
        elif action == ProtocolMessageAction.DETACHED:
            if self.state == ChannelState.DETACHING:
                self._notify_state(ChannelState.DETACHED)
            elif self.state == ChannelState.ATTACHING:
                self._notify_state(ChannelState.SUSPENDED)
            else:
                self._request_state(ChannelState.ATTACHING)
        elif action == ProtocolMessageAction.MESSAGE:
            messages = []
            try:
                messages = Message.from_encoded_array(proto_msg.get('messages'),
                                                      cipher=self.cipher, context=self.__decoding_context)
                self.__channel_serial = channel_serial
            except AblyException as e:
                if e.code == 40018:  # Delta decode failure - start recovery
                    self._start_decode_failure_recovery(e)
                else:
                    log.error(f"Message processing error {e}. Skip messages {proto_msg.get('messages')}")
            for message in messages:
                self.__message_emitter._emit(message.name, message)
        elif action == ProtocolMessageAction.PRESENCE:
            # Handle PRESENCE messages
            presence_messages = proto_msg.get('presence', [])
            decoded_presence = PresenceMessage.from_encoded_array(presence_messages, cipher=self.cipher)
            self.__presence.set_presence(decoded_presence, is_sync=False)
        elif action == ProtocolMessageAction.SYNC:
            # Handle SYNC messages (RTP18)
            presence_messages = proto_msg.get('presence', [])
            decoded_presence = PresenceMessage.from_encoded_array(presence_messages, cipher=self.cipher)
            sync_channel_serial = proto_msg.get('channelSerial')
            self.__presence.set_presence(decoded_presence, is_sync=True, sync_channel_serial=sync_channel_serial)
        elif action == ProtocolMessageAction.ANNOTATION:
            # Handle ANNOTATION messages
            # RTAN4b: Populate annotation fields from protocol message
            Annotation.update_inner_annotation_fields(proto_msg)
            annotation_data = proto_msg.get('annotations', [])
            try:
                annotations = Annotation.from_encoded_array(annotation_data, cipher=self.cipher)
                # Process annotations through the annotations handler
                self.annotations._process_incoming(annotations)
                # RTL15b: Update channel serial for ANNOTATION messages
                self.__channel_serial = channel_serial
            except Exception as e:
                log.error(f"Annotation processing error {e}. Skip annotations {annotation_data}")
        elif action == ProtocolMessageAction.ERROR:
            error = AblyException.from_dict(proto_msg.get('error'))
            self._notify_state(ChannelState.FAILED, reason=error)

    def _request_state(self, state: ChannelState) -> None:
        log.debug(f'RealtimeChannel._request_state(): state = {state}')
        self._notify_state(state)
        self._check_pending_state()

    def _notify_state(self, state: ChannelState, reason: AblyException | None = None,
                      resumed: bool = False, has_presence: bool = False) -> None:
        log.debug(f'RealtimeChannel._notify_state(): state = {state}')

        self.__clear_state_timer()

        if state == self.state:
            return

        if reason is not None:
            self.__error_reason = reason

        if state == ChannelState.INITIALIZED:
            self.__error_reason = None

        if state == ChannelState.SUSPENDED and self.ably.connection.state == ConnectionState.CONNECTED:
            self.__start_retry_timer()
        else:
            self.__cancel_retry_timer()

        # RTL4j1
        if state == ChannelState.ATTACHED:
            self.__attach_resume = True
        if state in (ChannelState.DETACHING, ChannelState.FAILED):
            self.__attach_resume = False

        # RTP5a1
        if state in (ChannelState.DETACHED, ChannelState.SUSPENDED, ChannelState.FAILED):
            self.__channel_serial = None

        if state != ChannelState.ATTACHING:
            self.__decode_failure_recovery_in_progress = False

        state_change = ChannelStateChange(self.__state, state, resumed, reason=reason)

        self.__state = state
        self._emit(state, state_change)
        self.__internal_state_emitter._emit(state, state_change)

        # RTP5: Notify presence of channel state change
        self.__presence.act_on_channel_state(state, has_presence=has_presence, error=reason)

    def _send_message(self, msg: dict) -> None:
        asyncio.create_task(self.__realtime.connection.connection_manager.send_protocol_message(msg))

    def _check_pending_state(self):
        connection_state = self.__realtime.connection.connection_manager.state

        if connection_state is not ConnectionState.CONNECTED:
            log.debug(f"RealtimeChannel._check_pending_state(): connection state = {connection_state}")
            return

        if self.state == ChannelState.ATTACHING:
            self.__start_state_timer()
            self._attach_impl()
        elif self.state == ChannelState.DETACHING:
            self.__start_state_timer()
            self._detach_impl()

    def __start_state_timer(self) -> None:
        if not self.__state_timer:
            def on_timeout() -> None:
                log.debug('RealtimeChannel.start_state_timer(): timer expired')
                self.__state_timer = None
                self.__timeout_pending_state()

            self.__state_timer = self.__timer_func(self.__realtime.options.realtime_request_timeout, on_timeout)

    def __clear_state_timer(self) -> None:
        if self.__state_timer:
            self.__state_timer.cancel()
            self.__state_timer = None

    def __timeout_pending_state(self) -> None:
        if self.state == ChannelState.ATTACHING:
            self._notify_state(
                ChannelState.SUSPENDED, reason=AblyException("Channel attach timed out", 408, 90007))
        elif self.state == ChannelState.DETACHING:
            self._notify_state(ChannelState.ATTACHED, reason=AblyException("Channel detach timed out", 408, 90007))
        else:
            self._check_pending_state()

    def __start_retry_timer(self) -> None:
        if self.__retry_timer:
            return

        self.__retry_timer = self.__timer_func(
            self.ably.options.channel_retry_timeout, self.__on_retry_timer_expire)

    def __cancel_retry_timer(self) -> None:
        if self.__retry_timer:
            self.__retry_timer.cancel()
            self.__retry_timer = None

    def __on_retry_timer_expire(self) -> None:
        if self.state == ChannelState.SUSPENDED and self.ably.connection.state == ConnectionState.CONNECTED:
            self.__retry_timer = None
            log.info("RealtimeChannel retry timer expired, attempting a new attach")
            self._request_state(ChannelState.ATTACHING)

    def should_reattach_to_set_options(self, new_options: ChannelOptions) -> bool:
        """Internal method"""
        if self.state != ChannelState.ATTACHING and self.state != ChannelState.ATTACHED:
            return False
        return self.__channel_options != new_options

    # RTL23
    @property
    def name(self) -> str:
        """Returns channel name"""
        return self.__name

    # RTL2b
    @property
    def state(self) -> ChannelState:
        """Returns channel state"""
        return self.__state

    @state.setter
    def state(self, state: ChannelState) -> None:
        self.__state = state

    # RTL24
    @property
    def error_reason(self) -> AblyException | None:
        """An AblyException instance describing the last error which occurred on the channel, if any."""
        return self.__error_reason

    @property
    def params(self) -> dict[str, str]:
        """Get channel parameters"""
        return self.__params

    @property
    def presence(self):
        """Get the RealtimePresence object for this channel"""
        return self.__presence

    @property
    def annotations(self) -> RealtimeAnnotations:
        return self._Channel__annotations

    @property
    def modes(self):
        """Get the list of channel modes"""
        return self.__modes

    def _start_decode_failure_recovery(self, error: AblyException) -> None:
        """Start RTL18 decode failure recovery procedure"""

        if self.__decode_failure_recovery_in_progress:
            log.info('VCDiff recovery process already started, skipping')
            return

        self.__decode_failure_recovery_in_progress = True

        # RTL18a: Log error with code 40018
        log.error(f'VCDiff decode failure: {error}')

        # RTL18b: Message is already discarded by not processing it

        # RTL18c: Send ATTACH with previous channel serial and transition to ATTACHING
        self._notify_state(ChannelState.ATTACHING, reason=error)
        self._check_pending_state()

    def _encode_flags(self) -> int | None:
        if not self.__channel_options.modes and not self.__attach_resume:
            return None

        flags = 0

        if self.__attach_resume:
            flags |= Flag.ATTACH_RESUME

        if self.__channel_options.modes:
            flags |= encode_channel_mode(self.__channel_options.modes)

        return flags


class Channels(RestChannels):
    """Creates and destroys RealtimeChannel objects.

    Methods
    -------
    get(name)
        Gets a channel
    release(name)
        Releases a channel
    """

    # RTS3
    def get(self, name: str, options: ChannelOptions | None = None, **kwargs) -> RealtimeChannel:
        """Creates a new RealtimeChannel object, or returns the existing channel object.

        Parameters
        ----------

        name: str
            Channel name
        options: ChannelOptions or dict, optional
            Channel options for the channel
        **kwargs:
            Additional keyword arguments to create ChannelOptions (e.g., cipher, params)
        """
        # Convert kwargs to ChannelOptions if provided
        if kwargs and not options:
            options = ChannelOptions(**kwargs)
        elif options and isinstance(options, dict):
            options = ChannelOptions.from_dict(options)

        if name not in self.__all:
            channel = self.__all[name] = RealtimeChannel(self.__ably, name, options)
        else:
            channel = self.__all[name]
            # Update options if channel is not attached or currently attaching
            if options and channel.should_reattach_to_set_options(options):
                raise AblyException(
                    'Channels.get() cannot be used to set channel options that would cause the channel to '
                    'reattach. Please, use RealtimeChannel.setOptions() instead.',
                    400,
                    40000
                )
            elif options:
                channel.set_options_without_reattach(options)
        return channel

    # RTS4
    def release(self, name: str) -> None:
        """Releases a RealtimeChannel object, deleting it, and enabling it to be garbage collected

        It also removes any listeners associated with the channel.
        To release a channel, the channel state must be INITIALIZED, DETACHED, or FAILED.


        Parameters
        ----------
        name: str
            Channel name
        """
        if name not in self.__all:
            return
        del self.__all[name]

    def _on_channel_message(self, msg: dict) -> None:
        channel_name = msg.get('channel')
        if not channel_name:
            log.error(
                'Channels.on_channel_message()',
                f'received event without channel, action = {msg.get("action")}'
            )
            return

        channel = self.__all[channel_name]
        if not channel:
            log.warning(
                'Channels.on_channel_message()',
                f'receieved event for non-existent channel: {channel_name}'
            )
            return

        channel._on_message(msg)

    def _propagate_connection_interruption(self, state: ConnectionState, reason: AblyException | None) -> None:
        from_channel_states = (
            ChannelState.ATTACHING,
            ChannelState.ATTACHED,
            ChannelState.DETACHING,
            ChannelState.SUSPENDED,
        )

        connection_to_channel_state = {
            ConnectionState.CLOSING: ChannelState.DETACHED,
            ConnectionState.CLOSED: ChannelState.DETACHED,
            ConnectionState.FAILED: ChannelState.FAILED,
            ConnectionState.SUSPENDED: ChannelState.SUSPENDED,
        }

        for channel_name in self.__all:
            channel = self.__all[channel_name]
            if channel.state in from_channel_states:
                channel._notify_state(connection_to_channel_state[state], reason)

    def _on_connected(self) -> None:
        for channel_name in self.__all:
            channel = self.__all[channel_name]
            if channel.state == ChannelState.ATTACHING or channel.state == ChannelState.DETACHING:
                channel._check_pending_state()
            elif channel.state == ChannelState.SUSPENDED:
                asyncio.create_task(channel.attach())
            elif channel.state == ChannelState.ATTACHED:
                channel._request_state(ChannelState.ATTACHING)

    def _initialize_channels(self) -> None:
        for channel_name in self.__all:
            channel = self.__all[channel_name]
            channel._request_state(ChannelState.INITIALIZED)
