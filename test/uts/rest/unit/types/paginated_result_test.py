"""Derived from uts/rest/unit/types/paginated_result.md in ably/specification.

Spec points: TG1, TG2, TG3, TG4
"""

import pytest

from ably.types.message import Message
from ably.types.presence import PresenceMessage
from ably.util.exceptions import AblyException
from test.uts.helpers.client import rest_client
from test.uts.helpers.mock_http import MockHttpClient


def paging_handler(captured_requests, pages):
    """Answers each successive request with the next entry from `pages`.

    An entry is a `(body, headers)` pair; the last entry serves every request
    beyond the ones listed.
    """
    def on_request(request):
        captured_requests.append(request)
        body, headers = pages[min(len(captured_requests) - 1, len(pages) - 1)]
        request.respond_with(200, body, headers)

    return on_request


# UTS: rest/unit/TG1/paginated-result-items-0
async def test_tg1_paginated_result_items():
    captured_requests = []
    mock_http = MockHttpClient(
        on_connection_attempt=lambda conn: conn.respond_with_success(),
        on_request=paging_handler(captured_requests, [(
            [
                {'id': 'item1', 'name': 'e1', 'data': 'd1'},
                {'id': 'item2', 'name': 'e2', 'data': 'd2'},
            ],
            {},
        )]),
    )
    client = rest_client(mock_http)
    channel = client.channels.get('test')

    result = await channel.history()

    assert isinstance(result.items, list)
    assert len(result.items) == 2
    assert result.items[0].id == 'item1'
    assert result.items[1].id == 'item2'


# UTS: rest/unit/TG2/has-next-is-last-0
async def test_tg2_has_next_is_last_with_more_pages():
    captured_requests = []
    mock_http = MockHttpClient(
        on_connection_attempt=lambda conn: conn.respond_with_success(),
        on_request=paging_handler(captured_requests, [(
            [{'id': 'item1'}],
            {'Link': '</channels/test/messages?cursor=next123>; rel="next"'},
        )]),
    )
    client = rest_client(mock_http)
    channel = client.channels.get('test')

    result = await channel.history()

    assert result.has_next() is True
    assert result.is_last() is False


# UTS: rest/unit/TG2/has-next-is-last-0
async def test_tg2_has_next_is_last_without_more_pages():
    captured_requests = []
    mock_http = MockHttpClient(
        on_connection_attempt=lambda conn: conn.respond_with_success(),
        on_request=paging_handler(captured_requests, [([{'id': 'item1'}], {})]),
    )
    client = rest_client(mock_http)
    channel = client.channels.get('test')

    result = await channel.history()

    assert result.has_next() is False
    assert result.is_last() is True


# UTS: rest/unit/TG3/next-fetches-next-page-0
async def test_tg3_next_fetches_next_page():
    captured_requests = []
    mock_http = MockHttpClient(
        on_connection_attempt=lambda conn: conn.respond_with_success(),
        on_request=paging_handler(captured_requests, [
            (
                [{'id': 'page1-item1'}, {'id': 'page1-item2'}],
                {'Link': '</channels/test/messages?cursor=abc123>; rel="next"'},
            ),
            ([{'id': 'page2-item1'}], {}),
        ]),
    )
    client = rest_client(mock_http)
    channel = client.channels.get('test')

    page1 = await channel.history()
    page2 = await page1.next()

    assert len(page1.items) == 2
    assert page1.items[0].id == 'page1-item1'
    assert page1.has_next() is True

    assert len(page2.items) == 1
    assert page2.items[0].id == 'page2-item1'
    assert page2.has_next() is False

    next_request = captured_requests[1]
    assert 'cursor' in next_request.url.query_params
    assert next_request.url.query_params['cursor'] == 'abc123'


