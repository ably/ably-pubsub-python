"""A stand-in for the websocket layer, implementing the ``mock_websocket``
helper that the Universal Test Specifications are written against.

The contract lives in ``uts/realtime/unit/helpers/mock_websocket.md`` in the
ably/specification repository. Names here match the pseudocode, which reserves
snake_case for test-harness constructs.

A test builds a `MockWebSocket`, hands it to `realtime_client()`, and drives
the client either from handlers set on the mock or from the `await_*` family,
which return an awaitable registered at call time so the next event can be
waited for before the current one is answered.

Every connection attempt surfaces as a `PendingConnection` the test responds
to. A successful response yields a `MockConnection`, which is the object the
library holds as its websocket: frames the test injects reach the client's read
loop, and frames the client sends reach the test.
"""

import asyncio
import copy
import json
import socket
import time
from enum import Enum

import httpx
import msgpack
from websockets.exceptions import WebSocketException

from ably.transport.websockettransport import ProtocolMessageAction
from test.uts.helpers.mock_http import RecordedUrl

MSGPACK_PROTOCOL = 'application/x-msgpack'
JSON_PROTOCOL = 'application/json'

# How long an `await_*` call waits before failing the test. The specifications
# quote timeouts in seconds; so does `mock_http`.
DEFAULT_AWAIT_TIMEOUT = 5.0

# PING and PONG are protocol.md actions 22 and 23. `ProtocolMessageAction` stops
# at ANNOTATION, so the values are named here.
PING_ACTION = 22
PONG_ACTION = 23

# The close code the library's own close path produces, which `websockets`
# defaults to and the specifications quote as "1000 for normal closure".
NORMAL_CLOSURE = 1000


class MockEventType(Enum):
    """The kinds of event the unified timeline records."""

    CONNECTION_ATTEMPT = 'connection_attempt'
    CONNECTION_SUCCESS = 'connection_success'
    CONNECTION_FAILURE = 'connection_failure'
    MESSAGE_FROM_CLIENT = 'message_from_client'
    MESSAGE_TO_CLIENT = 'message_to_client'
    PING_FRAME = 'ping_frame'
    SERVER_DISCONNECT = 'server_disconnect'
    CLIENT_CLOSE = 'client_close'


class MockEvent:
    """One entry in the timeline, carrying whatever the event is about."""

    def __init__(self, type, data=None):
        self.type = type
        self.timestamp = time.time()
        self.data = data

    def __repr__(self):
        return f'MockEvent({self.type.name}, {self.data!r})'


class ClientCloseEvent:
    """The close the library asked the websocket for."""

    def __init__(self, code=None, reason=None):
        self.code = code
        self.reason = reason

    def __repr__(self):
        return f'ClientCloseEvent(code={self.code!r}, reason={self.reason!r})'


class MockWebSocketClosed(WebSocketException):
    """An abnormal close of the transport, as `websockets` would report one.

    Subclassing `WebSocketException` is what puts it on the library's transport
    failure path; anything else escapes `ws_read_loop` uncaught.
    """

    def __init__(self, message, code=None, reason=None, error=None):
        super().__init__(message)
        self.code = code
        self.reason = reason
        self.error = error


class _ServerClose:
    """The sentinel a server-side close puts on a connection's inbox."""

    def __init__(self, failure=None):
        self.failure = failure


