from __future__ import annotations

import asyncio
import logging
import time
from collections import deque
from itertools import zip_longest
from typing import TYPE_CHECKING

import httpx

from ably.pubsub.transport.defaults import Defaults
from ably.pubsub.transport.websockettransport import ProtocolMessageAction, WebSocketTransport
from ably.pubsub.types.connectiondetails import ConnectionDetails
from ably.pubsub.types.connectionerrors import ConnectionErrors
from ably.pubsub.types.connectionstate import ConnectionEvent, ConnectionState, ConnectionStateChange
from ably.pubsub.types.operations import PublishResult
from ably.pubsub.types.tokendetails import TokenDetails
from ably.pubsub.util.eventemitter import EventEmitter
from ably.pubsub.util.exceptions import AblyException, IncompatibleClientIdException
from ably.pubsub.util.helper import Timer, get_random_id, is_token_error

if TYPE_CHECKING:
    from ably.pubsub.realtime.realtime import DefaultPubSubRealtimeClient

log = logging.getLogger(__name__)


class PendingMessage:
    """Represents a message awaiting acknowledgment from the server"""

    def __init__(self, message: dict):
        self.message = message
        self.future: asyncio.Future[PublishResult] | None = None
        action = message.get('action')

        # Messages that require acknowledgment: MESSAGE, PRESENCE, ANNOTATION, OBJECT
        self.ack_required = action in (
            ProtocolMessageAction.MESSAGE,
            ProtocolMessageAction.PRESENCE,
            ProtocolMessageAction.ANNOTATION,
            ProtocolMessageAction.OBJECT,
        )

        if self.ack_required:
            self.future = asyncio.Future()


class PendingMessageQueue:
    """Queue for tracking messages awaiting acknowledgment"""

    def __init__(self):
        self.messages: list[PendingMessage] = []

    def push(self, pending_message: PendingMessage) -> None:
        """Add a message to the queue"""
        self.messages.append(pending_message)

    def count(self) -> int:
        """Return the number of pending messages"""
        return len(self.messages)

    def complete_messages(
        self,
        serial: int,
        count: int,
        res: list[PublishResult] | None,
        err: AblyException | None = None
    ) -> None:
        """Complete messages based on serial and count from ACK/NACK

        Args:
            serial: The msgSerial of the first message being acknowledged
            count: The number of messages being acknowledged
            res: List of PublishResult objects for each message acknowledged, or None if not available
            err: Error from NACK, or None for successful ACK
        """
        log.debug(f'MessageQueue.complete_messages(): serial={serial}, count={count}, res={res}, err={err}')

        if not self.messages:
            log.warning('MessageQueue.complete_messages(): called on empty queue')
            return

        first = self.messages[0]
        if first:
            start_serial = first.message.get('msgSerial')
            if start_serial is None:
                log.warning('MessageQueue.complete_messages(): first message has no msgSerial')
                return

            end_serial = serial + count

            if end_serial > start_serial:
                # Remove and complete the acknowledged messages
                num_to_complete = min(end_serial - start_serial, len(self.messages))
                completed_messages = self.messages[:num_to_complete]
                self.messages = self.messages[num_to_complete:]

                # Default res to empty list if None
                res_list = res if res is not None else []
                for (msg, publish_result) in zip_longest(completed_messages, res_list):
                    if msg.future and not msg.future.done():
                        if err:
                            msg.future.set_exception(err)
                        else:
                            # If publish_result is None, return empty PublishResult
                            if publish_result is None:
                                publish_result = PublishResult()
                            msg.future.set_result(publish_result)

    def complete_all_messages(self, err: AblyException) -> None:
        """Complete all pending messages with an error"""
        while self.messages:
            msg = self.messages.pop(0)
            if msg.future and not msg.future.done():
                msg.future.set_exception(err)

    def clear(self) -> None:
        """Clear all messages from the queue"""
        self.messages.clear()


class PendingPing:
    """Represents a ping awaiting its heartbeat echo from the server"""

    def __init__(self, id: str):
        self.id = id
        self.future: asyncio.Future[None] = asyncio.get_running_loop().create_future()
        self.start_time: float = time.monotonic()

    @property
    def message(self) -> dict:
        return {"action": ProtocolMessageAction.HEARTBEAT, "id": self.id}

    @property
    def response_time_ms(self) -> float:
        return round((time.monotonic() - self.start_time) * 1000, 2)


