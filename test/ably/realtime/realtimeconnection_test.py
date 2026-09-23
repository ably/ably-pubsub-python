import asyncio
import time

import pytest
from websockets import connect as _ws_connect

try:
    # websockets 15+ preferred import
    from websockets.asyncio.server import serve as ws_serve
except ImportError:
    # websockets 14 and earlier fallback
    from websockets.server import serve as ws_serve

from ably.realtime.connection import ConnectionEvent, ConnectionState
from ably.transport.defaults import Defaults
from ably.transport.websockettransport import ProtocolMessageAction
from ably.util.exceptions import AblyException
from test.ably.testapp import TestApp
from test.ably.utils import BaseAsyncTestCase


async def _relay(src, dst):
    try:
        async for msg in src:
            await dst.send(msg)
    except Exception:
        pass


class WsProxy:
    """Local WS proxy that forwards to real Ably and lets tests trigger a normal close."""

    def __init__(self, target_host: str):
        self.target_host = target_host
        self.server = None
        self.port: int | None = None
        self._close_event: asyncio.Event | None = None

    async def _handler(self, client_ws):
        # Create a fresh event for this connection; signal to drop the connection cleanly
        self._close_event = asyncio.Event()
        path = client_ws.request.path  # e.g. "/?key=...&format=json"
        target_url = f"wss://{self.target_host}{path}"
        try:
            async with _ws_connect(target_url, ping_interval=None) as server_ws:
                c2s = asyncio.create_task(_relay(client_ws, server_ws))
                s2c = asyncio.create_task(_relay(server_ws, client_ws))
                close_task = asyncio.create_task(self._close_event.wait())
                try:
                    await asyncio.wait([c2s, s2c, close_task], return_when=asyncio.FIRST_COMPLETED)
                finally:
                    c2s.cancel()
                    s2c.cancel()
                    close_task.cancel()
        except Exception:
            pass
        # After _handler returns the websockets server sends a normal close frame (1000)

    async def close_active_connection(self):
        """Trigger a normal WS close (code 1000) on the currently active client connection.

        Signals the handler to exit; the websockets server framework then sends the
        close frame automatically when the handler coroutine returns.
        """
        if self._close_event:
            self._close_event.set()

    @property
    def endpoint(self) -> str:
        """Host to pass to AblyRealtime (combine with tls=False and port=self.port)."""
        return "127.0.0.1"

    async def __aenter__(self):
        self.server = await ws_serve(self._handler, "127.0.0.1", 0, ping_interval=None)
        self.port = self.server.sockets[0].getsockname()[1]
        return self

    async def __aexit__(self, *args):
        if self.server:
            self.server.close()
            await self.server.wait_closed()


