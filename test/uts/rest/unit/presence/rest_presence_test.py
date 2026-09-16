"""Derived from uts/rest/unit/presence/rest_presence.md in ably/specification.

Spec points: RSL3, RSP1, RSP1a, RSP1b, RSP3, RSP3a1, RSP3a2, RSP3a3, RSP4, RSP4a,
RSP4b1, RSP4b2, RSP4b3, RSP5
"""

import base64
import uuid
from datetime import datetime

import msgpack
import pytest

from ably.http.paginatedresult import PaginatedResult
from ably.types.presence import Presence, PresenceAction, PresenceMessage
from ably.util.crypto import CipherParams
from ably.util.exceptions import AblyException
from test.uts.helpers.client import rest_client
from test.uts.helpers.deviations import deviation
from test.uts.helpers.mock_http import MockHttpClient


def random_id():
    return uuid.uuid4().hex[:8]


def capturing_mock(captured_requests, body=None, headers=None):
    """A mock that records every request and answers each with the same response."""
    def on_request(request):
        captured_requests.append(request)
        request.respond_with(200, [] if body is None else body, headers)

    return MockHttpClient(
        on_connection_attempt=lambda conn: conn.respond_with_success(),
        on_request=on_request,
    )


def error_mock(captured_requests, status, code, message):
    def on_request(request):
        captured_requests.append(request)
        request.respond_with(status, {
            'error': {'code': code, 'statusCode': status, 'message': message},
        })

    return MockHttpClient(
        on_connection_attempt=lambda conn: conn.respond_with_success(),
        on_request=on_request,
    )


# UTS: rest/unit/RSP1a/presence-channel-attribute-0
async def test_rsp1a_presence_channel_attribute():
    channel_name = f'test-RSP1a-{random_id()}'
    captured_requests = []
    mock_http = capturing_mock(captured_requests)
    client = rest_client(mock_http)

    channel = client.channels.get(channel_name)
    presence = channel.presence

    assert presence is not None
    assert isinstance(presence, Presence)

    # The association with the channel is observable through the path it requests
    await presence.get()
    assert len(captured_requests) == 1
    assert captured_requests[0].path == f'/channels/{channel_name}/presence'


# UTS: rest/unit/RSP1b/same-instance-returned-0
async def test_rsp1b_same_instance_returned():
    channel_name = f'test-RSP1b-{random_id()}'
    captured_requests = []
    mock_http = capturing_mock(captured_requests)
    client = rest_client(mock_http)

    channel = client.channels.get(channel_name)

    assert channel.presence is channel.presence
    assert client.channels.get(channel_name).presence is channel.presence


# UTS: rest/unit/RSP3a/get-request-endpoint-0
async def test_rsp3a_get_request_endpoint():
    channel_name = f'test-RSP3a-{random_id()}'
    captured_requests = []
    mock_http = capturing_mock(captured_requests, [
        {'action': 1, 'clientId': 'client1', 'data': 'hello'},
        {'action': 1, 'clientId': 'client2', 'data': 'world'},
    ])
    client = rest_client(mock_http)

    result = await client.channels.get(channel_name).presence.get()

    assert len(captured_requests) == 1
    assert captured_requests[0].method == 'GET'
    assert captured_requests[0].url.path == f'/channels/{channel_name}/presence'
    assert isinstance(result, PaginatedResult)
    assert len(result.items) == 2
    assert all(isinstance(item, PresenceMessage) for item in result.items)


# UTS: rest/unit/RSP3b/get-returns-presence-messages-0
async def test_rsp3b_get_returns_presence_messages():
    channel_name = f'test-RSP3b-{random_id()}'
    captured_requests = []
    mock_http = capturing_mock(captured_requests, [
        {
            'action': 1,
            'clientId': 'user123',
            'connectionId': 'conn456',
            'data': 'status data',
            'encoding': None,
            'timestamp': 1234567890000,
        },
    ])
    client = rest_client(mock_http)

    result = await client.channels.get(channel_name).presence.get()

    assert len(result.items) == 1
    message = result.items[0]
    assert isinstance(message, PresenceMessage)
    assert message.action == PresenceAction.PRESENT
    assert message.client_id == 'user123'
    assert message.connection_id == 'conn456'
    assert message.data == 'status data'
    # NOTE: the spec asserts the raw millisecond value. PresenceMessage.timestamp is a
    # datetime, which is the "Date/Time object where appropriate to the language" form.
    assert message.timestamp == datetime.utcfromtimestamp(1234567890000 / 1000)