class ConnectionManager(EventEmitter):
    def __init__(self, realtime: DefaultPubSubRealtimeClient, initial_state):
        self.options = realtime.options
        self.__ably = realtime
        self.__state: ConnectionState = initial_state
        self.__pending_pings: dict[str, PendingPing] = {}
        self.__timeout_in_secs: float = self.options.realtime_request_timeout / 1000
        self.transport: WebSocketTransport | None = None
        self.__connection_details: ConnectionDetails | None = None
        self.connection_id: str | None = None
        self.__fail_state = ConnectionState.DISCONNECTED
        self.transition_timer: Timer | None = None
        self.suspend_timer: Timer | None = None
        self.retry_timer: Timer | None = None
        self.connect_base_task: asyncio.Task | None = None
        self.disconnect_transport_task: asyncio.Task | None = None
        self.__fallback_hosts: list[str] = self.options.get_fallback_hosts()
        self.queued_messages: deque[PendingMessage] = deque()
        self.__error_reason: AblyException | None = None
        self.msg_serial: int = 0
        self.pending_message_queue: PendingMessageQueue = PendingMessageQueue()
        super().__init__()

    def enact_state_change(self, state: ConnectionState, reason: AblyException | None = None) -> None:
        current_state = self.__state
        log.debug(f'ConnectionManager.enact_state_change(): {current_state} -> {state}; reason = {reason}')
        self.__state = state
        if reason:
            self.__error_reason = reason

        # RTN13b: a ping cannot complete from these states, and the echo of a heartbeat already
        # sent will never arrive, so fail pending pings rather than leaving them to time out
        if state in (
            ConnectionState.SUSPENDED,
            ConnectionState.CLOSING,
            ConnectionState.CLOSED,
            ConnectionState.FAILED,
        ):
            self.__fail_pending_pings(reason or ConnectionErrors[state])

        # RTN16d: Clear connection state when entering SUSPENDED or terminal states
        if state == ConnectionState.SUSPENDED or state in (
            ConnectionState.CLOSED,
            ConnectionState.FAILED
        ):
            self.__connection_details = None
            self.connection_id = None
            self.__connection_key = None
            self.msg_serial = 0

        self._emit('connectionstate', ConnectionStateChange(current_state, state, state, reason))

    def check_connection(self) -> bool:
        try:
            response = httpx.get(self.options.connectivity_check_url)
            return 200 <= response.status_code < 300 and \
                (self.options.connectivity_check_url != Defaults.connectivity_check_url or "yes" in response.text)
        except httpx.HTTPError:
            return False

    def get_state_error(self) -> AblyException:
        return ConnectionErrors[self.state]

    async def __get_transport_params(self) -> dict:
        protocol_version = Defaults.protocol_version
        params = await self.ably.auth.get_auth_transport_param()
        params["v"] = protocol_version
        if self.connection_details:
            params["resume"] = self.connection_details.connection_key
        # RTN2a: Set format to msgpack if use_binary_protocol is enabled
        if self.options.use_binary_protocol:
            params["format"] = "msgpack"

        # Add any custom transport params from options
        params.update(self.options.transport_params)

        return params

    async def close_impl(self) -> None:
        log.debug('ConnectionManager.close_impl()')

        self.cancel_suspend_timer()
        self.start_transition_timer(ConnectionState.CLOSING, fail_state=ConnectionState.CLOSED)
        if self.transport:
            # Try to send protocol CLOSE message in the background
            asyncio.create_task(self.transport.close())
            # Yield to event loop to give the close message a chance to send
            await asyncio.sleep(0)
            await self.transport.dispose()  # Dispose transport resources
        if self.connect_base_task:
            self.connect_base_task.cancel()
        if self.disconnect_transport_task:
            await self.disconnect_transport_task
        self.cancel_retry_timer()

        # Clear connection details to prevent resume on next connect
        # When explicitly closed, we want a fresh connection, not a resume
        self.__connection_details = None
        self.connection_id = None
        self.msg_serial = 0

        self.notify_state(ConnectionState.CLOSED)

    async def send_protocol_message(self, protocol_message: dict) -> PublishResult | None:
        """Send a protocol message and optionally track it for acknowledgment

        Args:
            protocol_message: protocol message dict (new message)
        Returns:
            None
        """
        state_should_queue = (self.state in
                           (ConnectionState.INITIALIZED, ConnectionState.DISCONNECTED, ConnectionState.CONNECTING))

        if self.state != ConnectionState.CONNECTED and not state_should_queue:
            raise AblyException(f"Cannot send message while connection is {self.state}", 400, 90000)

        # RTL6c2: If queueMessages is false, fail immediately when not CONNECTED
        if state_should_queue and not self.options.queue_messages:
            raise AblyException(
                f"Cannot send message while connection is {self.state}, and queue_messages is false",
                400,
                90000,
            )

        pending_message = PendingMessage(protocol_message)

        # Assign msgSerial to messages that need acknowledgment
        if pending_message.ack_required:
            # New message - assign fresh serial
            protocol_message['msgSerial'] = self.msg_serial
            self.pending_message_queue.push(pending_message)
            self.msg_serial += 1

        if state_should_queue:
            self.queued_messages.appendleft(pending_message)
            if pending_message.ack_required:
                return await pending_message.future
            return None

        return await self._send_protocol_message_on_connected_state(pending_message)

    async def _send_protocol_message_on_connected_state(
        self, pending_message: PendingMessage
    ) -> PublishResult | None:
        if self.state == ConnectionState.CONNECTED and self.transport:
            # Add to pending queue before sending (for messages being resent from queue)
            if pending_message.ack_required and pending_message not in self.pending_message_queue.messages:
                self.pending_message_queue.push(pending_message)
            await self.transport.send(pending_message.message)
        else:
            log.exception(
                "ConnectionManager.send_protocol_message(): can not send message with no active transport"
            )
            if pending_message.future:
                pending_message.future.set_exception(
                    AblyException("No active transport", 500, 50000)
                )
        if pending_message.ack_required:
            return await pending_message.future
        return None

    def send_queued_messages(self) -> None:
        log.info(f'ConnectionManager.send_queued_messages(): sending {len(self.queued_messages)} message(s)')
        while len(self.queued_messages) > 0:
            pending_message = self.queued_messages.pop()
            asyncio.create_task(self._send_protocol_message_on_connected_state(pending_message))

    def requeue_pending_messages(self) -> None:
        """RTN19a: Requeue messages awaiting ACK/NACK when transport disconnects

        These messages will be resent when connection becomes CONNECTED again.
        RTN19a2: msgSerial is preserved for resume, reset for new connection.
        """
        pending_count = self.pending_message_queue.count()
        if pending_count == 0:
            return

        log.info(
            f'ConnectionManager.requeue_pending_messages(): '
            f'requeuing {pending_count} pending message(s) for resend'
        )

        # Get all pending messages and add them back to the queue
        # They'll be sent again when we reconnect
        pending_messages = list(self.pending_message_queue.messages)

        # Add back to front of queue (FIFO but priority over new messages)
        # Store the entire PendingMessage object to preserve Future
        for pending_msg in reversed(pending_messages):
            # PendingMessage object retains its Future, msgSerial
            self.queued_messages.append(pending_msg)

        # Clear the message queue since we're requeueing them all
        # When they're resent, the existing Future will be resolved
        self.pending_message_queue.clear()

    def fail_queued_messages(self, err) -> None:
        log.info(
            f"ConnectionManager.fail_queued_messages(): discarding {len(self.queued_messages)} messages;" +
            f" reason = {err}"
        )
        error = err or AblyException("Connection failed", 80000, 500)
        while len(self.queued_messages) > 0:
            pending_msg = self.queued_messages.pop()
            log.exception(
                f"ConnectionManager.fail_queued_messages(): Failed to send protocol message: "
                f"{pending_msg.message}"
            )
            # Fail the Future if it exists
            if pending_msg.future and not pending_msg.future.done():
                pending_msg.future.set_exception(error)

        # Also fail all pending messages awaiting acknowledgment
        if self.pending_message_queue.count() > 0:
            count = self.pending_message_queue.count()
            log.info(
                f"ConnectionManager.fail_queued_messages(): failing {count} pending messages"
            )
            self.pending_message_queue.complete_all_messages(error)

    async def ping(self) -> float:
        # RTN13b
        if self.__state not in (ConnectionState.CONNECTED, ConnectionState.CONNECTING):
            raise AblyException("Cannot send ping request. Calling ping in invalid state", 400, 40000)

        # RTN13e: the id tells this ping's echo apart from server heartbeats and other pings
        pending_ping = PendingPing(get_random_id())
        self.__pending_pings[pending_ping.id] = pending_ping
        try:
            # RTN13d: while connecting, the heartbeat goes out once the connection is established
            if self.__state == ConnectionState.CONNECTED:
                await self.__send_heartbeat(pending_ping)
            # RTN13c
            await asyncio.wait_for(pending_ping.future, self.__timeout_in_secs)
        except asyncio.TimeoutError:
            raise AblyException("Timeout waiting for ping response", 504, 50003) from None
        finally:
            self.__pending_pings.pop(pending_ping.id, None)
        return pending_ping.response_time_ms

    async def __send_heartbeat(self, pending_ping: PendingPing) -> None:
        pending_ping.start_time = time.monotonic()
        try:
            await self.send_protocol_message(pending_ping.message)
        except Exception as error:
            # the caller is waiting on the future, so the send failure is surfaced there
            if not pending_ping.future.done():
                pending_ping.future.set_exception(error)

    def __send_pending_pings(self) -> None:
        """RTN13d: send the heartbeat for each ping waiting on the connection

        A ping registered while the connection was establishing has not sent its heartbeat yet,
        and one whose heartbeat went out before the transport went away will never see that echo,
        so both are (re)sent here and their round trip is measured from this point.
        """
        for pending_ping in list(self.__pending_pings.values()):
            asyncio.create_task(self.__send_heartbeat(pending_ping))

    def on_connected(self, connection_details: ConnectionDetails, connection_id: str,
                     reason: AblyException | None = None) -> None:
        self.__fail_state = ConnectionState.DISCONNECTED

        # RTN19a2: Reset msgSerial if connectionId changed (new connection)
        prev_connection_id = self.connection_id
        connection_id_changed = prev_connection_id is not None and prev_connection_id != connection_id

        if connection_id_changed:
            log.info('ConnectionManager.on_connected(): New connectionId; resetting msgSerial')
            self.msg_serial = 0
            # Note: In JS they call resetSendAttempted() here, but we don't need it
            # because we fail all pending messages on disconnect per RTN7e

        self.__connection_details = connection_details
        self.connection_id = connection_id

        if connection_details.client_id:
            try:
                self.ably.auth._configure_client_id(connection_details.client_id)
            except IncompatibleClientIdException as e:
                self.notify_state(ConnectionState.FAILED, reason=e)
                return

        if self.__state == ConnectionState.CONNECTED:
            state_change = ConnectionStateChange(ConnectionState.CONNECTED, ConnectionState.CONNECTED,
                                                 ConnectionEvent.UPDATE)
            self._emit(ConnectionEvent.UPDATE, state_change)
        else:
            self.notify_state(ConnectionState.CONNECTED, reason=reason)

        self.ably.channels._on_connected()

    async def on_disconnected(self, exception: AblyException) -> None:
        # RTN15h
        if self.transport:
            await self.transport.dispose()
        if exception:
            status_code = exception.status_code
            if status_code >= 500 and status_code <= 504:  # RTN17f1
                if len(self.__fallback_hosts) > 0:
                    try:
                        await self.connect_with_fallback_hosts(self.__fallback_hosts)
                    except Exception as e:
                        self.notify_state(self.__fail_state, reason=e)
                    return
                else:
                    log.info("No fallback host to try for disconnected protocol message")
            elif is_token_error(exception):
                await self.on_token_error(exception)
            else:
                self.notify_state(ConnectionState.DISCONNECTED, exception)
        else:
            log.warn("DISCONNECTED message received without error")

    async def on_token_error(self, exception: AblyException) -> None:
        if self.__error_reason is None or not is_token_error(self.__error_reason):
            self.__error_reason = exception
            try:
                await self.ably.auth._ensure_valid_auth_credentials(force=True)
            except Exception as e:
                self.on_error_from_authorize(e)
                return
            self.notify_state(self.__fail_state, exception, retry_immediately=True)
            return
        self.notify_state(self.__fail_state, exception)

    async def on_error(self, msg: dict, exception: AblyException) -> None:
        if msg.get("channel") is not None:  # RTN15i
            self.on_channel_message(msg)
            return
        if self.transport:
            await self.transport.dispose()
        if is_token_error(exception):  # RTN14b
            await self.on_token_error(exception)
        else:
            self.enact_state_change(ConnectionState.FAILED, exception)

    def on_error_from_authorize(self, exception: AblyException) -> None:
        log.info("ConnectionManager.on_error_from_authorize(): err = %s", exception)
        # RSA4a
        if exception.code == 40171:
            self.notify_state(ConnectionState.FAILED, exception)
        elif exception.status_code == 403:
            msg = 'Client configured authentication provider returned 403; failing the connection'
            log.error(f'ConnectionManager.on_error_from_authorize(): {msg}')
            self.notify_state(ConnectionState.FAILED, AblyException(msg, 403, 80019))
        else:
            msg = 'Client configured authentication provider request failed'
            log.warning(f'ConnectionManager.on_error_from_authorize: {msg}')
            self.notify_state(self.__fail_state, AblyException(msg, 401, 80019))

    async def on_closed(self) -> None:
        if self.transport:
            await self.transport.dispose()
        if self.connect_base_task:
            self.connect_base_task.cancel()

    def on_channel_message(self, msg: dict) -> None:
        self.__ably.channels._on_channel_message(msg)

    def on_heartbeat(self, id: str | None) -> None:
        if id is None:
            return
        pending_ping = self.__pending_pings.pop(id, None)
        # the echo can arrive while wait_for is still cancelling a timed-out ping
        if pending_ping is not None and not pending_ping.future.done():
            pending_ping.future.set_result(None)

    def __fail_pending_pings(self, error: AblyException) -> None:
        pending, self.__pending_pings = self.__pending_pings, {}
        for pending_ping in pending.values():
            if not pending_ping.future.done():
                pending_ping.future.set_exception(error)

    def on_ack(
        self, serial: int, count: int, res: list[PublishResult] | None
    ) -> None:
        """Handle ACK protocol message from server

        Args:
            serial: The msgSerial of the first message being acknowledged
            count: The number of messages being acknowledged
            res: List of PublishResult objects for each message acknowledged, or None if not available
        """
        log.debug(f'ConnectionManager.on_ack(): serial={serial}, count={count}, res={res}')
        self.pending_message_queue.complete_messages(serial, count, res)

    def on_nack(self, serial: int, count: int, err: AblyException | None) -> None:
        """Handle NACK protocol message from server

        Args:
            serial: The msgSerial of the first message being rejected
            count: The number of messages being rejected
            err: Error information from the server
        """
        if not err:
            err = AblyException('Unable to send message; channel not responding', 50001, 500)

        log.error(f'ConnectionManager.on_nack(): serial={serial}, count={count}, err={err}')
        self.pending_message_queue.complete_messages(serial, count, None, err)

    def deactivate_transport(self, reason: AblyException | None = None):
        # RTN19a: Before disconnecting, requeue any pending messages
        # so they'll be resent on reconnection
        if self.transport:
            log.info('ConnectionManager.deactivate_transport(): requeuing pending messages')
            self.requeue_pending_messages()
        self.transport = None
        self.notify_state(ConnectionState.DISCONNECTED, reason)

    def request_state(self, state: ConnectionState, force=False) -> None:
        log.debug(f'ConnectionManager.request_state(): state = {state}')

        if not force and state == self.state:
            return

        if state == ConnectionState.CONNECTING and self.__state == ConnectionState.CONNECTED:
            return

        if state == ConnectionState.CLOSING and self.__state == ConnectionState.CLOSED:
            return

        if state == ConnectionState.CONNECTING and self.__state in (ConnectionState.CLOSED,
                                                                    ConnectionState.FAILED):
            self.ably.channels._initialize_channels()

        if not force:
            self.enact_state_change(state)

        if state == ConnectionState.CONNECTING:
            self.start_connect()

        if state == ConnectionState.CLOSING:
            asyncio.create_task(self.close_impl())

    def start_connect(self) -> None:
        self.start_suspend_timer()
        self.start_transition_timer(ConnectionState.CONNECTING)
        self.connect_base_task = asyncio.create_task(self.connect_base())

    async def connect_with_fallback_hosts(self, fallback_hosts: list) -> Exception | None:
        for host in fallback_hosts:
            try:
                if self.check_connection():
                    await self.try_host(host)
                    return
                else:
                    message = "Unable to connect, network unreachable"
                    log.exception(message)
                    exception = AblyException(message, status_code=404, code=80003)
                    self.notify_state(self.__fail_state, exception)
                    return
            except Exception as exc:
                exception = exc
                log.exception(f'Connection to {host} failed, reason={exception}')
        log.exception("No more fallback hosts to try")
        return exception

    async def connect_base(self) -> None:
        fallback_hosts = self.__fallback_hosts
        primary_host = self.options.get_host()
        try:
            await self.try_host(primary_host)
            return
        except Exception as exception:
            log.exception(f'Connection to {primary_host} failed, reason={exception}')
            if len(fallback_hosts) > 0:
                log.info("Attempting connection to fallback host(s)")
                resp = await self.connect_with_fallback_hosts(fallback_hosts)
                if not resp:
                    return
                exception = resp
            self.notify_state(self.__fail_state, reason=exception)

    async def try_host(self, host) -> None:
        try:
            params = await self.__get_transport_params()
        except AblyException as e:
            self.on_error_from_authorize(e)
            return
        self.transport = WebSocketTransport(self, host, params)
        self._emit('transport.pending', self.transport)
        self.transport.connect()

        future = asyncio.Future()

        def on_transport_connected():
            log.debug('ConnectionManager.try_a_host(): transport connected')
            if self.transport:
                self.transport.off('failed', on_transport_failed)
            if not future.done():
                future.set_result(None)

        async def on_transport_failed(exception):
            log.info('ConnectionManager.try_a_host(): transport failed')
            if self.transport:
                self.transport.off('connected', on_transport_connected)
                await self.transport.dispose()
            future.set_exception(exception)

        self.transport.once('connected', on_transport_connected)
        self.transport.once('failed', on_transport_failed)
        #  Fix asyncio CancelledError in python 3.7
        try:
            await future
        except asyncio.CancelledError:
            return

    def notify_state(self, state: ConnectionState, reason: AblyException | None = None,
                     retry_immediately: bool | None = None) -> None:
        # RTN15a
        retry_immediately = (retry_immediately is not False) and (
            state == ConnectionState.DISCONNECTED and self.__state == ConnectionState.CONNECTED)

        log.debug(
            f'ConnectionManager.notify_state(): new state: {state}'
            + ('; will retry immediately' if retry_immediately else '')
        )

        if state == self.__state:
            return

        self.cancel_transition_timer()
        self.check_suspend_timer(state)

        if retry_immediately:
            self.options.loop.call_soon(self.request_state, ConnectionState.CONNECTING)
        elif state == ConnectionState.DISCONNECTED:
            self.start_retry_timer(self.options.disconnected_retry_timeout)
        elif state == ConnectionState.SUSPENDED:
            self.start_retry_timer(self.options.suspended_retry_timeout)

        if (state == ConnectionState.DISCONNECTED and not retry_immediately) or state == ConnectionState.SUSPENDED:
            self.disconnect_transport()

        self.enact_state_change(state, reason)

        if state == ConnectionState.CONNECTED:
            self.send_queued_messages()
            self.__send_pending_pings()
        elif state in (
            ConnectionState.CLOSING,
            ConnectionState.CLOSED,
            ConnectionState.SUSPENDED,
            ConnectionState.FAILED,
        ):
            # RTN7e: Fail pending messages on SUSPENDED, CLOSED, FAILED
            self.fail_queued_messages(reason)
            self.ably.channels._propagate_connection_interruption(state, reason)
        elif state == ConnectionState.DISCONNECTED and not self.options.queue_messages:
            # RTN7d: If queueMessages is false, fail pending messages on DISCONNECTED
            log.info(
                'ConnectionManager.notify_state(): queueMessages is false; '
                'failing pending messages on DISCONNECTED'
            )
            self.fail_queued_messages(reason)

    def start_transition_timer(self, state: ConnectionState, fail_state: ConnectionState | None = None) -> None:
        log.debug(f'ConnectionManager.start_transition_timer(): transition state = {state}')

        if self.transition_timer:
            log.debug('ConnectionManager.start_transition_timer(): clearing already-running timer')
            self.transition_timer.cancel()

        if fail_state is None:
            fail_state = self.__fail_state if state != ConnectionState.CLOSING else ConnectionState.CLOSED

        timeout = self.options.realtime_request_timeout

        def on_transition_timer_expire():
            if self.transition_timer:
                self.transition_timer = None
                log.info(f'ConnectionManager {state} timer expired, notifying new state: {fail_state}')
                self.notify_state(
                    fail_state,
                    AblyException("Connection cancelled due to request timeout", 504, 50003)
                )

        log.debug(f'ConnectionManager.start_transition_timer(): setting timer for {timeout}ms')

        self.transition_timer = Timer(timeout, on_transition_timer_expire)

    def cancel_transition_timer(self):
        log.debug('ConnectionManager.cancel_transition_timer()')
        if self.transition_timer:
            self.transition_timer.cancel()
            self.transition_timer = None

    def start_suspend_timer(self) -> None:
        log.debug('ConnectionManager.start_suspend_timer()')
        if self.suspend_timer:
            return

        def on_suspend_timer_expire() -> None:
            if self.suspend_timer:
                self.suspend_timer = None
                log.info('ConnectionManager suspend timer expired, requesting new state: suspended')
                self.notify_state(
                    ConnectionState.SUSPENDED,
                    AblyException("Connection to server unavailable", 400, 80002)
                )
                self.__fail_state = ConnectionState.SUSPENDED

        self.suspend_timer = Timer(Defaults.connection_state_ttl, on_suspend_timer_expire)

    def check_suspend_timer(self, state: ConnectionState) -> None:
        if state not in (
            ConnectionState.CONNECTING,
            ConnectionState.DISCONNECTED,
            ConnectionState.SUSPENDED,
        ):
            self.cancel_suspend_timer()

    def cancel_suspend_timer(self) -> None:
        log.debug('ConnectionManager.cancel_suspend_timer()')
        self.__fail_state = ConnectionState.DISCONNECTED
        if self.suspend_timer:
            self.suspend_timer.cancel()
            self.suspend_timer = None

    def start_retry_timer(self, interval: int) -> None:
        def on_retry_timeout():
            log.info('ConnectionManager retry timer expired, retrying')
            self.retry_timer = None
            self.request_state(ConnectionState.CONNECTING)

        self.retry_timer = Timer(interval, on_retry_timeout)

    def cancel_retry_timer(self) -> None:
        if self.retry_timer:
            self.retry_timer.cancel()
            self.retry_timer = None

    def disconnect_transport(self) -> None:
        log.info('ConnectionManager.disconnect_transport()')
        if self.transport:
            # RTN19a: Requeue pending messages before disposing transport
            self.requeue_pending_messages()
            self.disconnect_transport_task = asyncio.create_task(self.transport.dispose())

    async def on_auth_updated(self, token_details: TokenDetails):
        log.info(f"ConnectionManager.on_auth_updated(): state = {self.state}")
        if self.state == ConnectionState.CONNECTED:
            auth_message = {
                "action": ProtocolMessageAction.AUTH,
                "auth": {
                    "accessToken": token_details.token
                }
            }
            await self.send_protocol_message(auth_message)

            state_change = await self.once_async()

            if state_change.current == ConnectionState.CONNECTED:
                return
            elif state_change.current == ConnectionState.FAILED:
                raise state_change.reason
        elif self.state == ConnectionState.CONNECTING:
            if self.connect_base_task and not self.connect_base_task.done():
                self.connect_base_task.cancel()
            if self.transport:
                await self.transport.dispose()
        if self.state != ConnectionState.CONNECTED:
            future = asyncio.Future()

            def on_state_change(state_change: ConnectionStateChange) -> None:
                if state_change.current == ConnectionState.CONNECTED:
                    self.off('connectionstate', on_state_change)
                    future.set_result(token_details)
                if state_change.current in (
                        ConnectionState.CLOSED,
                        ConnectionState.FAILED,
                        ConnectionState.SUSPENDED
                ):
                    self.off('connectionstate', on_state_change)
                    future.set_exception(state_change.reason or self.get_state_error())

            self.on('connectionstate', on_state_change)

            if self.state == ConnectionState.CONNECTING:
                self.start_connect()
            else:
                self.request_state(ConnectionState.CONNECTING)

            return await future

    @property
    def ably(self):
        return self.__ably

    @property
    def state(self) -> ConnectionState:
        return self.__state

    @property
    def connection_details(self) -> ConnectionDetails | None:
        return self.__connection_details