class TestRealtimeConnection(BaseAsyncTestCase):
    @pytest.fixture(autouse=True)
    async def setup(self):
        self.test_vars = await TestApp.get_test_vars()
        self.valid_key_format = "api:key"

    async def test_connection_state(self):
        ably = await TestApp.get_ably_realtime(auto_connect=False)
        assert ably.connection.state == ConnectionState.INITIALIZED
        ably.connect()
        await ably.connection.once_async()
        assert ably.connection.state == ConnectionState.CONNECTING
        await ably.connection.once_async()
        assert ably.connection.state == ConnectionState.CONNECTED
        await ably.close()
        assert ably.connection.state == ConnectionState.CLOSED

    async def test_connection_state_is_connecting_on_init(self):
        ably = await TestApp.get_ably_realtime()
        assert ably.connection.state == ConnectionState.CONNECTING
        await ably.close()

    async def test_auth_invalid_key(self):
        ably = await TestApp.get_ably_realtime(key=self.valid_key_format)
        state_change = await ably.connection.once_async()
        assert ably.connection.state == ConnectionState.FAILED
        assert state_change.reason
        assert state_change.reason.code == 40101
        assert state_change.reason.status_code == 401
        assert ably.connection.error_reason
        assert ably.connection.error_reason.code == 40101
        assert ably.connection.error_reason.status_code == 401
        await ably.close()

    async def test_connection_ping_connected(self):
        ably = await TestApp.get_ably_realtime()
        await asyncio.wait_for(ably.connection.once_async(ConnectionState.CONNECTED), timeout=5)
        response_time_ms = await ably.connection.ping()
        assert response_time_ms is not None
        assert type(response_time_ms) is float
        await ably.close()

    async def test_connection_ping_initialized(self):
        ably = await TestApp.get_ably_realtime(auto_connect=False)
        assert ably.connection.state == ConnectionState.INITIALIZED
        with pytest.raises(AblyException) as exception:
            await ably.connection.ping()
        assert exception.value.code == 40000
        assert exception.value.status_code == 400

    async def test_connection_ping_failed(self):
        ably = await TestApp.get_ably_realtime(key=self.valid_key_format)
        await ably.connection.once_async(ConnectionState.FAILED)
        assert ably.connection.state == ConnectionState.FAILED
        with pytest.raises(AblyException) as exception:
            await ably.connection.ping()
        assert exception.value.code == 40000
        assert exception.value.status_code == 400
        await ably.close()

    async def test_connection_ping_closed(self):
        ably = await TestApp.get_ably_realtime()
        ably.connect()
        await asyncio.wait_for(ably.connection.once_async(ConnectionState.CONNECTED), timeout=5)
        await ably.close()
        with pytest.raises(AblyException) as exception:
            await ably.connection.ping()
        assert exception.value.code == 40000
        assert exception.value.status_code == 400

    async def test_auto_connect(self):
        ably = await TestApp.get_ably_realtime()
        connect_future = asyncio.Future()
        ably.connection.on(ConnectionState.CONNECTED, lambda change: connect_future.set_result(change))
        await connect_future
        assert ably.connection.state == ConnectionState.CONNECTED
        await ably.close()

    async def test_connection_state_change(self):
        ably = await TestApp.get_ably_realtime()

        connected_future = asyncio.Future()

        def on_state_change(change):
            connected_future.set_result(change)

        ably.connection.on(ConnectionState.CONNECTED, on_state_change)

        state_change = await connected_future
        assert state_change.previous == ConnectionState.CONNECTING
        assert state_change.current == ConnectionState.CONNECTED
        await ably.close()

    async def test_connection_state_change_reason(self):
        ably = await TestApp.get_ably_realtime(key=self.valid_key_format)

        state_change = await ably.connection.once_async()

        assert state_change.previous == ConnectionState.CONNECTING
        assert state_change.current == ConnectionState.FAILED
        assert ably.connection.error_reason is not None
        assert ably.connection.error_reason is state_change.reason
        await ably.close()

    async def test_realtime_request_timeout_connect(self):
        ably = await TestApp.get_ably_realtime(realtime_request_timeout=0.000001)
        state_change = await ably.connection.once_async()
        assert state_change.reason is not None
        assert state_change.reason.code == 50003
        assert state_change.reason.status_code == 504
        assert ably.connection.state == ConnectionState.DISCONNECTED
        assert ably.connection.error_reason == state_change.reason
        await ably.close()

    async def test_realtime_request_timeout_ping(self):
        ably = await TestApp.get_ably_realtime(realtime_request_timeout=2000)
        await asyncio.wait_for(ably.connection.once_async(ConnectionState.CONNECTED), timeout=5)

        original_send_protocol_message = ably.connection.connection_manager.send_protocol_message

        async def new_send_protocol_message(protocol_message):
            if protocol_message.get('action') == ProtocolMessageAction.HEARTBEAT:
                return
            await original_send_protocol_message(protocol_message)

        ably.connection.connection_manager.send_protocol_message = new_send_protocol_message

        with pytest.raises(AblyException) as exception:
            await ably.connection.ping()

        assert exception.value.code == 50003
        assert exception.value.status_code == 504

        # one timed-out ping must not break later pings
        ably.connection.connection_manager.send_protocol_message = original_send_protocol_message
        response_time_ms = await asyncio.wait_for(ably.connection.ping(), timeout=5)
        assert type(response_time_ms) is float
        await ably.close()

    async def test_ping_after_invalid_state_ping(self):
        # a ping rejected for bad state must not break later pings
        ably = await TestApp.get_ably_realtime(auto_connect=False)
        with pytest.raises(AblyException) as exception:
            await ably.connection.ping()
        assert exception.value.code == 40000

        ably.connect()
        await asyncio.wait_for(ably.connection.once_async(ConnectionState.CONNECTED), timeout=5)
        response_time_ms = await asyncio.wait_for(ably.connection.ping(), timeout=5)
        assert type(response_time_ms) is float
        await ably.close()

    async def test_ping_survives_connection_drop(self):
        # RTN13d: a heartbeat lost with a dropped connection is sent again once the connection is
        # back, rather than the ping failing or waiting out realtime_request_timeout
        outage_secs = 1
        async with WsProxy(self.test_vars["host"]) as proxy:
            ably = await TestApp.get_ably_realtime(
                realtime_request_timeout=20000,
                tls=False,
                endpoint=proxy.endpoint,
                port=proxy.port,
            )
            try:
                await asyncio.wait_for(ably.connection.once_async(ConnectionState.CONNECTED), timeout=10)

                connection_manager = ably.connection.connection_manager
                original_send_protocol_message = connection_manager.send_protocol_message

                async def drop_heartbeats(protocol_message):
                    if protocol_message.get('action') == ProtocolMessageAction.HEARTBEAT:
                        return
                    await original_send_protocol_message(protocol_message)

                connection_manager.send_protocol_message = drop_heartbeats
                ping_start_time = time.monotonic()
                ping = asyncio.ensure_future(ably.connection.ping())
                await asyncio.sleep(outage_secs)
                assert not ping.done()

                # Simulate server sending a normal WS close frame
                connection_manager.send_protocol_message = original_send_protocol_message
                await proxy.close_active_connection()

                response_time_ms = await asyncio.wait_for(ping, timeout=15)
                elapsed_ms = (time.monotonic() - ping_start_time) * 1000
                assert type(response_time_ms) is float
                # the round trip is measured from the heartbeat that was sent on reconnection,
                # so it excludes the time spent waiting for the connection
                assert response_time_ms < elapsed_ms - outage_secs * 1000
            finally:
                await ably.close()

    async def test_ping_fails_when_connection_closes(self):
        # RTN13b: a ping cannot complete once the connection has transitioned to CLOSING
        ably = await TestApp.get_ably_realtime(realtime_request_timeout=20000)
        await asyncio.wait_for(ably.connection.once_async(ConnectionState.CONNECTED), timeout=5)

        connection_manager = ably.connection.connection_manager
        original_send_protocol_message = connection_manager.send_protocol_message

        async def drop_heartbeats(protocol_message):
            if protocol_message.get('action') == ProtocolMessageAction.HEARTBEAT:
                return
            await original_send_protocol_message(protocol_message)

        connection_manager.send_protocol_message = drop_heartbeats
        ping = asyncio.ensure_future(ably.connection.ping())
        await asyncio.sleep(0.5)
        assert not ping.done()

        await ably.close()

        with pytest.raises(AblyException) as exception:
            await asyncio.wait_for(ping, timeout=5)
        assert exception.value.code == 80017
        assert exception.value.status_code == 400

    async def test_ping_while_connecting(self):
        # RTN13d: a ping requested while connecting is done once the connection is established
        ably = await TestApp.get_ably_realtime(auto_connect=False)
        ably.connect()
        assert ably.connection.state == ConnectionState.CONNECTING
        response_time_ms = await asyncio.wait_for(ably.connection.ping(), timeout=15)
        assert type(response_time_ms) is float
        await ably.close()

    async def test_concurrent_pings(self):
        ably = await TestApp.get_ably_realtime()
        await asyncio.wait_for(ably.connection.once_async(ConnectionState.CONNECTED), timeout=5)
        results = await asyncio.wait_for(
            asyncio.gather(ably.connection.ping(), ably.connection.ping(), ably.connection.ping()), timeout=5
        )
        assert all(type(response_time_ms) is float for response_time_ms in results)
        await ably.close()

    async def test_disconnected_retry_timeout(self):
        ably = await TestApp.get_ably_realtime(disconnected_retry_timeout=2000, auto_connect=False)
        original_connect = ably.connection.connection_manager.connect_base
        call_count = 0

        # intercept the library connection mechanism to fail the first two connection attempts
        async def new_connect():
            nonlocal call_count
            if call_count < 2:
                ably.connection.connection_manager.notify_state(ConnectionState.DISCONNECTED)
                call_count += 1
            else:
                await original_connect()

        ably.connection.connection_manager.connect_base = new_connect

        ably.connect()

        await ably.connection.once_async(ConnectionState.DISCONNECTED)

        # Test that the library eventually connects after two failed attempts
        await asyncio.wait_for(ably.connection.once_async(ConnectionState.CONNECTED), timeout=5)

        await ably.close()

    async def test_connectivity_check_default(self):
        ably = await TestApp.get_ably_realtime(auto_connect=False)
        # The default connectivity check should return True
        assert ably.connection.connection_manager.check_connection() is True

    async def test_connectivity_check_non_default(self):
        ably = await TestApp.get_ably_realtime(
            connectivity_check_url="https://echo.ably.io/respondWith?status=200", auto_connect=False)
        # A non-default URL should return True with a HTTP OK despite not returning "Yes" in the body
        assert ably.connection.connection_manager.check_connection() is True

    async def test_connectivity_check_bad_status(self):
        ably = await TestApp.get_ably_realtime(
            connectivity_check_url="https://echo.ably.io/respondWith?status=400", auto_connect=False)
        # Should return False when the URL returns a non-2xx response code
        assert ably.connection.connection_manager.check_connection() is False

    async def test_unroutable_host(self):
        ably = await TestApp.get_ably_realtime(endpoint="10.255.255.1", realtime_request_timeout=3000)
        state_change = await ably.connection.once_async()
        assert state_change.reason
        assert state_change.reason.code == 50003
        assert state_change.reason.status_code == 504
        assert ably.connection.state == ConnectionState.DISCONNECTED
        assert ably.connection.error_reason == state_change.reason
        await ably.close()

    async def test_invalid_host(self):
        ably = await TestApp.get_ably_realtime(endpoint="iamnotahost")
        state_change = await ably.connection.once_async()
        assert state_change.reason
        assert state_change.reason.code == 40000
        assert state_change.reason.status_code == 400
        assert ably.connection.state == ConnectionState.DISCONNECTED
        assert ably.connection.error_reason == state_change.reason
        await ably.close()

    async def test_connection_state_ttl(self):
        Defaults.connection_state_ttl = 10
        ably = await TestApp.get_ably_realtime()

        state_change = await ably.connection.once_async()

        assert state_change.previous == ConnectionState.CONNECTING
        assert state_change.current == ConnectionState.SUSPENDED
        assert state_change.reason
        assert state_change.reason.code == 80002
        assert state_change.reason.status_code == 400
        assert ably.connection.connection_details is None
        await ably.close()

        Defaults.connection_state_ttl = 120000

    async def test_handle_connected(self):
        ably = await TestApp.get_ably_realtime()
        test_future = asyncio.Future()

        def on_update(connection_state):
            if connection_state.event == ConnectionEvent.UPDATE:
                test_future.set_result(connection_state)

        ably.connection.on(ConnectionEvent.UPDATE, on_update)

        async def on_transport_pending(transport):
            await transport.on_protocol_message({'action': 4, "connectionDetails": {"connectionStateTtl": 200}})

        ably.connection.connection_manager.on('transport.pending', on_transport_pending)

        state_change = await test_future

        assert state_change.previous == ConnectionState.CONNECTED
        assert state_change.current == ConnectionState.CONNECTED
        assert state_change.event == ConnectionEvent.UPDATE
        await ably.close()

    async def test_max_idle_interval(self):
        ably = await TestApp.get_ably_realtime(realtime_request_timeout=2000)

        def on_transport_pending(transport):
            original_on_protocol_message = transport.on_protocol_message

            async def on_protocol_message(msg):
                if msg["action"] == ProtocolMessageAction.CONNECTED:
                    msg["connectionDetails"]["maxIdleInterval"] = 100

                await original_on_protocol_message(msg)

            transport.on_protocol_message = on_protocol_message

        ably.connection.connection_manager.on('transport.pending', on_transport_pending)

        state_change = await ably.connection.once_async(ConnectionState.DISCONNECTED)

        assert state_change.previous == ConnectionState.CONNECTED
        assert state_change.current == ConnectionState.DISCONNECTED
        assert state_change.reason.code == 80003
        assert state_change.reason.status_code == 408

        await ably.close()

    # RTN15a
    async def test_retry_immediately_upon_unexpected_disconnection(self):
        # Set timeouts to 500s so that if the client uses retry delay the test will fail with a timeout
        ably = await TestApp.get_ably_realtime(
            disconnected_retry_timeout=500_000,
            suspended_retry_timeout=500_000
        )

        # Wait for the client to connect
        await asyncio.wait_for(ably.connection.once_async(ConnectionState.CONNECTED), timeout=5)

        # Simulate random loss of connection
        assert ably.connection.connection_manager.transport
        await ably.connection.connection_manager.transport.dispose()
        ably.connection.connection_manager.notify_state(ConnectionState.DISCONNECTED)
        assert ably.connection.state == ConnectionState.DISCONNECTED

        # Wait for the client to connect again
        await asyncio.wait_for(ably.connection.once_async(ConnectionState.CONNECTED), timeout=5)
        await ably.close()

    async def test_fallback_host(self):
        ably = await TestApp.get_ably_realtime()

        await ably.connection.connection_manager.once_async('transport.pending')
        assert ably.connection.connection_manager.transport
        ably.connection.connection_manager.transport._emit('failed', AblyException("test exception", 502, 50200))

        await asyncio.wait_for(ably.connection.once_async(ConnectionState.CONNECTED), timeout=5)

        assert ably.connection.connection_manager.transport.host != self.test_vars["host"]
        assert ably.options.fallback_host != self.test_vars["host"]
        await ably.close()

    async def test_fallback_host_no_connection(self):
        ably = await TestApp.get_ably_realtime()

        await ably.connection.connection_manager.once_async('transport.pending')
        assert ably.connection.connection_manager.transport

        def check_connection():
            return False

        ably.connection.connection_manager.check_connection = check_connection

        asyncio.create_task(ably.connection.connection_manager.transport.on_protocol_message({
            "action": ProtocolMessageAction.DISCONNECTED,
            "error": {
                "statusCode": 502,
                "code": 50200,
                "message": "test exception"
            }
        }))

        await ably.connection.once_async(ConnectionState.DISCONNECTED)

        assert ably.options.fallback_host is None
        await ably.close()

    async def test_fallback_host_disconnected_protocol_msg(self):
        ably = await TestApp.get_ably_realtime()

        await ably.connection.connection_manager.once_async('transport.pending')
        assert ably.connection.connection_manager.transport
        asyncio.create_task(ably.connection.connection_manager.transport.on_protocol_message({
            "action": ProtocolMessageAction.DISCONNECTED,
            "error": {
                "statusCode": 502,
                "code": 50200,
                "message": "test exception"
            }
        }))

        await asyncio.wait_for(ably.connection.once_async(ConnectionState.CONNECTED), timeout=5)

        assert ably.connection.connection_manager.transport.host != self.test_vars["host"]
        assert ably.options.fallback_host != self.test_vars["host"]
        await ably.close()

    #  RTN2d
    async def test_connection_null_client_id_query_params(self):
        rest = await TestApp.get_ably_rest()

        token_details = await rest.auth.request_token()

        realtime = await TestApp.get_ably_realtime(token_details=token_details)

        await realtime.connection.once_async(ConnectionState.CONNECTED)
        assert realtime.connection.connection_manager.transport.params.get("client_id") is None
        assert realtime.auth.client_id is None

        await realtime.close()
        await rest.close()

    async def test_connection_client_id_query_params(self):
        client_id = 'test_client_id'

        ably = await TestApp.get_ably_realtime(client_id=client_id)

        await asyncio.wait_for(ably.connection.once_async(ConnectionState.CONNECTED), timeout=5)
        assert ably.connection.connection_manager.transport.params["clientId"] == client_id
        assert ably.auth.client_id == client_id

        await ably.close()

    async def test_lost_connection_lifecycle(self):
        ably = await TestApp.get_ably_realtime(realtime_request_timeout=2000, disconnected_retry_timeout=2000)

        # when client connectivity is lost, the transport will become aware of a connectivity issue
        # when it stops seeing activity from realtime within maxIdleInterval, therefore setting the max idle
        # interval arbitrarily low will simulate client behaviour when connectivity is lost.
        def on_transport_pending(transport):
            original_on_protocol_message = transport.on_protocol_message

            async def on_protocol_message(msg):
                if msg["action"] == ProtocolMessageAction.CONNECTED:
                    msg["connectionDetails"]["maxIdleInterval"] = 1000

                await original_on_protocol_message(msg)

            transport.on_protocol_message = on_protocol_message

        ably.connection.connection_manager.once('transport.pending', on_transport_pending)

        # should transition to disconnected due to lack of activity from realtime
        await ably.connection.once_async(ConnectionState.DISCONNECTED)

        # should re-establish connection after disconnected_retry_timeout
        await asyncio.wait_for(ably.connection.once_async(ConnectionState.CONNECTED), timeout=5)

        await ably.close()

    # RTN2f - Test msgpack format parameter when use_binary_protocol is enabled
    async def test_connection_format_msgpack_with_binary_protocol(self):
        """Test that format=msgpack is sent when use_binary_protocol=True"""
        ably = await TestApp.get_ably_realtime(use_binary_protocol=True)
        await asyncio.wait_for(ably.connection.once_async(ConnectionState.CONNECTED), timeout=5)

        received_raw_websocket_frames = []
        transport = ably.connection.connection_manager.transport
        original_decode_raw_websocket_frame = transport.decode_raw_websocket_frame

        def intercepted_websocket_frame(data):
            received_raw_websocket_frames.append(data)
            return original_decode_raw_websocket_frame(data)

        transport.decode_raw_websocket_frame = intercepted_websocket_frame

        # Verify transport has format set to msgpack
        assert ably.connection.connection_manager.transport is not None
        assert ably.connection.connection_manager.transport.format == 'msgpack'

        # Verify params include format=msgpack
        assert ably.connection.connection_manager.transport.params.get('format') == 'msgpack'

        await ably.channels.get('connection_test').publish('test', b'test')

        assert len(received_raw_websocket_frames) > 0
        assert all(isinstance(frame, bytes) for frame in received_raw_websocket_frames)

        await ably.close()

    async def test_connection_format_json_without_binary_protocol(self):
        """Test that format defaults to json when use_binary_protocol=False"""
        ably = await TestApp.get_ably_realtime(use_binary_protocol=False)
        await asyncio.wait_for(ably.connection.once_async(ConnectionState.CONNECTED), timeout=5)

        received_raw_websocket_frames = []
        transport = ably.connection.connection_manager.transport
        original_decode_raw_websocket_frame = transport.decode_raw_websocket_frame

        def intercepted_websocket_frame(data):
            received_raw_websocket_frames.append(data)
            return original_decode_raw_websocket_frame(data)

        transport.decode_raw_websocket_frame = intercepted_websocket_frame

        # Verify transport has format set to json (default)
        assert ably.connection.connection_manager.transport is not None
        assert ably.connection.connection_manager.transport.format == 'json'

        await ably.channels.get('connection_test').publish('test', b'test')

        # Verify params don't include format parameter (or it's json)
        transport_format = ably.connection.connection_manager.transport.params.get('format')
        assert transport_format is None or transport_format == 'json'

        assert len(received_raw_websocket_frames) > 0
        assert all(isinstance(frame, str) for frame in received_raw_websocket_frames)

        await ably.close()

    # TO3g
    async def test_queue_messages_defaults_to_true(self):
        """TO3g: Verify that queueMessages client option defaults to true"""
        ably = await TestApp.get_ably_realtime(auto_connect=False)

        # TO3g: queueMessages defaults to true
        assert ably.options.queue_messages is True
        assert ably.connection.connection_manager.options.queue_messages is True

    async def test_normal_ws_close_triggers_immediate_reconnection(self):
        """Server normal WS close (code 1000) must trigger immediate reconnection.

        Regression test: ConnectionClosedOK was silently swallowed and deactivate_transport
        was never called, leaving the client disconnected until the idle timer fired.
        """
        async with WsProxy(self.test_vars["host"]) as proxy:
            ably = await TestApp.get_ably_realtime(
                disconnected_retry_timeout=500_000,
                suspended_retry_timeout=500_000,
                tls=False,
                endpoint=proxy.endpoint,
                port=proxy.port,
            )

            try:
                await asyncio.wait_for(
                    ably.connection.once_async(ConnectionState.CONNECTED), timeout=10
                )

                # Simulate server sending a normal WS close frame
                await proxy.close_active_connection()

                # Must go CONNECTING quickly — not after the 25 s idle timer
                await asyncio.wait_for(
                    ably.connection.once_async(ConnectionState.CONNECTING), timeout=1
                )

                # Must reconnect immediately — not after the 500 s retry timer
                await asyncio.wait_for(
                    ably.connection.once_async(ConnectionState.CONNECTED), timeout=10
                )
            finally:
                await ably.close()