# UTS: rest/unit/TG4/first-returns-first-page-0
async def test_tg4_first_returns_first_page():
    captured_requests = []
    mock_http = MockHttpClient(
        on_connection_attempt=lambda conn: conn.respond_with_success(),
        on_request=paging_handler(captured_requests, [
            (
                [{'id': 'item1'}],
                {'Link': '</channels/test/messages?cursor=next>; rel="next", '
                         '</channels/test/messages>; rel="first"'},
            ),
            (
                [{'id': 'item2'}],
                {'Link': '</channels/test/messages>; rel="first"'},
            ),
            (
                [{'id': 'item1'}],
                {'Link': '</channels/test/messages?cursor=next>; rel="next"'},
            ),
        ]),
    )
    client = rest_client(mock_http)
    channel = client.channels.get('test')

    page1 = await channel.history()
    page2 = await page1.next()
    first_page = await page2.first()

    assert first_page.items[0].id == 'item1'


# UTS: rest/unit/TG/empty-result-handling-0
async def test_tg_empty_result_handling():
    captured_requests = []
    mock_http = MockHttpClient(
        on_connection_attempt=lambda conn: conn.respond_with_success(),
        on_request=paging_handler(captured_requests, [([], {})]),
    )
    client = rest_client(mock_http)
    channel = client.channels.get('test')

    result = await channel.history()

    assert isinstance(result.items, list)
    assert len(result.items) == 0
    assert result.has_next() is False
    assert result.is_last() is True


LINK_HEADER_CASES = [
    ('</path?cursor=abc>; rel="next"', True),
    ('</path?cursor=abc>; rel="next", </path>; rel="first"', True),
    ('</path>; rel="first"', False),
    ('', False),
]


# UTS: rest/unit/TG/link-header-parsing-1
@pytest.mark.parametrize('link_header,expected_has_next', LINK_HEADER_CASES)
async def test_tg_link_header_parsing(link_header, expected_has_next):
    captured_requests = []
    headers = {'Link': link_header} if link_header else {}
    mock_http = MockHttpClient(
        on_connection_attempt=lambda conn: conn.respond_with_success(),
        on_request=paging_handler(captured_requests, [([{'id': 'item'}], headers)]),
    )
    client = rest_client(mock_http)

    result = await client.channels.get('test').history()

    assert result.has_next() == expected_has_next


# UTS: rest/unit/TG/type-parameter-items-2
async def test_tg_type_parameter_items():
    captured_requests = []
    mock_http = MockHttpClient(
        on_connection_attempt=lambda conn: conn.respond_with_success(),
        on_request=paging_handler(captured_requests, [(
            [{'id': 'msg1', 'name': 'event', 'data': 'test'}],
            {},
        )]),
    )
    client = rest_client(mock_http)
    channel = client.channels.get('test')

    # NOTE: the spec calls this "primarily a compile-time/type-system verification".
    # Python is not statically typed, so only the runtime half is assertable.
    history_result = await channel.history()
    assert isinstance(history_result.items[0], Message)


# UTS: rest/unit/TG/next-on-last-page-3
async def test_tg_next_on_last_page():
    captured_requests = []
    mock_http = MockHttpClient(
        on_connection_attempt=lambda conn: conn.respond_with_success(),
        on_request=paging_handler(captured_requests, [([{'id': 'item'}], {})]),
    )
    client = rest_client(mock_http)
    channel = client.channels.get('test')

    result = await channel.history()
    assert result.is_last() is True

    next_result = await result.next()

    # The spec allows null, an empty result, or an exception; ably-python returns None
    assert next_result is None


# UTS: rest/unit/TG/pagination-preserves-auth-4
async def test_tg_pagination_preserves_auth():
    captured_requests = []
    mock_http = MockHttpClient(
        on_connection_attempt=lambda conn: conn.respond_with_success(),
        on_request=paging_handler(captured_requests, [
            (
                [{'id': 'item1'}],
                {'Link': '</channels/test/messages?cursor=next>; rel="next"'},
            ),
            ([{'id': 'item2'}], {}),
        ]),
    )
    client = rest_client(mock_http)
    channel = client.channels.get('test')

    page1 = await channel.history()
    await page1.next()

    assert 'Authorization' in captured_requests[0].headers
    assert 'Authorization' in captured_requests[1].headers
    assert captured_requests[0].headers['Authorization'] == captured_requests[1].headers['Authorization']


