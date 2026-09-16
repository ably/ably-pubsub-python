"""Derived from uts/rest/unit/push/push_channel_subscriptions.md in ably/specification.

Spec points: RSH1c, RSH1c1, RSH1c2, RSH1c3, RSH1c4, RSH1c5
"""

import msgpack
import pytest

from ably.http.paginatedresult import PaginatedResult
from ably.types.channelsubscription import PushChannelSubscription
from ably.util.exceptions import AblyException
from test.uts.helpers.client import rest_client
from test.uts.helpers.mock_http import MockHttpClient


def capture_and_respond(captured_requests, status, body=None):
    def on_request(request):
        captured_requests.append(request)
        request.respond_with(status, body)

    return on_request


def success_mock(on_request):
    return MockHttpClient(
        on_connection_attempt=lambda conn: conn.respond_with_success(),
        on_request=on_request,
    )


# UTS: rest/unit/RSH1c1/list-filtered-by-channel-0
async def test_rsh1c1_list_filtered_by_channel():
    captured_requests = []
    mock_http = success_mock(capture_and_respond(captured_requests, 200, [
        {'channel': 'my-channel', 'deviceId': 'device-001'},
        {'channel': 'my-channel', 'clientId': 'client-abc'},
    ]))
    client = rest_client(mock_http)

    result = await client.push.admin.channel_subscriptions.list(channel='my-channel')

    assert len(captured_requests) == 1

    request = captured_requests[0]
    assert request.method == 'GET'
    assert request.url.path == '/push/channelSubscriptions'
    assert request.url.query_params['channel'] == 'my-channel'

    assert isinstance(result, PaginatedResult)
    assert len(result.items) == 2
    assert isinstance(result.items[0], PushChannelSubscription)
    assert result.items[0].channel == 'my-channel'
    assert result.items[0].device_id == 'device-001'
    assert result.items[1].client_id == 'client-abc'


# UTS: rest/unit/RSH1c1/list-filtered-by-device-client-1
async def test_rsh1c1_list_filtered_by_device_client():
    captured_requests = []
    mock_http = success_mock(capture_and_respond(captured_requests, 200, [
        {'channel': 'notifications', 'deviceId': 'device-001'},
    ]))
    client = rest_client(mock_http)

    result = await client.push.admin.channel_subscriptions.list(
        deviceId='device-001', clientId='client-abc')

    assert captured_requests[0].url.query_params['deviceId'] == 'device-001'
    assert captured_requests[0].url.query_params['clientId'] == 'client-abc'
    assert len(result.items) == 1


# UTS: rest/unit/RSH1c1/list-with-limit-param-2
async def test_rsh1c1_list_with_limit_param():
    captured_requests = []
    mock_http = success_mock(capture_and_respond(captured_requests, 200, [
        {'channel': 'ch-1', 'deviceId': 'device-001'},
    ]))
    client = rest_client(mock_http)

    await client.push.admin.channel_subscriptions.list(limit='5')

    assert captured_requests[0].url.query_params['limit'] == '5'


# UTS: rest/unit/RSH1c2/list-channels-paginated-0
async def test_rsh1c2_list_channels_paginated():
    captured_requests = []
    mock_http = success_mock(
        capture_and_respond(captured_requests, 200, ['channel-1', 'channel-2', 'channel-3']))
    client = rest_client(mock_http)

    result = await client.push.admin.channel_subscriptions.list_channels()

    assert len(captured_requests) == 1

    request = captured_requests[0]
    assert request.method == 'GET'
    assert request.url.path == '/push/channels'

    assert isinstance(result, PaginatedResult)
    assert len(result.items) == 3
    assert result.items[0] == 'channel-1'
    assert result.items[1] == 'channel-2'
    assert result.items[2] == 'channel-3'


# UTS: rest/unit/RSH1c2/list-channels-with-limit-1
async def test_rsh1c2_list_channels_with_limit():
    captured_requests = []
    mock_http = success_mock(capture_and_respond(captured_requests, 200, ['channel-1']))
    client = rest_client(mock_http)

    result = await client.push.admin.channel_subscriptions.list_channels(limit='1')

    assert captured_requests[0].url.query_params['limit'] == '1'
    assert len(result.items) == 1


# UTS: rest/unit/RSH1c3/save-post-subscription-0
async def test_rsh1c3_save_post_subscription():
    captured_requests = []
    mock_http = success_mock(capture_and_respond(captured_requests, 200, {
        'channel': 'my-channel',
        'deviceId': 'device-001',
    }))
    client = rest_client(mock_http)

    subscription = PushChannelSubscription(channel='my-channel', device_id='device-001')

    result = await client.push.admin.channel_subscriptions.save(subscription)

    assert len(captured_requests) == 1

    request = captured_requests[0]
    assert request.method == 'POST'
    assert request.url.path == '/push/channelSubscriptions'

    body = msgpack.unpackb(request.body)
    assert body['channel'] == 'my-channel'
    assert body['deviceId'] == 'device-001'

    assert isinstance(result, PushChannelSubscription)
    assert result.channel == 'my-channel'
    assert result.device_id == 'device-001'