# UTS: rest/unit/RSP3c/get-empty-members-0
async def test_rsp3c_get_empty_members():
    channel_name = f'test-RSP3c-{random_id()}'
    captured_requests = []
    mock_http = capturing_mock(captured_requests, [])
    client = rest_client(mock_http)

    result = await client.channels.get(channel_name).presence.get()

    assert isinstance(result.items, list)
    assert len(result.items) == 0
    assert result.has_next() is False


# UTS: rest/unit/RSP3a1/get-limit-parameter-0
async def test_rsp3a1_get_limit_parameter():
    channel_name = f'test-RSP3a1a-{random_id()}'
    captured_requests = []
    mock_http = capturing_mock(captured_requests, [
        {'action': 1, 'clientId': 'client1'},
        {'action': 1, 'clientId': 'client2'},
    ])
    client = rest_client(mock_http)

    await client.channels.get(channel_name).presence.get(limit=50)

    assert captured_requests[0].url.query_params['limit'] == '50'


# UTS: rest/unit/RSP3a1/get-limit-default-100-1
async def test_rsp3a1_get_limit_default_100():
    channel_name = f'test-RSP3a1b-{random_id()}'
    captured_requests = []
    mock_http = capturing_mock(captured_requests, [])
    client = rest_client(mock_http)

    await client.channels.get(channel_name).presence.get()

    query_params = captured_requests[0].url.query_params
    assert 'limit' not in query_params or query_params['limit'] == '100'


# UTS: rest/unit/RSP3a1/get-limit-max-1000-2
async def test_rsp3a1_get_limit_max_1000():
    channel_name = f'test-RSP3a1c-{random_id()}'
    captured_requests = []
    mock_http = capturing_mock(captured_requests, [])
    client = rest_client(mock_http)

    await client.channels.get(channel_name).presence.get(limit=1000)

    assert captured_requests[0].url.query_params['limit'] == '1000'


# UTS: rest/unit/RSP3a2/get-clientid-filter-0
@deviation
async def test_rsp3a2_get_clientid_filter():
    channel_name = f'test-RSP3a2-{random_id()}'
    captured_requests = []
    mock_http = capturing_mock(captured_requests, [
        {'action': 1, 'clientId': 'specific-client', 'data': 'filtered'},
    ])
    client = rest_client(mock_http)

    await client.channels.get(channel_name).presence.get(client_id='specific-client')

    assert captured_requests[0].url.query_params['clientId'] == 'specific-client'


# UTS: rest/unit/RSP3a3/get-connectionid-filter-0
@deviation
async def test_rsp3a3_get_connectionid_filter():
    channel_name = f'test-RSP3a3-{random_id()}'
    captured_requests = []
    mock_http = capturing_mock(captured_requests, [
        {'action': 1, 'clientId': 'client1', 'connectionId': 'conn123'},
    ])
    client = rest_client(mock_http)

    await client.channels.get(channel_name).presence.get(connection_id='conn123')

    assert captured_requests[0].url.query_params['connectionId'] == 'conn123'


# UTS: rest/unit/RSP3/get-multiple-filters-0
@deviation
async def test_rsp3_get_multiple_filters():
    channel_name = f'test-RSP3-multi-{random_id()}'
    captured_requests = []
    mock_http = capturing_mock(captured_requests, [])
    client = rest_client(mock_http)

    await client.channels.get(channel_name).presence.get(
        limit=25, client_id='user1', connection_id='conn1')

    query_params = captured_requests[0].url.query_params
    assert query_params['limit'] == '25'
    assert query_params['clientId'] == 'user1'
    assert query_params['connectionId'] == 'conn1'


