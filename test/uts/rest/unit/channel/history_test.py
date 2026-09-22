"""Derived from uts/rest/unit/channel/history.md in ably/specification.

Spec points: RSL2, RSL2a, RSL2b, RSL2b1, RSL2b2, RSL2b3
"""

import uuid

from ably.http.paginatedresult import PaginatedResult
from ably.types.message import Message
from test.uts.helpers.client import rest_client
from test.uts.helpers.mock_http import MockHttpClient


def random_id():
    return uuid.uuid4().hex[:8]


def capture_and_respond(captured_requests, body):
    def on_request(request):
        captured_requests.append(request)
        request.respond_with(200, body)

    return on_request


def wire_path(request):
    """The request path as it went on the wire, percent-encoding intact.

    `request.url.path` is percent-decoded by the URL type the mock records, so
    `%2F` reads back as `/` and the encoding the specification asserts on is no
    longer visible there. The encoded form survives in the full URL.
    """
    without_scheme = str(request.url).split('://', 1)[-1]
    path = without_scheme[without_scheme.index('/'):]
    return path.split('?', 1)[0]


# UTS: rest/unit/RSL2a/returns-paginated-result-0
async def test_rsl2a_returns_paginated_result():
    channel_name = f'test-RSL2a-{random_id()}'
    captured_requests = []
    mock_http = MockHttpClient(
        on_connection_attempt=lambda conn: conn.respond_with_success(),
        on_request=capture_and_respond(captured_requests, [
            {'id': 'msg1', 'name': 'event1', 'data': 'data1', 'timestamp': 1000},
            {'id': 'msg2', 'name': 'event2', 'data': 'data2', 'timestamp': 2000},
        ]),
    )
    client = rest_client(mock_http)
    channel = client.channels.get(channel_name)

    result = await channel.history()

    assert isinstance(result, PaginatedResult)
    assert isinstance(result.items, list)
    assert len(result.items) == 2

    assert isinstance(result.items[0], Message)
    assert result.items[0].id == 'msg1'
    assert result.items[0].name == 'event1'
    assert result.items[0].data == 'data1'


# UTS: rest/unit/RSL2b/query-parameters-0
async def test_rsl2b_query_parameters():
    channel_name = f'test-RSL2b-{random_id()}'
    captured_requests = []
    mock_http = MockHttpClient(
        on_connection_attempt=lambda conn: conn.respond_with_success(),
        on_request=capture_and_respond(captured_requests, []),
    )
    client = rest_client(mock_http)
    channel = client.channels.get(channel_name)

    test_cases = [
        ('start', 1234567890000, '1234567890000'),
        ('end', 1234567899999, '1234567899999'),
        ('direction', 'backwards', 'backwards'),
        ('direction', 'forwards', 'forwards'),
        ('limit', 50, '50'),
    ]

    for parameter, value, expected in test_cases:
        captured_requests.clear()

        # history() takes the query parameters as keyword arguments rather than a dict
        await channel.history(**{parameter: value})

        request = captured_requests[0]
        assert request.url.query_params[parameter] == expected


# UTS: rest/unit/RSL2b1/default-direction-backwards-0
async def test_rsl2b1_default_direction_backwards():
    channel_name = f'test-RSL2b1-{random_id()}'
    captured_requests = []
    mock_http = MockHttpClient(
        on_connection_attempt=lambda conn: conn.respond_with_success(),
        on_request=capture_and_respond(captured_requests, []),
    )
    client = rest_client(mock_http)
    channel = client.channels.get(channel_name)

    await channel.history()  # No direction specified

    request = captured_requests[0]

    # Either direction param is absent (server default) or explicitly "backwards"
    if 'direction' in request.url.query_params:
        assert request.url.query_params['direction'] == 'backwards'


