"""Derived from uts/rest/unit/push/push_channels.md in ably/specification.

Spec points: RSH7, RSH7a, RSH7a1, RSH7a2, RSH7a3, RSH7b, RSH7b1, RSH7b2, RSH7c,
RSH7c1, RSH7c2, RSH7c3, RSH7d, RSH7d1, RSH7d2, RSH7e

DEVIATION: ably-python implements neither the PushChannel interface (RSH7, the
``push`` field on a channel) nor LocalDevice (RSH8), so every test in this file
is gated behind RUN_DEVIATIONS. The assertions are written against the spec, using
the names ably-python would use for these APIs: ``client.device``,
``ably.types.device.LocalDevice`` and ``channel.push.subscribe_device()`` and
friends. Running them raises ImportError/AttributeError until the APIs land.
"""

import msgpack
import pytest

from ably.http.paginatedresult import PaginatedResult
from ably.types.channelsubscription import PushChannelSubscription
from ably.util.exceptions import AblyException
from test.uts.helpers.client import rest_client
from test.uts.helpers.deviations import deviation
from test.uts.helpers.mock_http import MockHttpClient

DEVICE_ID = 'test-device-001'
DEVICE_IDENTITY_TOKEN = 'test-device-identity-token'
CLIENT_ID = 'test-client'
CHANNEL_NAME = 'my-channel'


def set_local_device(client, device_id=DEVICE_ID, device_identity_token=DEVICE_IDENTITY_TOKEN,
                     client_id=CLIENT_ID):
    """Configure the client's local device, standing in for the spec's ``client.device = ...``."""
    from ably.types.device import LocalDevice

    client.device = LocalDevice(
        id=device_id,
        device_identity_token=device_identity_token,
        client_id=client_id,
    )


def capture_and_respond(captured_requests, status, body=None):
    def on_request(request):
        captured_requests.append(request)
        request.respond_with(status, body)

    return on_request


def assert_message_mentions(error, field):
    """Assert the error names `field`, tolerating a snake_case rendering of it."""
    normalised = error.message.lower().replace('_', '')
    assert field.lower() in normalised


# UTS: rest/unit/RSH7a2/subscribe-device-post-0
@deviation
async def test_rsh7a2_subscribe_device_post():
    captured_requests = []
    mock_http = MockHttpClient(
        on_connection_attempt=lambda conn: conn.respond_with_success(),
        on_request=capture_and_respond(captured_requests, 200, {
            'channel': CHANNEL_NAME,
            'deviceId': DEVICE_ID,
        }),
    )
    client = rest_client(mock_http)
    set_local_device(client)
    channel = client.channels.get(CHANNEL_NAME)

    await channel.push.subscribe_device()

    assert len(captured_requests) == 1

    request = captured_requests[0]
    assert request.method == 'POST'
    assert request.url.path == '/push/channelSubscriptions'

    body = msgpack.unpackb(request.body)
    assert body['channel'] == CHANNEL_NAME
    assert body['deviceId'] == DEVICE_ID

    # RSH7a3 + RSH6a - push device authentication via deviceIdentityToken
    assert request.headers['X-Ably-DeviceToken'] == DEVICE_IDENTITY_TOKEN


# UTS: rest/unit/RSH7a1/subscribe-device-no-token-fails-0
@deviation
async def test_rsh7a1_subscribe_device_no_token_fails():
    mock_http = MockHttpClient(
        on_connection_attempt=lambda conn: conn.respond_with_success(),
        on_request=lambda request: request.respond_with(200, {}),
    )
    client = rest_client(mock_http)
    set_local_device(client, device_identity_token=None)
    channel = client.channels.get(CHANNEL_NAME)

    with pytest.raises(AblyException) as excinfo:
        await channel.push.subscribe_device()

    assert excinfo.value.code is not None
    assert_message_mentions(excinfo.value, 'deviceIdentityToken')


# UTS: rest/unit/RSH7b2/subscribe-client-post-0
@deviation
async def test_rsh7b2_subscribe_client_post():
    captured_requests = []
    mock_http = MockHttpClient(
        on_connection_attempt=lambda conn: conn.respond_with_success(),
        on_request=capture_and_respond(captured_requests, 200, {
            'channel': CHANNEL_NAME,
            'clientId': CLIENT_ID,
        }),
    )
    client = rest_client(mock_http)
    set_local_device(client)
    channel = client.channels.get(CHANNEL_NAME)

    await channel.push.subscribe_client()

    assert len(captured_requests) == 1

    request = captured_requests[0]
    assert request.method == 'POST'
    assert request.url.path == '/push/channelSubscriptions'

    body = msgpack.unpackb(request.body)
    assert body['channel'] == CHANNEL_NAME
    assert body['clientId'] == CLIENT_ID


# UTS: rest/unit/RSH7b1/subscribe-client-no-clientid-fails-0
@deviation
async def test_rsh7b1_subscribe_client_no_clientid_fails():
    mock_http = MockHttpClient(
        on_connection_attempt=lambda conn: conn.respond_with_success(),
        on_request=lambda request: request.respond_with(200, {}),
    )
    client = rest_client(mock_http)
    set_local_device(client, client_id=None)
    channel = client.channels.get(CHANNEL_NAME)

    with pytest.raises(AblyException) as excinfo:
        await channel.push.subscribe_client()

    assert excinfo.value.code is not None
    assert_message_mentions(excinfo.value, 'clientId')