# UTS: rest/unit/RSP4a/history-request-endpoint-0
async def test_rsp4a_history_request_endpoint():
    channel_name = f'test-RSP4a-{random_id()}'
    captured_requests = []
    mock_http = capturing_mock(captured_requests, [
        {'action': 2, 'clientId': 'client1', 'data': 'entered'},
        {'action': 4, 'clientId': 'client1', 'data': 'left'},
    ])
    client = rest_client(mock_http)

    result = await client.channels.get(channel_name).presence.history()

    assert captured_requests[0].method == 'GET'
    assert captured_requests[0].url.path == f'/channels/{channel_name}/presence/history'
    assert isinstance(result, PaginatedResult)
    assert all(isinstance(item, PresenceMessage) for item in result.items)


# UTS: rest/unit/RSP4a/history-returns-paginated-1
async def test_rsp4a_history_returns_paginated():
    channel_name = f'test-RSP4a-result-{random_id()}'
    captured_requests = []
    mock_http = capturing_mock(captured_requests, [
        {'action': 2, 'clientId': 'user1', 'data': 'd1', 'timestamp': 1000},
        {'action': 3, 'clientId': 'user1', 'data': 'd2', 'timestamp': 2000},
        {'action': 4, 'clientId': 'user1', 'data': 'd3', 'timestamp': 3000},
    ])
    client = rest_client(mock_http)

    result = await client.channels.get(channel_name).presence.history()

    assert isinstance(result, PaginatedResult)
    assert len(result.items) == 3
    assert all(isinstance(item, PresenceMessage) for item in result.items)
    assert result.items[0].action == PresenceAction.ENTER
    assert result.items[1].action == PresenceAction.LEAVE
    assert result.items[2].action == PresenceAction.UPDATE


# UTS: rest/unit/RSP4b1/history-start-parameter-0
async def test_rsp4b1_history_start_parameter():
    channel_name = f'test-RSP4b1a-{random_id()}'
    captured_requests = []
    mock_http = capturing_mock(captured_requests, [])
    client = rest_client(mock_http)
    start_time = 1609459200000  # 2021-01-01 00:00:00 UTC

    await client.channels.get(channel_name).presence.history(start=start_time)

    assert captured_requests[0].url.query_params['start'] == '1609459200000'


# UTS: rest/unit/RSP4b1/history-end-parameter-1
async def test_rsp4b1_history_end_parameter():
    channel_name = f'test-RSP4b1b-{random_id()}'
    captured_requests = []
    mock_http = capturing_mock(captured_requests, [])
    client = rest_client(mock_http)
    end_time = 1609545600000  # 2021-01-02 00:00:00 UTC

    await client.channels.get(channel_name).presence.history(end=end_time)

    assert captured_requests[0].url.query_params['end'] == '1609545600000'


# UTS: rest/unit/RSP4b1/history-start-end-params-2
async def test_rsp4b1_history_start_end_params():
    channel_name = f'test-RSP4b1c-{random_id()}'
    captured_requests = []
    mock_http = capturing_mock(captured_requests, [])
    client = rest_client(mock_http)
    start_time = 1609459200000
    end_time = 1609545600000

    await client.channels.get(channel_name).presence.history(start=start_time, end=end_time)

    query_params = captured_requests[0].url.query_params
    assert query_params['start'] == '1609459200000'
    assert query_params['end'] == '1609545600000'


# UTS: rest/unit/RSP4b1/history-datetime-objects-3
async def test_rsp4b1_history_datetime_objects():
    channel_name = f'test-RSP4b1d-{random_id()}'
    captured_requests = []
    mock_http = capturing_mock(captured_requests, [])
    client = rest_client(mock_http)
    # ably-python treats a naive datetime as UTC when converting to epoch milliseconds
    start_datetime = datetime(2021, 1, 1, 0, 0, 0)

    await client.channels.get(channel_name).presence.history(start=start_datetime)

    assert captured_requests[0].url.query_params['start'] == '1609459200000'


# UTS: rest/unit/RSP4b2/history-direction-backwards-default-0
async def test_rsp4b2_history_direction_backwards_default():
    channel_name = f'test-RSP4b2a-{random_id()}'
    captured_requests = []
    mock_http = capturing_mock(captured_requests, [])
    client = rest_client(mock_http)

    await client.channels.get(channel_name).presence.history()

    query_params = captured_requests[0].url.query_params
    assert 'direction' not in query_params or query_params['direction'] == 'backwards'


