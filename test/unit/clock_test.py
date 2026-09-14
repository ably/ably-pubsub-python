import httpx
import pytest

from ably.pubsub.server import AblyRest
from ably.pubsub.types.testoptions import TestOptions
from ably.pubsub.util.clock import Clock
from ably.pubsub.util.exceptions import AblyException

# A plausible wall-clock reading for a fake to start from, so that a time taken
# against it looks like a real one.
EPOCH_MS = 1_700_000_000_000


class FakeClock:
    """A clock whose notional time only the test moves.

    `advance` moves it by hand; `step_ms` moves it by that much on every read,
    which is how a duration measured across several reads is driven.
    """

    def __init__(self, now_ms=EPOCH_MS, step_ms=0):
        self.__now_ms = now_ms
        self.__step_ms = step_ms

    def now_ms(self):
        reading = self.__now_ms
        self.__now_ms += self.__step_ms
        return reading

    def monotonic_ms(self):
        return float(self.__now_ms)

    def advance(self, milliseconds):
        self.__now_ms += milliseconds

    def timer(self, timeout, callback):
        raise AssertionError('the REST client schedules no delayed callbacks')


class RecordingTransport(httpx.AsyncBaseTransport):
    """Records the host of every request and refuses the ones in `refusing`.

    A host left out of `refusing` is served a server time. `refusing` is set
    after the client is built, since the host to refuse is one of its own.
    """

    def __init__(self):
        self.refusing = ()
        self.hosts = []

    async def handle_async_request(self, request):
        self.hosts.append(request.url.host)
        if request.url.host in self.refusing:
            raise httpx.ConnectError('connection refused', request=request)
        return httpx.Response(200, json=[1500000000000])


def test_auth_timestamps_from_the_injected_clock():
    ably = AblyRest(key='name:secret', _test_options=TestOptions(clock=FakeClock(1_500_000_000_000)))
    assert ably.auth._timestamp() == 1_500_000_000_000


def test_a_client_without_test_options_reads_the_real_clock():
    ably = AblyRest(token='foo')
    assert isinstance(ably.auth._Auth__clock, Clock)
    assert isinstance(ably.http._Http__clock, Clock)


async def test_the_cached_fallback_host_expires_on_the_clock():
    # RSC15f: the cache lasts fallback_retry_timeout milliseconds
    clock = FakeClock()
    transport = RecordingTransport()
    ably = AblyRest(token='foo', fallback_retry_timeout=2000,
                    _test_options=TestOptions(http_transport=transport, clock=clock))
    primary = ably.options.get_host()
    transport.refusing = (primary,)

    await ably.time()

    fallback = transport.hosts[-1]
    assert fallback != primary
    assert ably.http._Http__host_expires == EPOCH_MS + 2000
    assert ably.http.get_hosts()[0] == fallback

    clock.advance(1999)
    assert ably.http.get_hosts()[0] == fallback

    clock.advance(2)
    assert ably.http.get_hosts()[0] == primary
    assert ably.http._Http__host_expires is None

    await ably.close()


async def test_every_host_is_tried_while_the_retry_budget_lasts():
    # A second of clock time per reading, against the default 15 second budget
    clock = FakeClock(step_ms=1000)
    transport = RecordingTransport()
    ably = AblyRest(token='foo', _test_options=TestOptions(http_transport=transport, clock=clock))
    hosts = ably.http.get_hosts()
    transport.refusing = tuple(hosts)

    with pytest.raises(AblyException):
        await ably.time()

    assert transport.hosts == hosts

    await ably.close()


async def test_retrying_stops_once_the_retry_budget_is_spent():
    # RSC15l: http_max_retry_duration is seconds where the clock is milliseconds
    clock = FakeClock(step_ms=1000)
    transport = RecordingTransport()
    ably = AblyRest(token='foo', http_max_retry_duration=0.5,
                    _test_options=TestOptions(http_transport=transport, clock=clock))
    transport.refusing = tuple(ably.http.get_hosts())

    with pytest.raises(AblyException):
        await ably.time()

    assert len(transport.hosts) == 1

    await ably.close()