# UTS: rest/unit/TG/pagination-relative-urls-5
async def test_tg_pagination_relative_urls():
    captured_requests = []
    mock_http = MockHttpClient(
        on_connection_attempt=lambda conn: conn.respond_with_success(),
        on_request=paging_handler(captured_requests, [
            (
                [{'id': 'item1'}],
                {'Link': '</channels/test/messages?page=2>; rel="next"'},
            ),
            ([{'id': 'item2'}], {}),
        ]),
    )
    client = rest_client(mock_http, rest_host='rest.ably.io')
    channel = client.channels.get('test')

    page1 = await channel.history()
    await page1.next()

    assert captured_requests[1].url.host == 'rest.ably.io'
    assert captured_requests[1].url.path == '/channels/test/messages'
    assert 'page' in captured_requests[1].url.query_params


# UTS: rest/unit/TG/multiple-link-relations-6
async def test_tg_multiple_link_relations():
    captured_requests = []
    mock_http = MockHttpClient(
        on_connection_attempt=lambda conn: conn.respond_with_success(),
        on_request=paging_handler(captured_requests, [(
            [{'id': 'item1'}],
            {'Link': '</channels/test/messages?page=2>; rel="next", '
                     '</channels/test/messages?page=1>; rel="first", '
                     '</channels/test/messages?page=5>; rel="last"'},
        )]),
    )
    client = rest_client(mock_http)
    channel = client.channels.get('test')

    result = await channel.history()

    assert result.has_next() is True
    # The spec adds that navigation to next, first or last should be possible;
    # ably-python exposes next and first
    assert result.has_first() is True


# UTS: rest/unit/TG/pagination-presence-results-7
async def test_tg_pagination_presence_results():
    captured_requests = []
    mock_http = MockHttpClient(
        on_connection_attempt=lambda conn: conn.respond_with_success(),
        on_request=paging_handler(captured_requests, [
            (
                [{'action': 1, 'clientId': 'client1'}],
                {'Link': '</channels/test/presence?page=2>; rel="next"'},
            ),
            ([{'action': 1, 'clientId': 'client2'}], {}),
        ]),
    )
    client = rest_client(mock_http)
    channel = client.channels.get('test')

    page1 = await channel.presence.get()
    page2 = await page1.next()

    assert isinstance(page1.items[0], PresenceMessage)
    assert page1.items[0].client_id == 'client1'
    assert page2.items[0].client_id == 'client2'


# UTS: rest/unit/TG/pagination-includes-headers-8
async def test_tg_pagination_includes_headers():
    captured_requests = []
    mock_http = MockHttpClient(
        on_connection_attempt=lambda conn: conn.respond_with_success(),
        on_request=paging_handler(captured_requests, [
            (
                [{'id': 'item1'}],
                {'Link': '</channels/test/messages?cursor=next>; rel="next"'},
            ),
            ([{'id': 'item2'}], {}),
        ]),
    )
    client = rest_client(mock_http)
    channel = client.channels.get('test')

    page1 = await channel.history()
    await page1.next()

    next_request = captured_requests[1]
    assert 'X-Ably-Version' in next_request.headers
    assert 'Ably-Agent' in next_request.headers
    assert 'ably-' in next_request.headers['Ably-Agent']


# UTS: rest/unit/TG/error-handling-on-next-9
async def test_tg_error_handling_on_next():
    captured_requests = []

    def on_request(request):
        captured_requests.append(request)
        if len(captured_requests) == 1:
            request.respond_with(
                200,
                [{'id': 'item1'}],
                {'Link': '</channels/test/messages?cursor=invalid>; rel="next"'},
            )
        else:
            request.respond_with(404, {
                'error': {
                    'code': 40400,
                    'statusCode': 404,
                    'message': 'Not found',
                },
            })

    mock_http = MockHttpClient(
        on_connection_attempt=lambda conn: conn.respond_with_success(),
        on_request=on_request,
    )
    client = rest_client(mock_http)
    channel = client.channels.get('test')

    page1 = await channel.history()

    with pytest.raises(AblyException) as excinfo:
        await page1.next()

    assert excinfo.value.status_code == 404
    assert excinfo.value.code == 40400