# UTS: rest/unit/RSP4b2/history-direction-forwards-1
async def test_rsp4b2_history_direction_forwards():
    channel_name = f'test-RSP4b2b-{random_id()}'
    captured_requests = []
    mock_http = capturing_mock(captured_requests, [])
    client = rest_client(mock_http)

    await client.channels.get(channel_name).presence.history(direction='forwards')

    assert captured_requests[0].url.query_params['direction'] == 'forwards'


# UTS: rest/unit/RSP4b2/history-direction-backwards-explicit-2
async def test_rsp4b2_history_direction_backwards_explicit():
    channel_name = f'test-RSP4b2c-{random_id()}'
    captured_requests = []
    mock_http = capturing_mock(captured_requests, [])
    client = rest_client(mock_http)

    await client.channels.get(channel_name).presence.history(direction='backwards')

    assert captured_requests[0].url.query_params['direction'] == 'backwards'


# UTS: rest/unit/RSP4b3/history-limit-parameter-0
async def test_rsp4b3_history_limit_parameter():
    channel_name = f'test-RSP4b3a-{random_id()}'
    captured_requests = []
    mock_http = capturing_mock(captured_requests, [])
    client = rest_client(mock_http)

    await client.channels.get(channel_name).presence.history(limit=50)

    assert captured_requests[0].url.query_params['limit'] == '50'


# UTS: rest/unit/RSP4b3/history-limit-default-100-1
async def test_rsp4b3_history_limit_default_100():
    channel_name = f'test-RSP4b3b-{random_id()}'
    captured_requests = []
    mock_http = capturing_mock(captured_requests, [])
    client = rest_client(mock_http)

    await client.channels.get(channel_name).presence.history()

    query_params = captured_requests[0].url.query_params
    assert 'limit' not in query_params or query_params['limit'] == '100'


# UTS: rest/unit/RSP4b3/history-limit-max-1000-2
async def test_rsp4b3_history_limit_max_1000():
    channel_name = f'test-RSP4b3c-{random_id()}'
    captured_requests = []
    mock_http = capturing_mock(captured_requests, [])
    client = rest_client(mock_http)

    await client.channels.get(channel_name).presence.history(limit=1000)

    assert captured_requests[0].url.query_params['limit'] == '1000'


# UTS: rest/unit/RSP4/history-all-parameters-0
async def test_rsp4_history_all_parameters():
    channel_name = f'test-RSP4-all-{random_id()}'
    captured_requests = []
    mock_http = capturing_mock(captured_requests, [])
    client = rest_client(mock_http)

    await client.channels.get(channel_name).presence.history(
        start=1609459200000,
        end=1609545600000,
        direction='forwards',
        limit=50,
    )

    query_params = captured_requests[0].url.query_params
    assert query_params['start'] == '1609459200000'
    assert query_params['end'] == '1609545600000'
    assert query_params['direction'] == 'forwards'
    assert query_params['limit'] == '50'


# UTS: rest/unit/RSP5/decode-string-data-0
async def test_rsp5_decode_string_data():
    channel_name = f'test-RSP5a-{random_id()}'
    captured_requests = []
    mock_http = capturing_mock(captured_requests, [
        {'action': 1, 'clientId': 'c1', 'data': 'plain string data'},
    ])
    client = rest_client(mock_http)

    result = await client.channels.get(channel_name).presence.get()

    assert result.items[0].data == 'plain string data'
    assert isinstance(result.items[0].data, str)


# UTS: rest/unit/RSP5/decode-json-data-1
async def test_rsp5_decode_json_data():
    channel_name = f'test-RSP5b-{random_id()}'
    captured_requests = []
    mock_http = capturing_mock(captured_requests, [
        {
            'action': 1,
            'clientId': 'c1',
            'data': '{"status":"online","count":42}',
            'encoding': 'json',
        },
    ])
    client = rest_client(mock_http)

    result = await client.channels.get(channel_name).presence.get()

    assert isinstance(result.items[0].data, dict)
    assert result.items[0].data['status'] == 'online'
    assert result.items[0].data['count'] == 42
    # NOTE: the spec asserts the consumed encoding is null; ably-python renders
    # "no remaining encoding" as the empty string.
    assert result.items[0].encoding == ''