class MockConnection:
    """An established connection, from both sides.

    The test's side injects frames with `send_to_client` and ends the
    connection with `send_to_client_and_close` or `simulate_disconnect`. The
    library's side is `__aiter__`, `send` and `close` — the whole surface
    `WebSocketTransport` uses.

    Frames the test injects are queued and only drained once the library starts
    its read loop, so a message injected from a connection handler arrives
    after the library has stored the connection.
    """

    def __init__(self, mock, protocol):
        self.protocol = protocol
        self.timestamp = time.time()
        self.closed = False
        self.close_event = None
        self.__mock = mock
        self.__inbox = asyncio.Queue()

    # Server side: what the test drives

    def send_to_client(self, message):
        """Delivers `message` to the client, leaving the connection open."""
        self.__mock._record(MockEventType.MESSAGE_TO_CLIENT, message)
        self.__inbox.put_nowait(self.__encode(message))

    def send_to_client_and_close(self, message):
        """Delivers `message` and then closes the connection, as the server
        does whenever it sends DISCONNECTED or a connection-level ERROR."""
        self.send_to_client(message)
        self.__server_close(None)

    def simulate_disconnect(self, error=None):
        """Ends the connection without a protocol message.

        With no `error` the transport closes normally, which the library reads
        as the server going away. With one, the read loop fails, and `error`
        becomes the reason on the resulting state change.
        """
        failure = None
        if error is not None:
            failure = MockWebSocketClosed(f'Connection closed: {error}', error=error)
        self.__server_close(failure)

    def send_ping_frame(self):
        """Records a websocket ping frame from the server.

        `WebSocketTransport` has no ping hook, so nothing observable follows;
        see the mock infrastructure limitation in
        [deviations.md](../deviations.md).
        """
        self.__mock._record(MockEventType.PING_FRAME, self)

    # Library side: what `WebSocketTransport` calls

    async def __aiter__(self):
        while True:
            frame = await self.__inbox.get()
            if isinstance(frame, _ServerClose):
                if frame.failure is not None:
                    raise frame.failure
                return
            yield frame

    async def send(self, raw):
        """Receives a frame the client sent.

        A frame sent after the connection closed is still recorded rather than
        raising, so that a test can assert on the CLOSE message the library
        sends while tearing the connection down.
        """
        self.__mock._on_frame_from_client(self, raw)

    async def close(self, code=NORMAL_CLOSURE, reason=None):
        """Closes the connection at the library's request.

        The close notification reaches the read loop on a later turn of the
        event loop, never inline, matching a real websocket where iteration
        ends from the stream rather than from the `close()` call.
        """
        if self.closed:
            return
        self.closed = True
        self.close_event = ClientCloseEvent(code, reason)
        self.__mock._on_client_close(self, self.close_event)
        self.__inbox.put_nowait(_ServerClose(None))

    # Internals

    def _decode(self, raw):
        if self.protocol == MSGPACK_PROTOCOL:
            return msgpack.unpackb(raw, raw=False)
        return json.loads(raw)

    def __encode(self, message):
        # A message given already encoded is passed through as the test wrote
        # it, so a specification can pin the wire format itself
        if isinstance(message, (bytes, str)):
            return message
        message = copy.deepcopy(message)
        if self.protocol == MSGPACK_PROTOCOL:
            return msgpack.packb(message, use_bin_type=True)
        return json.dumps(message)

    def __server_close(self, failure):
        if self.closed:
            return
        self.closed = True
        self.__mock._record(MockEventType.SERVER_DISCONNECT, failure)
        self.__inbox.put_nowait(_ServerClose(failure))

    def __repr__(self):
        return f'MockConnection(protocol={self.protocol!r}, closed={self.closed})'


class PendingConnection:
    """A connection attempt awaiting an outcome from the test.

    The server-side methods of `MockConnection` are also reachable here, so a
    handler can call `respond_with_success()` and then `send_to_client(...)` on
    the same object, as the specifications write it.
    """

    def __init__(self, mock, url, headers=None):
        self.url = RecordedUrl(httpx.URL(url))
        self.protocol = (MSGPACK_PROTOCOL if self.url.query_params.get('format') == 'msgpack'
                         else JSON_PROTOCOL)
        # httpx.Headers looks up case-insensitively, as the specifications expect
        self.headers = httpx.Headers(headers or {})
        self.timestamp = time.time()
        self.connection = MockConnection(mock, self.protocol)
        self.__mock = mock
        self.__outcome = asyncio.get_running_loop().create_future()

    def respond_with_success(self, connected_message=None):
        """Establishes the connection, then delivers `connected_message`.

        The connection completes first and the message is queued behind it, so
        the library has stored the connection before the message is processed.
        """
        if self.__settle(None) and connected_message is not None:
            self.connection.send_to_client(connected_message)

    def respond_with_refused(self):
        """Fails the attempt the way a refused TCP connection does.

        `websockets` lets `ConnectionRefusedError` through unwrapped, so this
        is what the library sees.
        """
        self.__settle(ConnectionRefusedError(
            f'Connection refused to {self.url.host}:{self.url.port}'))

    def respond_with_timeout(self):
        """Fails the attempt the way an unresponsive server does."""
        self.__settle(asyncio.TimeoutError(
            f'Connection to {self.url.host}:{self.url.port} timed out'))

    def respond_with_dns_error(self):
        """Fails the attempt the way an unresolvable host does."""
        self.__settle(socket.gaierror(
            socket.EAI_NONAME, f'Name resolution failed for {self.url.host}'))

    def respond_with_error(self, error_message, then_close=True):
        """Establishes the connection and has the server send an ERROR.

        `then_close` closes the transport behind the message, which is what the
        server does for a connection-level error.
        """
        if not self.__settle(None):
            return
        if then_close:
            self.connection.send_to_client_and_close(error_message)
        else:
            self.connection.send_to_client(error_message)

    # The server side of the connection this attempt produces

    def send_to_client(self, message):
        self.connection.send_to_client(message)

    def send_to_client_and_close(self, message):
        self.connection.send_to_client_and_close(message)

    def simulate_disconnect(self, error=None):
        self.connection.simulate_disconnect(error)

    def send_ping_frame(self):
        self.connection.send_ping_frame()

    def _outcome(self):
        return self.__outcome

    def _fail_with(self, exception):
        self.__settle(exception)

    def __settle(self, failure):
        if self.__outcome.done():
            return False
        self.__mock._record(
            MockEventType.CONNECTION_FAILURE if failure is not None
            else MockEventType.CONNECTION_SUCCESS, failure if failure is not None else self)
        self.__outcome.set_result(failure)
        return True

    def __repr__(self):
        return f'PendingConnection({str(self.url)!r})'


