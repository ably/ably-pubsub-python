"""A stand-in for the HTTP layer, implementing the ``mock_http`` helper that the
Universal Test Specifications are written against.

The contract lives in ``uts/rest/unit/helpers/mock_http.md`` in the
ably/specification repository. Names here match the pseudocode, which reserves
snake_case for test-harness constructs.

Every HTTP call surfaces as two events: a `PendingConnection`, and then, only
once that connection succeeds, a `PendingRequest`. Connection failures raise
transport exceptions and leave `captured_requests` untouched.
"""

import asyncio
import json
import time

import httpx
import msgpack

DEFAULT_PORTS = {'https': 443, 'http': 80, 'wss': 443, 'ws': 80}

MSGPACK_CONTENT_TYPE = 'application/x-msgpack'
JSON_CONTENT_TYPE = 'application/json'


class RecordedUrl:
    """The parts of a request URL that the specifications assert on."""

    def __init__(self, url):
        self.__url = url
        self.scheme = url.scheme
        # Hostname only, so that assertions on url.host ignore the port
        self.host = url.host
        self.port = url.port or DEFAULT_PORTS.get(url.scheme, 80)
        self.path = url.path
        # The path as it goes on the wire, for assertions about encoding, which
        # url.path cannot carry because it is decoded
        self.raw_path = url.raw_path.decode('ascii').split('?')[0]
        self.query_params = dict(url.params.items())

    def __str__(self):
        return str(self.__url)

    def __repr__(self):
        return f'RecordedUrl({str(self.__url)!r})'


class PendingConnection:
    """A connection attempt awaiting an outcome from the test."""

    def __init__(self, host, port, tls):
        self.host = host
        self.port = port
        self.tls = tls
        self.timestamp = time.time()
        self._outcome = asyncio.get_running_loop().create_future()

    def __settle(self, failure):
        if not self._outcome.done():
            self._outcome.set_result(failure)

    def respond_with_success(self):
        self.__settle(None)

    def respond_with_refused(self):
        self.__settle((httpx.ConnectError, f'Connection refused to {self.host}:{self.port}'))

    def respond_with_timeout(self):
        self.__settle((httpx.ConnectTimeout, f'Connection to {self.host}:{self.port} timed out'))

    def respond_with_dns_error(self):
        self.__settle((httpx.ConnectError, f'Name resolution failed for {self.host}'))


class PendingRequest:
    """A request awaiting a response from the test.

    Resolving it is independent of the handler that received it, so a handler
    may hold on to a request and respond to it later in the test.
    """

    def __init__(self, request):
        self._request = request
        self.method = request.method.upper()
        self.url = RecordedUrl(request.url)
        self.path = self.url.path
        # httpx.Headers looks up case-insensitively, as the specifications expect
        self.headers = request.headers
        self.body = request.content
        self.timestamp = time.time()
        self._outcome = asyncio.get_running_loop().create_future()

    def __settle(self, delay, response, error=None):
        if not self._outcome.done():
            self._outcome.set_result((delay, response, error))

    def respond_with(self, status, body=None, headers=None):
        self.__settle(0, self.__build_response(status, body, headers))

    def respond_with_delay(self, delay, status, body=None, headers=None):
        """Respond after `delay` milliseconds have passed."""
        self.__settle(delay / 1000.0, self.__build_response(status, body, headers))

    def respond_with_timeout(self):
        self.__settle(0, None, httpx.ReadTimeout(f'Request to {self.url} timed out',
                                                 request=self._request))

    def __build_response(self, status, body, headers):
        headers = dict(headers or {})
        content_type = next(
            (value for name, value in headers.items() if name.lower() == 'content-type'), None)

        if body is None:
            content = b''
        elif isinstance(body, (bytes, str)):
            # Bodies the test encoded itself are passed through as given
            content = body.encode('utf-8') if isinstance(body, str) else body
        else:
            if content_type is None:
                # Serialise a native body the way the client asked to receive it
                accept = self.headers.get('accept', '')
                content_type = MSGPACK_CONTENT_TYPE if 'x-msgpack' in accept else JSON_CONTENT_TYPE
                headers['Content-Type'] = content_type
            if 'x-msgpack' in content_type:
                content = msgpack.packb(body, use_bin_type=False)
            else:
                content = json.dumps(body, separators=(',', ':')).encode('utf-8')

        return httpx.Response(status, headers=headers, content=content)