# UTS: rest/unit/RSP5/decode-base64-binary-2
async def test_rsp5_decode_base64_binary():
    channel_name = f'test-RSP5c-{random_id()}'
    captured_requests = []
    mock_http = capturing_mock(captured_requests, [
        {
            'action': 1,
            'clientId': 'c1',
            'data': 'SGVsbG8gV29ybGQ=',  # "Hello World" in base64
            'encoding': 'base64',
        },
    ])
    client = rest_client(mock_http)

    result = await client.channels.get(channel_name).presence.get()

    assert isinstance(result.items[0].data, (bytes, bytearray))
    assert result.items[0].data == b'Hello World'
    assert result.items[0].encoding == ''


# UTS: rest/unit/RSP5/decode-msgpack-binary-3
async def test_rsp5_decode_msgpack_binary():
    channel_name = f'test-RSP5-msgpack-binary-{random_id()}'
    # Binary payload using msgpack bin type (valid UTF-8 bytes)
    binary_payload = bytes([0x73, 0x6F, 0x6D, 0x65, 0x20, 0x64, 0x61, 0x74, 0x61])  # "some data"
    body = msgpack.packb(
        [{'action': 1, 'clientId': 'client1', 'data': binary_payload}], use_bin_type=True)

    mock_http = MockHttpClient(
        on_connection_attempt=lambda conn: conn.respond_with_success(),
        on_request=lambda request: request.respond_with(
            200, body, {'Content-Type': 'application/x-msgpack'}),
    )
    client = rest_client(mock_http, use_binary_protocol=True)

    result = await client.channels.get(channel_name).presence.get()

    # Binary data must remain binary, NOT be converted to a string
    assert isinstance(result.items[0].data, (bytes, bytearray))
    assert result.items[0].data == bytes([0x73, 0x6F, 0x6D, 0x65, 0x20, 0x64, 0x61, 0x74, 0x61])
    assert result.items[0].encoding == ''


# UTS: rest/unit/RSP5/decode-utf8-data-4
async def test_rsp5_decode_utf8_data():
    channel_name = f'test-RSP5d-{random_id()}'
    captured_requests = []
    mock_http = capturing_mock(captured_requests, [
        {
            'action': 1,
            'clientId': 'c1',
            'data': 'SGVsbG8gV29ybGQ=',  # base64 of UTF-8 bytes
            'encoding': 'utf-8/base64',
        },
    ])
    client = rest_client(mock_http)

    result = await client.channels.get(channel_name).presence.get()

    assert result.items[0].data == 'Hello World'
    assert isinstance(result.items[0].data, str)


# UTS: rest/unit/RSP5/decode-chained-encoding-5
async def test_rsp5_decode_chained_encoding():
    channel_name = f'test-RSP5e-{random_id()}'
    captured_requests = []
    mock_http = capturing_mock(captured_requests, [
        {
            'action': 1,
            'clientId': 'c1',
            'data': 'eyJrZXkiOiJ2YWx1ZSJ9',  # base64 of {"key":"value"}
            'encoding': 'json/base64',
        },
    ])
    client = rest_client(mock_http)

    result = await client.channels.get(channel_name).presence.get()

    # Decoding order: base64 first, then json
    assert isinstance(result.items[0].data, dict)
    assert result.items[0].data['key'] == 'value'


# UTS: rest/unit/RSP5/decode-history-messages-6
async def test_rsp5_decode_history_messages():
    channel_name = f'test-RSP5f-{random_id()}'
    captured_requests = []
    mock_http = capturing_mock(captured_requests, [
        {
            'action': 2,
            'clientId': 'c1',
            'data': '{"event":"entered"}',
            'encoding': 'json',
        },
    ])
    client = rest_client(mock_http)

    result = await client.channels.get(channel_name).presence.history()

    assert isinstance(result.items[0].data, dict)
    assert result.items[0].data['event'] == 'entered'


