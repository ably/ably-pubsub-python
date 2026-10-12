"""Derived from uts/rest/unit/push/push_admin_apns_broadcast.md in ably/specification.

Spec points: RSH1, RSH1d
"""

import msgpack
import pytest

from ably.types.apnsbroadcast import PushApnsBroadcast
from ably.util.exceptions import AblyException
from test.uts.helpers.client import rest_client
from test.uts.helpers.mock_http import MockHttpClient

BROADCAST_RESPONSE = {'id': 'broadcast-1', 'apnsChannelId': 'apns-1'}


def capture_and_respond(captured_requests, status=201, body=None):
    def on_request(request):
        captured_requests.append(request)
        request.respond_with(status, body if body is not None else BROADCAST_RESPONSE)

    return on_request


# UTS: rest/unit/RSH1d/create-apns-broadcast-post-0
async def test_rsh1d_create_apns_broadcast_post():
    captured_requests = []
    mock_http = MockHttpClient(
        on_connection_attempt=lambda conn: conn.respond_with_success(),
        on_request=capture_and_respond(captured_requests),
    )
    client = rest_client(mock_http)

    await client.push.admin.create_apns_broadcast(message_storage_policy=1)

    assert len(captured_requests) == 1

    request = captured_requests[0]
    assert request.method == 'POST'
    assert request.url.path == '/push/apnsBroadcastChannels'


# UTS: rest/unit/RSH1d/message-storage-policy-1
async def test_rsh1d_message_storage_policy():
    captured_requests = []
    mock_http = MockHttpClient(
        on_connection_attempt=lambda conn: conn.respond_with_success(),
        on_request=capture_and_respond(captured_requests),
    )
    client = rest_client(mock_http)

    await client.push.admin.create_apns_broadcast(message_storage_policy=0)

    assert len(captured_requests) == 1

    body = msgpack.unpackb(captured_requests[0].body)
    assert body['messageStoragePolicy'] == 0


# UTS: rest/unit/RSH1d/returns-ids-2
async def test_rsh1d_returns_ids():
    mock_http = MockHttpClient(
        on_connection_attempt=lambda conn: conn.respond_with_success(),
        on_request=lambda request: request.respond_with(201, {
            'id': 'broadcast-xyz',
            'apnsChannelId': 'apple-channel-abc',
        }),
    )
    client = rest_client(mock_http)

    result = await client.push.admin.create_apns_broadcast(message_storage_policy=1)

    assert isinstance(result, PushApnsBroadcast)
    assert result.id == 'broadcast-xyz'
    assert result.apns_channel_id == 'apple-channel-abc'


# UTS: rest/unit/RSH1d/auth-header-3
async def test_rsh1d_auth_header():
    captured_requests = []
    mock_http = MockHttpClient(
        on_connection_attempt=lambda conn: conn.respond_with_success(),
        on_request=capture_and_respond(captured_requests),
    )
    client = rest_client(mock_http)

    await client.push.admin.create_apns_broadcast(message_storage_policy=1)

    assert len(captured_requests) == 1
    assert captured_requests[0].headers['Authorization'].startswith('Basic ')


# UTS: rest/unit/RSH1d/server-error-4
async def test_rsh1d_server_error():
    mock_http = MockHttpClient(
        on_connection_attempt=lambda conn: conn.respond_with_success(),
        on_request=lambda request: request.respond_with(400, {
            'error': {
                'code': 40000,
                'statusCode': 400,
                'message': 'Invalid request',
            },
        }),
    )
    client = rest_client(mock_http)

    with pytest.raises(AblyException) as excinfo:
        await client.push.admin.create_apns_broadcast(message_storage_policy=1)

    assert excinfo.value.code == 40000
