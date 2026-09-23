class TestOptions:
    """Substitutes for the infrastructure a client uses to perform I/O.

    Hooks left as None use the production implementation.

    :Parameters:
      - `http_transport`: an `httpx.AsyncBaseTransport` which handles every
        HTTP request the client makes, in place of the network.
      - `websocket_connect`: a callable which opens every realtime websocket
        connection the client makes, in place of `websockets.connect`. It is
        called as `websocket_connect(url, additional_headers=headers)`, or with
        `extra_headers=headers` if that raises `TypeError`, and returns an async
        context manager yielding an object supporting `__aiter__`, `send` and
        `close`.
    """

    # Excludes the class from pytest collection, which would otherwise treat
    # any module importing it as declaring a test suite.
    __test__ = False

    def __init__(self, http_transport=None, websocket_connect=None):
        self.http_transport = http_transport
        self.websocket_connect = websocket_connect