# UTS: rest/unit/RSP5/decode-cipher-channel-7
async def test_rsp5_decode_cipher_channel():
    channel_name = f'test-RSP5g-{random_id()}'
    captured_requests = []
    cipher_key = base64.b64decode('WUP6u0K7MXI5Zeo0VppPwg==')
    # UTS SPEC ERROR: rest/unit/RSP5/decode-cipher-channel-7 - its encrypted_data
    # "HO4cYSP8LybPYBPZPHQOtuD53yrD3YV3NBoTEYBh4U0=" is 32 bytes (IV + one AES block), too
    # short to hold the 17-byte plaintext {"secret":"data"} it claims, and decrypts to the
    # unrelated prefix '{"example":{"jso'. Encrypted afresh here for the stated plaintext.
    encrypted_data = 'AAECAwQFBgcICQoLDA0ODy/dJbqNQwvMGpOm6Km02JmdL4cBJsQ/+VPgKjrvv5/F'

    mock_http = capturing_mock(captured_requests, [
        {
            'action': 1,
            'clientId': 'c1',
            'data': encrypted_data,
            'encoding': 'json/utf-8/cipher+aes-128-cbc/base64',
        },
    ])
    client = rest_client(mock_http)
    channel = client.channels.get(
        channel_name, cipher=CipherParams(secret_key=cipher_key, algorithm='AES', mode='CBC'))

    result = await channel.presence.get()

    # Decryption applied based on cipher+aes-128-cbc encoding
    assert isinstance(result.items[0].data, dict)
    assert result.items[0].data == {'secret': 'data'}
    assert result.items[0].encoding == ''


# UTS: rest/unit/RSP3/get-pagination-link-header-1
async def test_rsp3_get_pagination_link_header():
    channel_name = f'test-RSP-pagination1-{random_id()}'
    captured_requests = []
    mock_http = capturing_mock(
        captured_requests,
        [{'action': 1, 'clientId': 'client1'}, {'action': 1, 'clientId': 'client2'}],
        {'Link': f'</channels/{channel_name}/presence?page=2>; rel="next"'},
    )
    client = rest_client(mock_http)

    result = await client.channels.get(channel_name).presence.get()

    assert len(result.items) == 2
    assert result.has_next() is True


# UTS: rest/unit/RSP3/get-pagination-next-page-2
async def test_rsp3_get_pagination_next_page():
    channel_name = f'test-RSP-pagination2-{random_id()}'
    captured_requests = []
    request_count = 0

    def on_request(request):
        nonlocal request_count
        captured_requests.append(request)
        request_count += 1

        if request_count == 1:
            request.respond_with(
                200,
                [{'action': 1, 'clientId': 'client1'}],
                {'Link': f'</channels/{channel_name}/presence?page=2>; rel="next"'},
            )
        else:
            request.respond_with(200, [{'action': 1, 'clientId': 'client2'}])

    mock_http = MockHttpClient(
        on_connection_attempt=lambda conn: conn.respond_with_success(),
        on_request=on_request,
    )
    client = rest_client(mock_http)

    page1 = await client.channels.get(channel_name).presence.get()
    page2 = await page1.next()

    assert page1.items[0].client_id == 'client1'
    assert page2.items[0].client_id == 'client2'
    assert page2.has_next() is False


# UTS: rest/unit/RSP4/history-pagination-1
async def test_rsp4_history_pagination():
    channel_name = f'test-RSP-pagination3-{random_id()}'
    captured_requests = []
    request_count = 0

    def on_request(request):
        nonlocal request_count
        captured_requests.append(request)
        request_count += 1

        if request_count == 1:
            request.respond_with(
                200,
                [{'action': 2, 'clientId': 'c1', 'timestamp': 3000}],
                {'Link': f'</channels/{channel_name}/presence/history?page=2>; rel="next"'},
            )
        else:
            request.respond_with(200, [{'action': 4, 'clientId': 'c1', 'timestamp': 1000}])

    mock_http = MockHttpClient(
        on_connection_attempt=lambda conn: conn.respond_with_success(),
        on_request=on_request,
    )
    client = rest_client(mock_http)

    page1 = await client.channels.get(channel_name).presence.history()
    page2 = await page1.next()

    assert page1.items[0].action == PresenceAction.ENTER
    # UTS SPEC ERROR: rest/unit/RSP4/history-pagination-1 - asserts action 4 is LEAVE, but the
    # same document (RSP4a, RSP_Action_1) and the wire protocol make 4 UPDATE and 3 LEAVE.
    assert page2.items[0].action == PresenceAction.UPDATE


