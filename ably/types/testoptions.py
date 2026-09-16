class TestOptions:
    """Substitutes for the infrastructure a client uses to perform I/O.

    Hooks left as None use the production implementation.

    :Parameters:
      - `http_transport`: an `httpx.AsyncBaseTransport` which handles every
        HTTP request the client makes, in place of the network.
    """

    # Excludes the class from pytest collection, which would otherwise treat
    # any module importing it as declaring a test suite.
    __test__ = False

    def __init__(self, http_transport=None):
        self.http_transport = http_transport