class MockHttpClient:
    """Serves the HTTP requests a client makes, in place of the network.

    Requests reach the test one of three ways, in order of precedence: a
    pending `await_request` future, the `on_request` handler, or a queued
    response. A request none of those covers is answered with a 404.
    """

    def __init__(self, on_connection_attempt=None, on_request=None):
        # Handlers are reassignable, as some specifications set them per-phase
        self.on_connection_attempt = on_connection_attempt
        self.on_request = on_request
        self.captured_requests = []
        self.__connection_waiters = []
        self.__request_waiters = []
        self.__queued = []
        self.__queued_by_host = {}
        self.__queued_by_url = {}

    def as_transport(self):
        """The transport to pass as `TestOptions(http_transport=...)`."""
        return _MockTransport(self)

    def reset(self):
        self.captured_requests.clear()
        self.__connection_waiters.clear()
        self.__request_waiters.clear()
        self.__queued.clear()
        self.__queued_by_host.clear()
        self.__queued_by_url.clear()

    async def await_connection_attempt(self, timeout=None):
        return await self.__await_event(
            self.__connection_waiters, timeout, 'Timeout waiting for connection attempt')

    async def await_request(self, timeout=None):
        return await self.__await_event(
            self.__request_waiters, timeout, 'Timeout waiting for request')

    def queue_response(self, status, body=None, headers=None):
        self.__queued.append(lambda request: request.respond_with(status, body, headers))

    def queue_responses(self, count, status, body=None, headers=None):
        for _ in range(count):
            self.queue_response(status, body, headers)

    def queue_timeout(self):
        self.__queued.append(lambda request: request.respond_with_timeout())

    def queue_delayed_response(self, delay, status, body=None, headers=None):
        self.__queued.append(
            lambda request: request.respond_with_delay(delay, status, body, headers))

    def queue_response_for_host(self, host, status, body=None, headers=None):
        self.__queued_by_host.setdefault(host, []).append(
            lambda request: request.respond_with(status, body, headers))

    def queue_response_for_url(self, url, status, body=None, headers=None):
        # Matched against the normalised URL, so a default port may be given or omitted
        self.__queued_by_url.setdefault(str(httpx.URL(str(url))), []).append(
            lambda request: request.respond_with(status, body, headers))

    async def _handle(self, request):
        connection = PendingConnection(
            host=request.url.host,
            port=request.url.port or DEFAULT_PORTS.get(request.url.scheme, 80),
            tls=request.url.scheme == 'https',
        )
        self.__dispatch_connection(connection)
        failure = await connection._outcome
        if failure is not None:
            error_class, message = failure
            raise error_class(message, request=request)

        pending = PendingRequest(request)
        self.captured_requests.append(pending)
        self.__dispatch_request(pending)

        delay, response, error = await pending._outcome
        if delay:
            # Timeouts are enforced by the transport, so a delay beyond the
            # client's read budget has to surface as one
            read_timeout = (request.extensions.get('timeout') or {}).get('read')
            if read_timeout is not None and delay > read_timeout:
                await asyncio.sleep(read_timeout)
                raise httpx.ReadTimeout(f'Request to {pending.url} timed out', request=request)
            await asyncio.sleep(delay)
        if error is not None:
            raise error
        return response

    def __dispatch_connection(self, connection):
        waiter = self.__take_waiter(self.__connection_waiters)
        if waiter is not None:
            waiter.set_result(connection)
        elif self.on_connection_attempt is not None:
            self.on_connection_attempt(connection)
        else:
            connection.respond_with_success()

    def __dispatch_request(self, request):
        waiter = self.__take_waiter(self.__request_waiters)
        if waiter is not None:
            waiter.set_result(request)
            return
        if self.on_request is not None:
            self.on_request(request)
            return
        stub = self.__take_queued_stub(request)
        if stub is not None:
            stub(request)
            return
        request.respond_with(404, {'error': {'message': 'No response configured', 'code': 40400}})

    def __take_queued_stub(self, request):
        for stubs, key in ((self.__queued_by_url, str(request.url)),
                           (self.__queued_by_host, request.url.host)):
            queued = stubs.get(key)
            if queued:
                return queued.pop(0)
        if self.__queued:
            return self.__queued.pop(0)
        return None

    @staticmethod
    def __take_waiter(waiters):
        while waiters:
            waiter = waiters.pop(0)
            if not waiter.done():
                return waiter
        return None

    @staticmethod
    async def __await_event(waiters, timeout, message):
        waiter = asyncio.get_running_loop().create_future()
        waiters.append(waiter)
        try:
            return await asyncio.wait_for(waiter, timeout)
        except asyncio.TimeoutError:
            raise AssertionError(message) from None


class _MockTransport(httpx.AsyncBaseTransport):
    def __init__(self, mock):
        self.__mock = mock

    async def handle_async_request(self, request):
        return await self.__mock._handle(request)

    async def aclose(self):
        pass