class MockWebSocket:
    """Serves the websocket connections a realtime client opens, in place of
    the network.

    Events reach the test one of two ways, in order of precedence: a waiter
    registered by an `await_*` call, or the matching handler. A connection
    attempt that neither covers succeeds with no messages, leaving the client
    connecting against a silent server.
    """

    def __init__(self, on_connection_attempt=None, on_message_from_client=None,
                 on_text_data_frame=None, on_binary_data_frame=None):
        # Handlers are reassignable, as some specifications set them per-phase
        self.on_connection_attempt = on_connection_attempt
        self.on_message_from_client = on_message_from_client
        self.on_text_data_frame = on_text_data_frame
        self.on_binary_data_frame = on_binary_data_frame
        self.events = []
        # Exceptions a test's handler raised, kept here rather than allowed to
        # escape into the library, where a `TypeError` would silently make
        # `ws_connect` retry with different keyword arguments
        self.handler_errors = []
        self.connections = []
        self.active_connection = None
        self.__connection_waiters = []
        self.__message_waiters = []
        self.__close_waiters = []

    def as_connect(self):
        """The callable to pass as `TestOptions(websocket_connect=...)`."""
        # `**kwargs` rather than a named `additional_headers`, because
        # `ws_connect` treats a `TypeError` from the call as a signal to retry
        # with `extra_headers` instead
        def connect(url, **kwargs):
            headers = kwargs.get('additional_headers') or kwargs.get('extra_headers')
            return _MockConnect(self, url, headers)
        return connect

    # The unified timeline, and the views onto it the specifications assert on

    @property
    def connection_attempts(self):
        """Every attempt the client made, in order."""
        return [event.data for event in self.events
                if event.type is MockEventType.CONNECTION_ATTEMPT]

    @property
    def messages_from_client(self):
        """Every decoded protocol message the client sent, in order."""
        return [event.data for event in self.events
                if event.type is MockEventType.MESSAGE_FROM_CLIENT]

    def events_of_type(self, type):
        return [event for event in self.events if event.type is type]

    # Message injection, against the connection most recently established

    def send_to_client(self, message):
        self.__require_connection().send_to_client(message)

    def send_to_client_and_close(self, message):
        self.__require_connection().send_to_client_and_close(message)

    def simulate_disconnect(self, error=None):
        self.__require_connection().simulate_disconnect(error)

    def send_ping_frame(self):
        self.__require_connection().send_ping_frame()

    # Awaitable event triggers. Each registers its waiter when called, so a
    # test can set up the next await before answering the current event.

    def await_connection_attempt(self, timeout=DEFAULT_AWAIT_TIMEOUT):
        return self.__await_event(
            self.__connection_waiters, timeout, 'Timeout waiting for connection attempt')

    def await_next_message_from_client(self, timeout=DEFAULT_AWAIT_TIMEOUT):
        return self.__await_event(
            self.__message_waiters, timeout, 'Timeout waiting for message from client')

    def await_client_close(self, timeout=DEFAULT_AWAIT_TIMEOUT):
        return self.__await_event(
            self.__close_waiters, timeout, 'Timeout waiting for client close')

    def reset(self):
        """Clears the timeline, the waiters and the recorded connections.

        A connection already established stays open; a test that wants it shut
        closes it first.
        """
        self.events.clear()
        self.handler_errors.clear()
        self.connections.clear()
        self.active_connection = None
        self.__connection_waiters.clear()
        self.__message_waiters.clear()
        self.__close_waiters.clear()

    # Internals

    def _record(self, type, data=None):
        event = MockEvent(type, data)
        self.events.append(event)
        return event

    def _on_connection_attempt(self, pending):
        self._record(MockEventType.CONNECTION_ATTEMPT, pending)
        waiter = self.__take_waiter(self.__connection_waiters)
        if waiter is not None:
            waiter.set_result(pending)
        elif self.on_connection_attempt is not None:
            if not self.__invoke(self.on_connection_attempt, pending):
                # A handler that raised has not answered the attempt. Failing
                # it here as a transport error reaches the library's failure
                # path at once, rather than leaving the test to hang out.
                pending._fail_with(MockWebSocketClosed(
                    f'mock_websocket handler raised {self.handler_errors[-1]!r}'))
        else:
            pending.respond_with_success()

    def _on_established(self, connection):
        self.connections.append(connection)
        self.active_connection = connection

    def _on_frame_from_client(self, connection, raw):
        message = connection._decode(raw)
        self._record(MockEventType.MESSAGE_FROM_CLIENT, message)
        # The raw frame hooks run in addition to the decoded handler, and
        # before it, as they see the frame before it is decoded
        if isinstance(raw, (bytes, bytearray)):
            if self.on_binary_data_frame is not None:
                self.__invoke(self.on_binary_data_frame, bytes(raw))
        elif self.on_text_data_frame is not None:
            self.__invoke(self.on_text_data_frame, raw)
        waiter = self.__take_waiter(self.__message_waiters)
        if waiter is not None:
            waiter.set_result(message)
        if self.on_message_from_client is not None:
            self.__invoke(self.on_message_from_client, message)

    def _on_client_close(self, connection, close_event):
        self._record(MockEventType.CLIENT_CLOSE, close_event)
        if self.active_connection is connection:
            self.active_connection = None
        waiter = self.__take_waiter(self.__close_waiters)
        if waiter is not None:
            waiter.set_result(close_event)

    def __require_connection(self):
        if self.active_connection is None:
            raise AssertionError('No connection has been established')
        return self.active_connection

    def __invoke(self, handler, argument):
        """Calls a test's handler, keeping whatever it raises out of the
        library's path. Returns whether it ran cleanly."""
        try:
            handler(argument)
        except Exception as error:
            self.handler_errors.append(error)
            return False
        return True

    def __await_event(self, waiters, timeout, message):
        waiter = asyncio.get_running_loop().create_future()
        waiters.append(waiter)

        async def wait():
            try:
                return await asyncio.wait_for(waiter, timeout)
            except asyncio.TimeoutError:
                raise AssertionError(self.__timeout_message(message)) from None

        return wait()

    def __timeout_message(self, message):
        if self.handler_errors:
            return f'{message}; a handler raised {self.handler_errors[0]!r}'
        return message

    @staticmethod
    def __take_waiter(waiters):
        while waiters:
            waiter = waiters.pop(0)
            if not waiter.done():
                return waiter
        return None