# UTS: rest/unit/RSH7c2/unsubscribe-device-delete-0
@deviation
async def test_rsh7c2_unsubscribe_device_delete():
    captured_requests = []
    mock_http = MockHttpClient(
        on_connection_attempt=lambda conn: conn.respond_with_success(),
        on_request=capture_and_respond(captured_requests, 204, None),
    )
    client = rest_client(mock_http)
    set_local_device(client)
    channel = client.channels.get(CHANNEL_NAME)

    await channel.push.unsubscribe_device()

    assert len(captured_requests) == 1

    request = captured_requests[0]
    assert request.method == 'DELETE'
    assert request.url.path == '/push/channelSubscriptions'
    assert request.url.query_params['channel'] == CHANNEL_NAME
    assert request.url.query_params['deviceId'] == DEVICE_ID

    # RSH7c3 + RSH6a - push device authentication via deviceIdentityToken
    assert request.headers['X-Ably-DeviceToken'] == DEVICE_IDENTITY_TOKEN


# UTS: rest/unit/RSH7c1/unsubscribe-device-no-token-fails-0
@deviation
async def test_rsh7c1_unsubscribe_device_no_token_fails():
    mock_http = MockHttpClient(
        on_connection_attempt=lambda conn: conn.respond_with_success(),
        on_request=lambda request: request.respond_with(204, None),
    )
    client = rest_client(mock_http)
    set_local_device(client, device_identity_token=None)
    channel = client.channels.get(CHANNEL_NAME)

    with pytest.raises(AblyException) as excinfo:
        await channel.push.unsubscribe_device()

    assert excinfo.value.code is not None
    assert_message_mentions(excinfo.value, 'deviceIdentityToken')


# UTS: rest/unit/RSH7d2/unsubscribe-client-delete-0
@deviation
async def test_rsh7d2_unsubscribe_client_delete():
    captured_requests = []
    mock_http = MockHttpClient(
        on_connection_attempt=lambda conn: conn.respond_with_success(),
        on_request=capture_and_respond(captured_requests, 204, None),
    )
    client = rest_client(mock_http)
    set_local_device(client)
    channel = client.channels.get(CHANNEL_NAME)

    await channel.push.unsubscribe_client()

    assert len(captured_requests) == 1

    request = captured_requests[0]
    assert request.method == 'DELETE'
    assert request.url.path == '/push/channelSubscriptions'
    assert request.url.query_params['channel'] == CHANNEL_NAME
    assert request.url.query_params['clientId'] == CLIENT_ID


# UTS: rest/unit/RSH7d1/unsubscribe-client-no-clientid-fails-0
@deviation
async def test_rsh7d1_unsubscribe_client_no_clientid_fails():
    mock_http = MockHttpClient(
        on_connection_attempt=lambda conn: conn.respond_with_success(),
        on_request=lambda request: request.respond_with(204, None),
    )
    client = rest_client(mock_http)
    set_local_device(client, client_id=None)
    channel = client.channels.get(CHANNEL_NAME)

    with pytest.raises(AblyException) as excinfo:
        await channel.push.unsubscribe_client()

    assert excinfo.value.code is not None
    assert_message_mentions(excinfo.value, 'clientId')


# UTS: rest/unit/RSH7e/list-subscriptions-with-filters-0
@deviation
async def test_rsh7e_list_subscriptions_with_filters():
    captured_requests = []
    mock_http = MockHttpClient(
        on_connection_attempt=lambda conn: conn.respond_with_success(),
        on_request=capture_and_respond(captured_requests, 200, [
            {
                'channel': CHANNEL_NAME,
                'deviceId': DEVICE_ID,
            },
            {
                'channel': CHANNEL_NAME,
                'clientId': CLIENT_ID,
            },
        ]),
    )
    client = rest_client(mock_http)
    set_local_device(client)
    channel = client.channels.get(CHANNEL_NAME)

    result = await channel.push.list_subscriptions(limit='10')

    assert len(captured_requests) == 1

    request = captured_requests[0]
    assert request.method == 'GET'
    assert request.url.path == '/push/channelSubscriptions'

    # Channel name, device ID, and client ID are automatically included
    assert request.url.query_params['channel'] == CHANNEL_NAME
    assert request.url.query_params['deviceId'] == DEVICE_ID
    assert request.url.query_params['clientId'] == CLIENT_ID

    # concatFilters must be set to true
    assert request.url.query_params['concatFilters'] == 'true'

    # User-provided params are forwarded
    assert request.url.query_params['limit'] == '10'

    assert isinstance(result, PaginatedResult)
    assert len(result.items) == 2
    assert isinstance(result.items[0], PushChannelSubscription)
    assert result.items[0].channel == CHANNEL_NAME
    assert result.items[0].device_id == DEVICE_ID
    assert result.items[1].client_id == CLIENT_ID


# UTS: rest/unit/RSH7e/list-subscriptions-omits-clientid-1
@deviation
async def test_rsh7e_list_subscriptions_omits_clientid():
    captured_requests = []
    mock_http = MockHttpClient(
        on_connection_attempt=lambda conn: conn.respond_with_success(),
        on_request=capture_and_respond(captured_requests, 200, [
            {
                'channel': CHANNEL_NAME,
                'deviceId': DEVICE_ID,
            },
        ]),
    )
    client = rest_client(mock_http)
    set_local_device(client, client_id=None)
    channel = client.channels.get(CHANNEL_NAME)

    result = await channel.push.list_subscriptions()

    request = captured_requests[0]
    assert request.url.query_params['channel'] == CHANNEL_NAME
    assert request.url.query_params['deviceId'] == DEVICE_ID
    assert request.url.query_params['concatFilters'] == 'true'
    assert 'clientId' not in request.url.query_params

    assert len(result.items) == 1