# UTS: rest/unit/RSH1c3/save-updates-existing-1
async def test_rsh1c3_save_updates_existing():
    request_count = 0

    def on_request(request):
        nonlocal request_count
        request_count += 1
        if request_count == 1:
            request.respond_with(200, {'channel': 'my-channel', 'clientId': 'client-abc'})
        else:
            request.respond_with(200, {'channel': 'my-channel', 'clientId': 'client-abc'})

    mock_http = success_mock(on_request)
    client = rest_client(mock_http)

    subscription = PushChannelSubscription(channel='my-channel', client_id='client-abc')

    result1 = await client.push.admin.channel_subscriptions.save(subscription)
    result2 = await client.push.admin.channel_subscriptions.save(subscription)

    assert request_count == 2
    assert result1.channel == 'my-channel'
    assert result2.channel == 'my-channel'


# UTS: rest/unit/RSH1c3/save-error-propagated-2
async def test_rsh1c3_save_error_propagated():
    mock_http = success_mock(lambda request: request.respond_with(400, {
        'error': {
            'code': 40000,
            'statusCode': 400,
            'message': 'Invalid subscription',
        },
    }))
    client = rest_client(mock_http)

    subscription = PushChannelSubscription(channel='my-channel', device_id='device-001')

    with pytest.raises(AblyException) as excinfo:
        await client.push.admin.channel_subscriptions.save(subscription)

    assert excinfo.value.code == 40000
    assert excinfo.value.status_code == 400


# UTS: rest/unit/RSH1c4/remove-delete-clientid-0
async def test_rsh1c4_remove_delete_clientid():
    captured_requests = []
    mock_http = success_mock(capture_and_respond(captured_requests, 204))
    client = rest_client(mock_http)

    subscription = PushChannelSubscription(channel='my-channel', client_id='client-abc')

    await client.push.admin.channel_subscriptions.remove(subscription)

    assert len(captured_requests) == 1

    request = captured_requests[0]
    assert request.method == 'DELETE'
    assert request.url.path == '/push/channelSubscriptions'
    assert request.url.query_params['channel'] == 'my-channel'
    assert request.url.query_params['clientId'] == 'client-abc'


# UTS: rest/unit/RSH1c4/remove-delete-deviceid-1
async def test_rsh1c4_remove_delete_deviceid():
    captured_requests = []
    mock_http = success_mock(capture_and_respond(captured_requests, 204))
    client = rest_client(mock_http)

    subscription = PushChannelSubscription(channel='my-channel', device_id='device-001')

    await client.push.admin.channel_subscriptions.remove(subscription)

    assert captured_requests[0].method == 'DELETE'
    assert captured_requests[0].url.path == '/push/channelSubscriptions'
    assert captured_requests[0].url.query_params['channel'] == 'my-channel'
    assert captured_requests[0].url.query_params['deviceId'] == 'device-001'


# UTS: rest/unit/RSH1c4/remove-nonexistent-succeeds-2
async def test_rsh1c4_remove_nonexistent_succeeds():
    mock_http = success_mock(lambda request: request.respond_with(204, None))
    client = rest_client(mock_http)

    subscription = PushChannelSubscription(
        channel='nonexistent-channel', client_id='nonexistent-client')

    await client.push.admin.channel_subscriptions.remove(subscription)


# UTS: rest/unit/RSH1c5/remove-where-clientid-0
async def test_rsh1c5_remove_where_clientid():
    captured_requests = []
    mock_http = success_mock(capture_and_respond(captured_requests, 204))
    client = rest_client(mock_http)

    await client.push.admin.channel_subscriptions.remove_where(clientId='client-abc')

    assert len(captured_requests) == 1

    request = captured_requests[0]
    assert request.method == 'DELETE'
    assert request.url.path == '/push/channelSubscriptions'
    assert request.url.query_params['clientId'] == 'client-abc'


# UTS: rest/unit/RSH1c5/remove-where-deviceid-1
async def test_rsh1c5_remove_where_deviceid():
    captured_requests = []
    mock_http = success_mock(capture_and_respond(captured_requests, 204))
    client = rest_client(mock_http)

    await client.push.admin.channel_subscriptions.remove_where(deviceId='device-001')

    assert captured_requests[0].method == 'DELETE'
    assert captured_requests[0].url.path == '/push/channelSubscriptions'
    assert captured_requests[0].url.query_params['deviceId'] == 'device-001'


# UTS: rest/unit/RSH1c5/remove-where-no-match-succeeds-2
async def test_rsh1c5_remove_where_no_match_succeeds():
    mock_http = success_mock(lambda request: request.respond_with(204, None))
    client = rest_client(mock_http)

    await client.push.admin.channel_subscriptions.remove_where(clientId='nonexistent-client')