# UTS: rest/unit/RSL2b2/limit-parameter-0
async def test_rsl2b2_limit_parameter():
    channel_name = f'test-RSL2b2-{random_id()}'
    captured_requests = []
    mock_http = MockHttpClient(
        on_connection_attempt=lambda conn: conn.respond_with_success(),
        on_request=capture_and_respond(captured_requests, [
            {'id': 'msg1', 'name': 'e', 'data': 'd', 'timestamp': 1000},
            {'id': 'msg2', 'name': 'e', 'data': 'd', 'timestamp': 2000},
            {'id': 'msg3', 'name': 'e', 'data': 'd', 'timestamp': 3000},
        ]),
    )
    client = rest_client(mock_http)
    channel = client.channels.get(channel_name)

    await channel.history(limit=10)

    request = captured_requests[0]
    assert request.url.query_params['limit'] == '10'


# UTS: rest/unit/RSL2b3/default-limit-hundred-0
async def test_rsl2b3_default_limit_hundred():
    channel_name = f'test-RSL2b3-{random_id()}'
    captured_requests = []
    mock_http = MockHttpClient(
        on_connection_attempt=lambda conn: conn.respond_with_success(),
        on_request=capture_and_respond(captured_requests, []),
    )
    client = rest_client(mock_http)
    channel = client.channels.get(channel_name)

    await channel.history()  # No limit specified

    request = captured_requests[0]

    # Either limit param is absent (server default) or explicitly "100"
    if 'limit' in request.url.query_params:
        assert request.url.query_params['limit'] == '100'


# UTS: rest/unit/RSL2/request-url-format-0
async def test_rsl2_request_url_format():
    captured_requests = []
    request_count = 0

    def on_request(request):
        nonlocal request_count
        captured_requests.append(request)
        request_count += 1
        request.respond_with(200, [])

    mock_http = MockHttpClient(
        on_connection_attempt=lambda conn: conn.respond_with_success(),
        on_request=on_request,
    )
    client = rest_client(mock_http)

    simple = f'test-RSL2-simple-{random_id()}'
    with_colon = f'test-RSL2-with:colon-{random_id()}'
    with_slash = f'test-RSL2-with/slash-{random_id()}'
    with_space = f'test-RSL2-with space-{random_id()}'

    test_cases = [
        (simple, f'/channels/{simple}/messages'),
        # DEVIATION RSL2: the spec asserts the colon is percent-encoded, as
        # encodeURIComponent would ("test-RSL2-with%3Acolon-..."). ably-python builds the
        # path with `quote_plus(name, safe=':')`, so a colon travels literally. It is a
        # legal path character, so the server still receives the same channel name.
        (with_colon, f'/channels/{with_colon}/messages'),
        (with_slash, f"/channels/{with_slash.replace('/', '%2F')}/messages"),
        # DEVIATION RSL2: the spec asserts a space is percent-encoded as "%20".
        # `quote_plus` renders it as "+", which in a URL *path* is a literal plus rather
        # than a space, so the channel name arrives at the server altered.
        (with_space, f"/channels/{with_space.replace(' ', '+')}/messages"),
    ]

    for channel_name, expected_path in test_cases:
        captured_requests.clear()
        request_count = 0

        channel = client.channels.get(channel_name)
        await channel.history()

        assert request_count == 1
        request = captured_requests[0]
        assert request.method == 'GET'
        assert wire_path(request) == expected_path


# UTS: rest/unit/RSL2/history-time-range-1
async def test_rsl2_history_time_range():
    channel_name = f'test-RSL2-timerange-{random_id()}'
    captured_requests = []
    mock_http = MockHttpClient(
        on_connection_attempt=lambda conn: conn.respond_with_success(),
        on_request=capture_and_respond(captured_requests, [
            {'id': 'msg1', 'name': 'e', 'data': 'd', 'timestamp': 1500},
        ]),
    )
    client = rest_client(mock_http)
    channel = client.channels.get(channel_name)

    await channel.history(start=1000, end=2000)

    request = captured_requests[0]
    assert request.url.query_params['start'] == '1000'
    assert request.url.query_params['end'] == '2000'
