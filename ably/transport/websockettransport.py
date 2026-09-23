from __future__ import annotations

import asyncio
import json
import logging
import socket
import urllib.parse
from enum import IntEnum
from typing import TYPE_CHECKING

import msgpack

from ably.http.httputils import HttpUtils
from ably.transport.defaults import Defaults
from ably.types.connectiondetails import ConnectionDetails
from ably.types.operations import PublishResult
from ably.util.eventemitter import EventEmitter
from ably.util.exceptions import AblyException
from ably.util.helper import Timer, unix_time_ms

try:
    # websockets 15+ preferred imports
    from websockets import ClientConnection as WebSocketClientProtocol
    from websockets import connect as ws_connect
except ImportError:
    # websockets 14 and earlier fallback
    from websockets.client import WebSocketClientProtocol
    from websockets.client import connect as ws_connect

from websockets.exceptions import ConnectionClosedOK, WebSocketException

if TYPE_CHECKING:
    from ably.realtime.connection import ConnectionManager

log = logging.getLogger(__name__)


class ProtocolMessageAction(IntEnum):
    HEARTBEAT = 0
    ACK = 1
    NACK = 2
    CONNECT = 3
    CONNECTED = 4
    DISCONNECT = 5
    DISCONNECTED = 6
    CLOSE = 7
    CLOSED = 8
    ERROR = 9
    ATTACH = 10
    ATTACHED = 11
    DETACH = 12
    DETACHED = 13
    PRESENCE = 14
    MESSAGE = 15
    SYNC = 16
    AUTH = 17
    ACTIVATE = 18
    OBJECT = 19
    OBJECT_SYNC = 20
    ANNOTATION = 21


