"""Derived from uts/realtime/unit/client/realtime_time.md in ably/specification.

Spec points: RTC6, RTC6a
"""

from test.uts.helpers.client import realtime_client
from test.uts.helpers.mock_http import MockHttpClient

SERVER_TIME_MS = 1704067200000


# UTS: realtime/unit/RTC6/time-proxies-rest-0
async def test_rtc6_time_proxies_rest():
    # The specification directs uts/rest/unit/time.md (RSC16) at a realtime client
    # in place of a REST one. `AblyRealtime` subclasses `AblyRest`, so the same
    # HTTP mock serves it, and this mirrors that suite's `RSC16/returns-server-time-0`.
    captured_requests = []

    def on_request(request):
        captured_requests.append(request)
        request.respond_with(200, [SERVER_TIME_MS])

    mock_http = MockHttpClient(
        on_connection_attempt=lambda conn: conn.respond_with_success(),
        on_request=on_request,
    )
    # `auto_connect` is left at `realtime_client`'s false, so no websocket is opened
    client = realtime_client(mock_http=mock_http)

    result = await client.time()

    # NOTE: the REST spec asserts the result IS DateTime. Its stated requirement
    # allows "a DateTime or timestamp", and time() returns milliseconds since the epoch.
    assert isinstance(result, (int, float))
    assert result == SERVER_TIME_MS

    assert len(captured_requests) == 1
    request = captured_requests[0]
    assert request.method == 'GET'
    assert request.path == '/time'