class _MockConnect:
    """The async context manager `websockets.connect` stands in for."""

    def __init__(self, mock, url, headers=None):
        self.__mock = mock
        self.__url = url
        self.__headers = headers
        self.__connection = None

    async def __aenter__(self):
        pending = PendingConnection(self.__mock, self.__url, self.__headers)
        self.__mock._on_connection_attempt(pending)
        failure = await pending._outcome()
        if failure is not None:
            raise failure
        self.__connection = pending.connection
        self.__mock._on_established(self.__connection)
        return self.__connection

    async def __aexit__(self, exc_type, exc, traceback):
        return False


# Protocol message templates, as named in the specification

CONNECTED_MESSAGE = {
    'action': int(ProtocolMessageAction.CONNECTED),
    'connectionId': 'test-connection-id',
    'connectionDetails': {
        'connectionKey': 'test-connection-key',
        'clientId': None,
        'connectionStateTtl': 120000,
        'maxIdleInterval': 15000,
    },
}

CLOSED_MESSAGE = {
    'action': int(ProtocolMessageAction.CLOSED),
}

# The specification's template carries no statusCode; `on_disconnected`
# compares it against 500 unguarded, so one is supplied here. See
# [deviations.md](../deviations.md).
DISCONNECTED_MESSAGE = {
    'action': int(ProtocolMessageAction.DISCONNECTED),
    'error': {'code': 80003, 'statusCode': 400, 'message': 'Connection disconnected'},
}