class WebSocketTransport(EventEmitter):
    def __init__(self, connection_manager: ConnectionManager, host: str, params: dict):
        self.websocket: WebSocketClientProtocol | None = None
        self.read_loop: asyncio.Task | None = None
        self.connect_task: asyncio.Task | None = None
        self.ws_connect_task: asyncio.Task | None = None
        self.connection_manager = connection_manager
        self.options = self.connection_manager.options
        self.is_connected = False
        self.idle_timer = None
        self.last_activity = None
        self.max_idle_interval = None
        self.is_disposed = False
        self.host = host
        self.params = params
        self.format = params.get('format', 'json')
        super().__init__()

    def connect(self):
        headers = HttpUtils.default_headers()
        query_params = urllib.parse.urlencode(self.params)
        scheme = 'wss' if self.options.tls else 'ws'
        port = Defaults.get_port(self.options)
        ws_url = f'{scheme}://{self.host}:{port}?{query_params}'
        log.info(f'connect(): attempting to connect to {ws_url}')
        self.ws_connect_task = asyncio.create_task(self.ws_connect(ws_url, headers))
        self.ws_connect_task.add_done_callback(self.on_ws_connect_done)

    def on_ws_connect_done(self, task: asyncio.Task):
        try:
            exception = task.exception()
        except asyncio.CancelledError as e:
            exception = e
        if exception is None or isinstance(exception, ConnectionClosedOK):
            return
        log.info(
            f'WebSocketTransport.on_ws_connect_done(): exception = {exception}'
        )

    async def ws_connect(self, ws_url, headers):
        try:
            # Use additional_headers for websockets 15+, fallback to extra_headers for older versions
            try:
                async with ws_connect(ws_url, additional_headers=headers) as websocket:
                    await self._handle_websocket_connection(ws_url, websocket)
            except TypeError:
                # Fallback for websockets 14 and earlier
                async with ws_connect(ws_url, extra_headers=headers) as websocket:
                    await self._handle_websocket_connection(ws_url, websocket)
        except (WebSocketException, socket.gaierror) as e:
            exception = AblyException(f'Error opening websocket connection: {e}', 400, 40000)
            log.exception(f'WebSocketTransport.ws_connect(): Error opening websocket connection: {exception}')
            self._emit('failed', exception)
            raise exception from e

    async def _handle_websocket_connection(self, ws_url, websocket):
        log.info(f'ws_connect(): connection established to {ws_url}')
        self._emit('connected')
        self.websocket = websocket
        self.read_loop = self.connection_manager.options.loop.create_task(self.ws_read_loop())
        self.read_loop.add_done_callback(self.on_read_loop_done)
        try:
            await self.read_loop
        except WebSocketException as err:
            if not self.is_disposed:
                await self.dispose()
                self.connection_manager.deactivate_transport(err)
        else:
            # Read loop exited normally (e.g., server sent normal WS close frame)
            if not self.is_disposed:
                await self.dispose()
                self.connection_manager.deactivate_transport()

    async def on_protocol_message(self, msg):
        self.on_activity()
        log.debug(f'WebSocketTransport.on_protocol_message(): received protocol message: {msg}')
        action = msg.get('action')
        if action == ProtocolMessageAction.CONNECTED:
            connection_id = msg.get('connectionId')
            connection_details = ConnectionDetails.from_dict(msg.get('connectionDetails'))

            error = msg.get('error')
            exception = None
            if error:
                exception = AblyException.from_dict(error)

            max_idle_interval = connection_details.max_idle_interval
            if max_idle_interval:
                self.max_idle_interval = max_idle_interval + self.options.realtime_request_timeout
                self.on_activity()
            self.is_connected = True
            if self.host != self.options.get_host():  # RTN17e
                self.options.fallback_host = self.host
            self.connection_manager.on_connected(connection_details, connection_id, reason=exception)
        elif action == ProtocolMessageAction.DISCONNECTED:
            error = msg.get('error')
            exception = None
            if error is not None:
                exception = AblyException.from_dict(error)
            await self.connection_manager.on_disconnected(exception)
        elif action == ProtocolMessageAction.AUTH:
            try:
                await self.connection_manager.ably.auth.authorize()
            except Exception as exc:
                log.exception(f"WebSocketTransport.on_protocol_message(): An exception \
                                occurred during reauth: {exc}")
        elif action == ProtocolMessageAction.CLOSED:
            if self.ws_connect_task:
                self.ws_connect_task.cancel()
            await self.connection_manager.on_closed()
        elif action == ProtocolMessageAction.ERROR:
            error = msg.get('error')
            exception = AblyException.from_dict(error)
            await self.connection_manager.on_error(msg, exception)
        elif action == ProtocolMessageAction.HEARTBEAT:
            id = msg.get('id')
            self.connection_manager.on_heartbeat(id)
        elif action == ProtocolMessageAction.ACK:
            # Handle acknowledgment of sent messages
            msg_serial = msg.get('msgSerial', 0)
            count = msg.get('count', 1)
            res = msg.get('res')
            if res is not None:
                res = [PublishResult.from_dict(result) for result in res]
            self.connection_manager.on_ack(msg_serial, count, res)
        elif action == ProtocolMessageAction.NACK:
            # Handle negative acknowledgment (error sending messages)
            msg_serial = msg.get('msgSerial', 0)
            count = msg.get('count', 1)
            error = msg.get('error')
            exception = AblyException.from_dict(error) if error else None
            self.connection_manager.on_nack(msg_serial, count, exception)
        elif action in (
            ProtocolMessageAction.ATTACHED,
            ProtocolMessageAction.DETACHED,
            ProtocolMessageAction.MESSAGE,
            ProtocolMessageAction.PRESENCE,
            ProtocolMessageAction.ANNOTATION,
            ProtocolMessageAction.SYNC
        ):
            self.connection_manager.on_channel_message(msg)

    async def ws_read_loop(self):
        if not self.websocket:
            raise AblyException('ws_read_loop started with no websocket', 500, 50000)
        try:
            async for raw in self.websocket:
                # Decode based on format
                try:
                    msg = self.decode_raw_websocket_frame(raw)
                    task = asyncio.create_task(self.on_protocol_message(msg))
                    task.add_done_callback(self.on_protcol_message_handled)
                except Exception as e:
                    log.exception(
                        f"WebSocketTransport.decode(): Unexpected exception handling channel message: {e}"
                    )
        except (ConnectionClosedOK, GeneratorExit):
            # ConnectionClosedOK: normal websocket closure
            # GeneratorExit: coroutine being closed (e.g., during event loop shutdown)
            return

    def decode_raw_websocket_frame(self, raw: str | bytes) -> dict:
        if self.format == 'msgpack':
            return msgpack.unpackb(raw, raw=False)
        return json.loads(raw)

    def on_protcol_message_handled(self, task):
        try:
            exception = task.exception()
        except Exception as e:
            exception = e
        if exception is not None:
            log.exception(f"WebSocketTransport.on_protocol_message_handled(): uncaught exception: {exception}")

    def on_read_loop_done(self, task: asyncio.Task):
        try:
            exception = task.exception()
        except asyncio.CancelledError as e:
            exception = e
        if isinstance(exception, ConnectionClosedOK):
            return

    async def dispose(self):
        self.is_disposed = True

        # Cancel tasks but don't await them yet to avoid deadlock
        tasks_to_await = []

        if self.read_loop:
            self.read_loop.cancel()
            tasks_to_await.append(self.read_loop)
        if self.ws_connect_task:
            self.ws_connect_task.cancel()
            tasks_to_await.append(self.ws_connect_task)
        if self.idle_timer:
            self.idle_timer.cancel()

        # Schedule cleanup of cancelled tasks in the background to avoid blocking dispose()
        # This prevents deadlock when dispose() is called from within these tasks
        if tasks_to_await:
            asyncio.create_task(self._cleanup_tasks(tasks_to_await))

        if self.websocket:
            try:
                await self.websocket.close()
            except asyncio.CancelledError:
                return

    async def _cleanup_tasks(self, tasks):
        """Wait for cancelled tasks to complete their cleanup."""
        for task in tasks:
            try:
                await task
            except Exception:
                pass  # Ignore all exceptions from cancelled/failed tasks

    async def close(self):
        await self.send({'action': ProtocolMessageAction.CLOSE})

    async def send(self, message: dict):
        if self.websocket is None:
            raise Exception()
        # Encode based on format
        if self.format == 'msgpack':
            raw_msg = msgpack.packb(message, use_bin_type=True)
            log.info(f'WebSocketTransport.send(): sending msgpack message (length: {len(raw_msg)} bytes)')
        else:
            raw_msg = json.dumps(message)
            log.info(f'WebSocketTransport.send(): sending {raw_msg}')
        await self.websocket.send(raw_msg)

    def set_idle_timer(self, timeout: float):
        if self.idle_timer:
            self.idle_timer.cancel()
        self.idle_timer = Timer(timeout, self.on_idle_timer_expire)

    async def on_idle_timer_expire(self):
        self.idle_timer = None
        since_last = unix_time_ms() - self.last_activity
        time_remaining = self.max_idle_interval - since_last
        msg = f"No activity seen from realtime in {since_last} ms; assuming connection has dropped"
        if time_remaining <= 0:
            log.error(msg)
            await self.disconnect(AblyException(msg, 408, 80003))
        else:
            self.set_idle_timer(time_remaining + 100)

    def on_activity(self):
        if not self.max_idle_interval:
            return
        self.last_activity = unix_time_ms()
        self.set_idle_timer(self.max_idle_interval + 100)

    async def disconnect(self, reason=None):
        await self.dispose()
        self.connection_manager.deactivate_transport(reason)
