"""Derived from uts/rest/unit/stats.md in ably/specification.

Spec points: RSC6, RSC6a, RSC6b1, RSC6b2, RSC6b3, RSC6b4
"""

from datetime import datetime, timezone

import pytest

from ably.http.paginatedresult import PaginatedResult
from ably.util.exceptions import AblyException
from test.uts.helpers.client import rest_client
from test.uts.helpers.mock_http import MockHttpClient

START_TIME = datetime(2024, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
END_TIME = datetime(2024, 1, 31, 23, 59, 59, tzinfo=timezone.utc)

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


def milliseconds_since_epoch(value):
    return int(value.timestamp() * 1000)


def capture_and_respond(captured_requests, body):
    def on_request(request):
        captured_requests.append(request)
        request.respond_with(200, body)

    return on_request


def capturing_client(captured_requests, body=None):
    mock_http = MockHttpClient(
        on_connection_attempt=lambda conn: conn.respond_with_success(),
        on_request=capture_and_respond(captured_requests, [] if body is None else body),
    )
    return rest_client(mock_http)


# UTS: rest/unit/RSC6a/returns-paginated-stats-0
async def test_rsc6a_stats_returns_paginated_stats():
    captured_requests = []
    client = capturing_client(captured_requests, STATS_DATA)

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


# UTS: rest/unit/RSC6a/authenticated-with-headers-1
async def test_rsc6a_stats_authenticated_with_headers():
    captured_requests = []
    client = capturing_client(captured_requests)

    await client.stats()

    assert len(captured_requests) == 1
    request = captured_requests[0]

    assert 'Authorization' in request.headers

    assert 'X-Ably-Version' in request.headers
    assert 'Ably-Agent' in request.headers


# UTS: rest/unit/RSC6b1/start-param-millis-0
async def test_rsc6b1_stats_start_param_millis():
    captured_requests = []
    client = capturing_client(captured_requests)

    await client.stats(start=START_TIME)

    assert len(captured_requests) == 1
    request = captured_requests[0]
    assert request.url.query_params['start'] == str(milliseconds_since_epoch(START_TIME))


# UTS: rest/unit/RSC6b1/end-param-millis-1
async def test_rsc6b1_stats_end_param_millis():
    captured_requests = []
    client = capturing_client(captured_requests)

    await client.stats(end=END_TIME)

    assert len(captured_requests) == 1
    request = captured_requests[0]
    assert request.url.query_params['end'] == str(milliseconds_since_epoch(END_TIME))


# UTS: rest/unit/RSC6b1/start-and-end-params-2
async def test_rsc6b1_stats_start_and_end_params():
    captured_requests = []
    client = capturing_client(captured_requests)

    await client.stats(start=START_TIME, end=END_TIME)

    assert len(captured_requests) == 1
    request = captured_requests[0]
    assert request.url.query_params['start'] == str(milliseconds_since_epoch(START_TIME))
    assert request.url.query_params['end'] == str(milliseconds_since_epoch(END_TIME))


# UTS: rest/unit/RSC6b2/direction-param-forwards-0
async def test_rsc6b2_stats_direction_param_forwards():
    captured_requests = []
    client = capturing_client(captured_requests)

    await client.stats(direction='forwards')

    assert len(captured_requests) == 1
    request = captured_requests[0]
    assert request.url.query_params['direction'] == 'forwards'


# UTS: rest/unit/RSC6b2/direction-defaults-backwards-1
async def test_rsc6b2_stats_direction_defaults_backwards():
    captured_requests = []
    client = capturing_client(captured_requests)

    await client.stats()

    assert len(captured_requests) == 1
    request = captured_requests[0]

    query_params = request.url.query_params
    assert 'direction' not in query_params or query_params['direction'] == 'backwards'


# UTS: rest/unit/RSC6b3/limit-param-value-0
async def test_rsc6b3_stats_limit_param_value():
    captured_requests = []
    client = capturing_client(captured_requests)

    await client.stats(limit=10)

    assert len(captured_requests) == 1
    request = captured_requests[0]
    assert request.url.query_params['limit'] == '10'


# UTS: rest/unit/RSC6b3/limit-defaults-to-100-1
async def test_rsc6b3_stats_limit_defaults_to_100():
    captured_requests = []
    client = capturing_client(captured_requests)

    await client.stats()

    assert len(captured_requests) == 1
    request = captured_requests[0]

    query_params = request.url.query_params
    assert 'limit' not in query_params or query_params['limit'] == '100'


# UTS: rest/unit/RSC6b4/unit-param-values-0
async def test_rsc6b4_stats_unit_param_values():
    captured_requests = []
    client = capturing_client(captured_requests)

    for unit in ('minute', 'hour', 'day', 'month'):
        captured_requests.clear()

        await client.stats(unit=unit)

        assert len(captured_requests) == 1
        request = captured_requests[0]
        assert request.url.query_params['unit'] == unit


# UTS: rest/unit/RSC6b4/unit-defaults-to-minute-1
async def test_rsc6b4_stats_unit_defaults_to_minute():
    captured_requests = []
    client = capturing_client(captured_requests)

    await client.stats()

    assert len(captured_requests) == 1
    request = captured_requests[0]

    query_params = request.url.query_params
    assert 'unit' not in query_params or query_params['unit'] == 'minute'


# UTS: rest/unit/RSC6b/all-params-combined-0
async def test_rsc6b_stats_all_params_combined():
    captured_requests = []
    client = capturing_client(captured_requests)

    await client.stats(
        start=START_TIME,
        end=END_TIME,
        direction='forwards',
        limit=50,
        unit='hour',
    )

    assert len(captured_requests) == 1
    request = captured_requests[0]
    query_params = request.url.query_params
    assert query_params['start'] == str(milliseconds_since_epoch(START_TIME))
    assert query_params['end'] == str(milliseconds_since_epoch(END_TIME))
    assert query_params['direction'] == 'forwards'
    assert query_params['limit'] == '50'
    assert query_params['unit'] == 'hour'


# UTS: rest/unit/RSC6a/no-params-clean-request-2
async def test_rsc6a_stats_no_params_clean_request():
    captured_requests = []
    client = capturing_client(captured_requests)

    await client.stats()

    assert len(captured_requests) == 1
    request = captured_requests[0]
    assert request.method == 'GET'
    assert request.path == '/stats'

    assert request.url.query_params == {}


# UTS: rest/unit/RSC6a/pagination-link-headers-3
async def test_rsc6a_stats_pagination_link_headers():
    request_count = 0

    def on_request(request):
        nonlocal request_count
        request_count += 1
        if request_count == 1:
            request.respond_with(
                200,
                [{'intervalId': '2024-01-01:01:00', 'unit': 'hour'}],
                headers={'Link': '</stats?start=1704070800000&limit=1>; rel="next"'},
            )
        else:
            request.respond_with(200, [{'intervalId': '2024-01-01:00:00', 'unit': 'hour'}])

    mock_http = MockHttpClient(
        on_connection_attempt=lambda conn: conn.respond_with_success(),
        on_request=on_request,
    )
    client = rest_client(mock_http)

    page1 = await client.stats(limit=1)
    page2 = await page1.next()

    assert len(page1.items) == 1
    assert page1.items[0].interval_id == '2024-01-01:01:00'
    assert page1.has_next() is True
    assert page1.is_last() is False

    assert len(page2.items) == 1
    assert page2.items[0].interval_id == '2024-01-01:00:00'
    assert page2.has_next() is False
    assert page2.is_last() is True


# UTS: rest/unit/RSC6a/empty-results-handled-4
async def test_rsc6a_stats_empty_results_handled():
    mock_http = MockHttpClient(
        on_connection_attempt=lambda conn: conn.respond_with_success(),
        on_request=lambda request: request.respond_with(200, []),
    )
    client = rest_client(mock_http)

    result = await client.stats()

    assert isinstance(result, PaginatedResult)
    assert len(result.items) == 0
    assert result.has_next() is False
    assert result.is_last() is True


# UTS: rest/unit/RSC6a/error-propagated-5
async def test_rsc6a_stats_error_propagated():
    mock_http = MockHttpClient(
        on_connection_attempt=lambda conn: conn.respond_with_success(),
        on_request=lambda request: request.respond_with(401, {
            'error': {
                'message': 'Unauthorized',
                'code': 40100,
                'statusCode': 401,
            },
        }),
    )
    client = rest_client(mock_http)

    with pytest.raises(AblyException) as excinfo:
        await client.stats()

    assert excinfo.value.status_code == 401
    assert excinfo.value.code == 40100