HEARTBEAT_MESSAGE = {
    'action': int(ProtocolMessageAction.HEARTBEAT),
}


def connected_message(connection_id='test-connection-id', **connection_details):
    """A CONNECTED message, with `connection_details` overriding the template's.

    The templates are shared dictionaries, so a test that needs its own
    `connectionDetails` — a small `maxIdleInterval`, say — builds one here
    rather than mutating `CONNECTED_MESSAGE`.
    """
    message = copy.deepcopy(CONNECTED_MESSAGE)
    message['connectionId'] = connection_id
    message['connectionDetails'].update(connection_details)
    return message


def ERROR_MESSAGE(code, message, status_code=None):  # noqa: N802 - the specification's name
    """An ERROR protocol message carrying `code`.

    The specification derives the status code as `code / 100`, which holds for
    the 4xxxx and 5xxxx ranges. The 8xxxx connection errors would yield 800, so
    they fall back to 500 unless `status_code` names one.
    """
    if status_code is None:
        derived = code // 100
        status_code = derived if derived < 600 else 500
    return {
        'action': int(ProtocolMessageAction.ERROR),
        'error': {'code': code, 'statusCode': status_code, 'message': message},
    }


def PING_MESSAGE(id):  # noqa: N802 - the specification's name
    return {'action': PING_ACTION, 'id': id}


CONNECTED_MESSAGE_NO_IDLE = connected_message(maxIdleInterval=0)
"""A CONNECTED message which leaves the transport's idle timer unscheduled.

The transport only sets the timer for a non-zero `maxIdleInterval`, so this is
what a test driving time with a `FakeClock` connects with: the idle timer
compares against the real clock and would otherwise fire on every advance.
"""


def attached_message(channel, **fields):
    """An ATTACHED message for `channel`."""
    return {'action': int(ProtocolMessageAction.ATTACHED), 'channel': channel, **fields}


def detached_message(channel, **fields):
    """A DETACHED message for `channel`."""
    return {'action': int(ProtocolMessageAction.DETACHED), 'channel': channel, **fields}


def server_detached_message(channel, code, message, status_code=None):
    """A DETACHED message carrying the error a server sends when it detaches a channel."""
    if status_code is None:
        derived = code // 100
        status_code = derived if derived < 600 else 500
    return detached_message(channel, error={'code': code, 'statusCode': status_code, 'message': message})


def contains_in_order(observed, expected):
    """Whether `expected` appears in `observed` in order, other entries allowed between.

    This is the specifications' `CONTAINS_IN_ORDER`, which they prefer to an
    equality check because a transient state may be passed through more than once.
    """
    remaining = list(expected)
    for item in observed:
        if remaining and item == remaining[0]:
            remaining.pop(0)
    return not remaining


async def await_protocol_messages(mock_websocket, action, count=1, timeout=5.0):
    """Waits until `count` protocol messages carrying `action` have left the client.

    An operation the server acknowledges is awaited on the client side, so a
    test driving one has nothing to wait on until it answers. This waits for the
    message to reach the mock so that the answer can be sent.
    """
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    wanted = int(action)
    while True:
        sent = [m for m in mock_websocket.messages_from_client if m.get('action') == wanted]
        if len(sent) >= count:
            return sent
        if loop.time() >= deadline:
            raise AssertionError(
                f'Timed out waiting for {count} messages with action {wanted}; {len(sent)} were sent')
        await asyncio.sleep(0)


async def await_published(mock_websocket, count=1, timeout=5.0):
    """Waits until `count` MESSAGE protocol messages have left the client."""
    return await await_protocol_messages(mock_websocket, ProtocolMessageAction.MESSAGE, count, timeout)


async def await_presence_sent(mock_websocket, count=1, timeout=5.0):
    """Waits until `count` PRESENCE protocol messages have left the client."""
    return await await_protocol_messages(mock_websocket, ProtocolMessageAction.PRESENCE, count, timeout)


def message_protocol_message(channel, messages, **fields):
    """A MESSAGE protocol message carrying `messages` on `channel`."""
    return {
        'action': int(ProtocolMessageAction.MESSAGE),
        'channel': channel,
        'messages': messages,
        **fields,
    }


def channel_error_message(channel, code, message, status_code=None):
    """An ERROR message scoped to `channel`, which the connection routes to it."""
    if status_code is None:
        derived = code // 100
        status_code = derived if derived < 600 else 500
    return {
        'action': int(ProtocolMessageAction.ERROR),
        'channel': channel,
        'error': {'code': code, 'statusCode': status_code, 'message': message},
    }