# UTS: rest/unit/RSP3/get-server-error-3
async def test_rsp3_get_server_error():
    channel_name = f'test-RSP-error1-{random_id()}'
    captured_requests = []
    mock_http = error_mock(captured_requests, 500, 50000, 'Internal server error')
    client = rest_client(mock_http)

    with pytest.raises(AblyException) as excinfo:
        await client.channels.get(channel_name).presence.get()

    assert excinfo.value.code == 50000
    assert excinfo.value.status_code == 500


# UTS: rest/unit/RSP4/history-auth-error-2
async def test_rsp4_history_auth_error():
    channel_name = f'test-RSP-error2-{random_id()}'
    captured_requests = []
    mock_http = error_mock(captured_requests, 401, 40101, 'Invalid credentials')
    client = rest_client(mock_http, key='invalid.key:secret')

    with pytest.raises(AblyException) as excinfo:
        await client.channels.get(channel_name).presence.history()

    assert excinfo.value.code == 40101
    assert excinfo.value.status_code == 401


# UTS: rest/unit/RSP3/get-channel-not-found-4
async def test_rsp3_get_channel_not_found():
    channel_name = f'test-RSP-error3-{random_id()}'
    captured_requests = []
    mock_http = error_mock(captured_requests, 404, 40400, 'Channel not found')
    client = rest_client(mock_http)

    with pytest.raises(AblyException) as excinfo:
        await client.channels.get(channel_name).presence.get()

    assert excinfo.value.code == 40400
    assert excinfo.value.status_code == 404


# UTS: rest/unit/RSP3/get-standard-headers-5
async def test_rsp3_get_standard_headers():
    channel_name = f'test-RSP-headers1-{random_id()}'
    captured_requests = []
    mock_http = capturing_mock(captured_requests, [])
    client = rest_client(mock_http)

    await client.channels.get(channel_name).presence.get()

    headers = captured_requests[0].headers
    assert 'X-Ably-Version' in headers
    assert 'ably-' in headers['Ably-Agent']
    assert 'Accept' in headers


# UTS: rest/unit/RSP4/history-auth-header-3
async def test_rsp4_history_auth_header():
    channel_name = f'test-RSP-headers2-{random_id()}'
    captured_requests = []
    mock_http = capturing_mock(captured_requests, [])
    client = rest_client(mock_http)

    await client.channels.get(channel_name).presence.history()

    headers = captured_requests[0].headers
    assert 'Authorization' in headers
    assert headers['Authorization'].startswith('Basic ')


# UTS: rest/unit/RSP3/get-request-id-enabled-6
async def test_rsp3_get_request_id_enabled():
    channel_name = f'test-RSP-headers3-{random_id()}'
    captured_requests = []
    mock_http = capturing_mock(captured_requests, [])
    client = rest_client(mock_http, add_request_ids=True)

    await client.channels.get(channel_name).presence.get()

    query_params = captured_requests[0].url.query_params
    assert 'request_id' in query_params
    assert query_params['request_id'] != ''


# UTS: rest/unit/RSP5/presence-action-mapping-8
async def test_rsp5_presence_action_mapping():
    channel_name = f'test-RSP-action1-{random_id()}'
    captured_requests = []
    mock_http = capturing_mock(captured_requests, [
        {'action': 0, 'clientId': 'c1'},  # absent
        {'action': 1, 'clientId': 'c2'},  # present
        {'action': 2, 'clientId': 'c3'},  # enter
        {'action': 3, 'clientId': 'c4'},  # leave
        {'action': 4, 'clientId': 'c5'},  # update
    ])
    client = rest_client(mock_http)

    result = await client.channels.get(channel_name).presence.history()

    assert result.items[0].action == PresenceAction.ABSENT
    assert result.items[1].action == PresenceAction.PRESENT
    assert result.items[2].action == PresenceAction.ENTER
    assert result.items[3].action == PresenceAction.LEAVE
    assert result.items[4].action == PresenceAction.UPDATE
