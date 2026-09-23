"""Derived from uts/realtime/unit/client/realtime_stats.md in ably/specification.

Spec points: RTC5, RTC5a, RTC5b
"""

from ably.http.paginatedresult import PaginatedResult
from test.uts.helpers.client import realtime_client
from test.uts.helpers.mock_http import MockHttpClient

STATS_DATA = [
    {
        'intervalId': '2024-01-01:00:00',
        'unit': 'hour',
        'all': {
            'messages': {'count': 100, 'data': 5000},
            'all': {'count': 100, 'data': 5000},
        },
    },
    {
        'intervalId': '2024-01-01:01:00',
        'unit': 'hour',
        'all': {
            'messages': {'count': 150, 'data': 7500},
            'all': {'count': 150, 'data': 7500},
        },
    },
]


# UTS: realtime/unit/RTC5/stats-proxies-rest-0
async def test_rtc5_stats_proxies_rest():
    # The specification directs uts/rest/unit/stats.md (RSC6) at a realtime client
    # in place of a REST one. `AblyRealtime` subclasses `AblyRest`, so the same HTTP
    # mock serves it, and this mirrors that suite's `RSC6a/returns-paginated-stats-0`.
    captured_requests = []

    def on_request(request):
        captured_requests.append(request)
        request.respond_with(200, STATS_DATA)

    mock_http = MockHttpClient(
        on_connection_attempt=lambda conn: conn.respond_with_success(),
        on_request=on_request,
    )
    # `auto_connect` is left at `realtime_client`'s false, so no websocket is opened
    client = realtime_client(mock_http=mock_http)

    result = await client.stats()

    assert isinstance(result, PaginatedResult)
    assert len(result.items) == 2

    # NOTE: the spec spells the field intervalId; ably-python exposes it as interval_id.
    assert result.items[0].interval_id == '2024-01-01:00:00'
    assert result.items[0].unit == 'hour'
    assert result.items[1].interval_id == '2024-01-01:01:00'

    assert len(captured_requests) == 1
    request = captured_requests[0]
    assert request.method == 'GET'
    assert request.path == '/stats'
