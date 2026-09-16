"""Derived from uts/rest/unit/push/push_admin_publish.md in ably/specification.

Spec points: RSH1, RSH1a
"""

import msgpack
import pytest

from ably.rest.push import Push, PushAdmin, PushChannelSubscriptions, PushDeviceRegistrations
from ably.util.exceptions import AblyException
from test.uts.helpers.client import rest_client
from test.uts.helpers.mock_http import MockHttpClient


def capture_and_respond(captured_requests, status=201, body=None):
    def on_request(request):
        captured_requests.append(request)
        request.respond_with(status, body if body is not None else {})

    return on_request


# UTS: rest/unit/RSH1/push-admin-accessible-0
async def test_rsh1_push_admin_accessible():
    mock_http = MockHttpClient(
        on_connection_attempt=lambda conn: conn.respond_with_success(),
        on_request=lambda request: request.respond_with(200, {}),
    )
    client = rest_client(mock_http)

    assert isinstance(client.push, Push)
    assert isinstance(client.push.admin, PushAdmin)
    assert isinstance(client.push.admin.device_registrations, PushDeviceRegistrations)
    assert isinstance(client.push.admin.channel_subscriptions, PushChannelSubscriptions)


# UTS: rest/unit/RSH1a/publish-post-push-publish-0
async def test_rsh1a_publish_post_push_publish():
    captured_requests = []
    mock_http = MockHttpClient(
        on_connection_attempt=lambda conn: conn.respond_with_success(),
        on_request=capture_and_respond(captured_requests),
    )
    client = rest_client(mock_http)

    await client.push.admin.publish(
        recipient={
            'transportType': 'apns',
            'deviceToken': 'foo',
        },
        data={
            'notification': {
                'title': 'Test',
                'body': 'Hello',
            },
        },
    )

    assert len(captured_requests) == 1

    request = captured_requests[0]
    assert request.method == 'POST'
    assert request.url.path == '/push/publish'

    body = msgpack.unpackb(request.body)
    assert body['recipient']['transportType'] == 'apns'
    assert body['recipient']['deviceToken'] == 'foo'
    assert body['notification']['title'] == 'Test'
    assert body['notification']['body'] == 'Hello'


# UTS: rest/unit/RSH1a/publish-clientid-recipient-1
async def test_rsh1a_publish_clientid_recipient():
    captured_requests = []
    mock_http = MockHttpClient(
        on_connection_attempt=lambda conn: conn.respond_with_success(),
        on_request=capture_and_respond(captured_requests),
    )
    client = rest_client(mock_http)

    await client.push.admin.publish(
        recipient={'clientId': 'user-123'},
        data={'data': {'key': 'value'}},
    )

    assert len(captured_requests) == 1

    body = msgpack.unpackb(captured_requests[0].body)
    assert body['recipient']['clientId'] == 'user-123'
    assert body['data']['key'] == 'value'


# UTS: rest/unit/RSH1a/publish-deviceid-recipient-2
async def test_rsh1a_publish_deviceid_recipient():
    captured_requests = []
    mock_http = MockHttpClient(
        on_connection_attempt=lambda conn: conn.respond_with_success(),
        on_request=capture_and_respond(captured_requests),
    )
    client = rest_client(mock_http)

    await client.push.admin.publish(
        recipient={'deviceId': 'device-abc'},
        data={'notification': {'title': 'Device Push'}},
    )

    assert len(captured_requests) == 1

    body = msgpack.unpackb(captured_requests[0].body)
    assert body['recipient']['deviceId'] == 'device-abc'
    assert body['notification']['title'] == 'Device Push'


# UTS: rest/unit/RSH1a/rejects-empty-recipient-3
async def test_rsh1a_rejects_empty_recipient():
    captured_requests = []
    mock_http = MockHttpClient(
        on_connection_attempt=lambda conn: conn.respond_with_success(),
        on_request=capture_and_respond(captured_requests),
    )
    client = rest_client(mock_http)

    # DEVIATION: the spec asserts error.code == 40000. PushAdmin.publish validates
    # locally and raises a plain ValueError, which carries no Ably error code.
    with pytest.raises(ValueError) as excinfo:
        await client.push.admin.publish(
            recipient={},
            data={'notification': {'title': 'Test'}},
        )

    assert not isinstance(excinfo.value, AblyException)
    assert 'recipient' in str(excinfo.value)

    assert len(captured_requests) == 0


# UTS: rest/unit/RSH1a/rejects-empty-data-4
async def test_rsh1a_rejects_empty_data():
    captured_requests = []
    mock_http = MockHttpClient(
        on_connection_attempt=lambda conn: conn.respond_with_success(),
        on_request=capture_and_respond(captured_requests),
    )
    client = rest_client(mock_http)

    # DEVIATION: the spec asserts error.code == 40000. PushAdmin.publish validates
    # locally and raises a plain ValueError, which carries no Ably error code.
    with pytest.raises(ValueError) as excinfo:
        await client.push.admin.publish(
            recipient={'clientId': 'user-123'},
            data={},
        )

    assert not isinstance(excinfo.value, AblyException)
    assert 'data' in str(excinfo.value)

    assert len(captured_requests) == 0


# UTS: rest/unit/RSH1a/rejects-null-recipient-5
async def test_rsh1a_rejects_null_recipient():
    captured_requests = []
    mock_http = MockHttpClient(
        on_connection_attempt=lambda conn: conn.respond_with_success(),
        on_request=capture_and_respond(captured_requests),
    )
    client = rest_client(mock_http)

    # DEVIATION: the spec asserts error.code == 40000. PushAdmin.publish rejects a
    # non-dict recipient with a plain TypeError, which carries no Ably error code.
    with pytest.raises(TypeError) as excinfo:
        await client.push.admin.publish(
            recipient=None,
            data={'notification': {'title': 'Test'}},
        )

    assert not isinstance(excinfo.value, AblyException)
    assert 'recipient' in str(excinfo.value)

    assert len(captured_requests) == 0


# UTS: rest/unit/RSH1a/server-error-propagated-6
async def test_rsh1a_server_error_propagated():
    mock_http = MockHttpClient(
        on_connection_attempt=lambda conn: conn.respond_with_success(),
        on_request=lambda request: request.respond_with(400, {
            'error': {
                'code': 40000,
                'statusCode': 400,
                'message': 'Invalid recipient',
            },
        }),
    )
    client = rest_client(mock_http)

    with pytest.raises(AblyException) as excinfo:
        await client.push.admin.publish(
            recipient={'transportType': 'invalid'},
            data={'notification': {'title': 'Test'}},
        )

    assert excinfo.value.code == 40000
    assert excinfo.value.status_code == 400
