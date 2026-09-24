"""Derived from uts/rest/unit/channel/message_versions.md in ably/specification.

Spec points: RSL14, RSL14a, RSL14a1, RSL14b, RSL14c
"""

import uuid

from ably.http.paginatedresult import PaginatedResult
from ably.types.message import Message, MessageAction
from test.uts.helpers.client import rest_client
from test.uts.helpers.mock_http import MockHttpClient


def random_id():
    return uuid.uuid4().hex[:8]


# UTS: rest/unit/RSL14b/get-correct-endpoint-0
async def test_rsl14b_get_correct_endpoint():
    channel_name = f'test-RSL14b-{random_id()}'
    captured_requests = []

    def on_request(request):
        captured_requests.append(request)
        request.respond_with(200, [
            {
                'name': 'evt',
                'data': 'v2-data',
                'serial': 'msg-serial-1',
                'action': 1,
                'version': {'serial': 'vs2', 'timestamp': 1700000002000},
            },
            {
                'name': 'evt',
                'data': 'v1-data',
                'serial': 'msg-serial-1',
                'action': 0,
                'version': {'serial': 'vs1', 'timestamp': 1700000001000},
            },
        ])

    mock_http = MockHttpClient(
        on_connection_attempt=lambda conn: conn.respond_with_success(),
        on_request=on_request,
    )
    client = rest_client(mock_http)
    channel = client.channels.get(channel_name)

    await channel.get_message_versions('msg-serial-1')

    assert len(captured_requests) == 1

    request = captured_requests[0]
    assert request.method == 'GET'
    assert request.url.path == f'/channels/{channel_name}/messages/msg-serial-1/versions'


# UTS: rest/unit/RSL14c/returns-paginated-result-0
async def test_rsl14c_returns_paginated_result():
    channel_name = f'test-RSL14c-{random_id()}'

    def on_request(request):
        request.respond_with(200, [
            {
                'name': 'evt',
                'data': 'updated-data',
                'serial': 'msg-serial-1',
                'action': 1,
                'version': {
                    'serial': 'vs2',
                    'timestamp': 1700000002000,
                    'clientId': 'user-1',
                    'description': 'edit',
                },
            },
            {
                'name': 'evt',
                'data': 'original-data',
                'serial': 'msg-serial-1',
                'action': 0,
                'version': {
                    'serial': 'vs1',
                    'timestamp': 1700000001000,
                },
            },
        ])

    mock_http = MockHttpClient(
        on_connection_attempt=lambda conn: conn.respond_with_success(),
        on_request=on_request,
    )
    client = rest_client(mock_http)
    channel = client.channels.get(channel_name)

    result = await channel.get_message_versions('msg-serial-1')

    assert isinstance(result, PaginatedResult)
    assert len(result.items) == 2

    assert isinstance(result.items[0], Message)
    assert result.items[0].data == 'updated-data'
    assert result.items[0].action == MessageAction.MESSAGE_UPDATE
    assert result.items[0].version.serial == 'vs2'
    assert result.items[0].version.description == 'edit'

    assert result.items[1].data == 'original-data'
    assert result.items[1].action == MessageAction.MESSAGE_CREATE


# UTS: rest/unit/RSL14a/params-as-querystring-0
async def test_rsl14a_params_as_querystring():
    channel_name = f'test-RSL14a-params-{random_id()}'
    captured_requests = []

    def on_request(request):
        captured_requests.append(request)
        request.respond_with(200, [])

    mock_http = MockHttpClient(
        on_connection_attempt=lambda conn: conn.respond_with_success(),
        on_request=on_request,
    )
    client = rest_client(mock_http)
    channel = client.channels.get(channel_name)

    # DEVIATION RSL14a: `params` is specified as Dict<string, stringifiable>, so a
    # stringified limit must be accepted. `format_params` compares `limit` against the
    # integer 1000 without coercing it, so a string limit raises
    # `TypeError: '>' not supported between instances of 'str' and 'int'`.
    await channel.get_message_versions('msg-serial-1', params={
        'direction': 'backwards',
        'limit': '10',
    })

    request = captured_requests[0]
    assert request.url.query_params['direction'] == 'backwards'
    assert request.url.query_params['limit'] == '10'
