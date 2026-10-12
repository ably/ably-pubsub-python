"""Derived from uts/rest/unit/push/push_admin_live_activity.md in ably/specification.

Spec points: RSH1, RSH1e, RSH1e1, RSH1e2, RSH1e3
"""

from urllib.parse import quote

import msgpack
import pytest

from ably.util.exceptions import AblyException
from test.uts.helpers.client import rest_client
from test.uts.helpers.mock_http import MockHttpClient

APNS_HEADERS = {'apns-priority': '10', 'apns-expiration': '1782948701'}

SERVER_ERROR = {
    'error': {
        'code': 40000,
        'statusCode': 400,
        'message': 'Invalid request',
    },
}


def capture_and_respond(captured_requests, status=200, body=None):
    def on_request(request):
        captured_requests.append(request)
        request.respond_with(status, body if body is not None else {})

    return on_request


def capturing_client(captured_requests):
    mock_http = MockHttpClient(
        on_connection_attempt=lambda conn: conn.respond_with_success(),
        on_request=capture_and_respond(captured_requests),
    )
    return rest_client(mock_http)


def failing_client():
    mock_http = MockHttpClient(
        on_connection_attempt=lambda conn: conn.respond_with_success(),
        on_request=lambda request: request.respond_with(400, SERVER_ERROR),
    )
    return rest_client(mock_http)


# UTS: rest/unit/RSH1e1/start-post-0
async def test_rsh1e1_start_post():
    captured_requests = []
    client = capturing_client(captured_requests)

    await client.push.admin.live_activity.start(
        recipient={'channels': ['nba:lakers', 'nba:celtics']},
        apns_broadcast='broadcast-1',
        apns={'aps': {'event': 'start', 'attributes-type': 'GameAttributes'}},
        headers=APNS_HEADERS,
    )

    assert len(captured_requests) == 1

    request = captured_requests[0]
    assert request.method == 'POST'
    assert request.url.path == '/push/apnsBroadcastChannels/broadcast-1/start'

    body = msgpack.unpackb(request.body)
    assert body['channels'] == ['nba:lakers', 'nba:celtics']
    assert body['apns']['aps']['event'] == 'start'
    assert 'deviceId' not in body
    assert body['headers'] == APNS_HEADERS
    assert request.headers['Authorization'].startswith('Basic ')


# UTS: rest/unit/RSH1e1/start-deviceid-encode-1
async def test_rsh1e1_start_deviceid_encode():
    captured_requests = []
    client = capturing_client(captured_requests)

    await client.push.admin.live_activity.start(
        recipient={'deviceId': 'device-7'},
        apns_broadcast='broadcast/with space',
        apns={'aps': {'event': 'start'}},
    )

    assert len(captured_requests) == 1

    request = captured_requests[0]
    # url.path is percent-decoded, so the encoding the spec asserts on is read off raw_path
    encoded_id = quote('broadcast/with space', safe='')
    assert request.url.raw_path == '/push/apnsBroadcastChannels/' + encoded_id + '/start'

    body = msgpack.unpackb(request.body)
    assert body['deviceId'] == 'device-7'
    assert 'channels' not in body


# UTS: rest/unit/RSH1e2/update-post-0
async def test_rsh1e2_update_post():
    captured_requests = []
    client = capturing_client(captured_requests)

    await client.push.admin.live_activity.update(
        apns_broadcast='broadcast-1',
        apns={'aps': {'event': 'update', 'content-state': {'homeScore': 14}}},
        headers=APNS_HEADERS,
    )

    assert len(captured_requests) == 1

    request = captured_requests[0]
    assert request.method == 'POST'
    assert request.url.path == '/push/apnsBroadcastChannels/broadcast-1/broadcast'

    body = msgpack.unpackb(request.body)
    assert body['apns']['aps']['event'] == 'update'
    # The optional APNs delivery headers are sent in the request body under a "headers" key
    assert body['headers'] == APNS_HEADERS
    assert request.headers['Authorization'].startswith('Basic ')


# UTS: rest/unit/RSH1e2/update-no-headers-1
async def test_rsh1e2_update_no_headers():
    captured_requests = []
    client = capturing_client(captured_requests)

    await client.push.admin.live_activity.update(
        apns_broadcast='broadcast-1',
        apns={'aps': {'event': 'update', 'content-state': {}}},
    )

    assert len(captured_requests) == 1

    body = msgpack.unpackb(captured_requests[0].body)
    assert body['apns']['aps']['event'] == 'update'
    assert 'headers' not in body


# UTS: rest/unit/RSH1e3/end-post-0
async def test_rsh1e3_end_post():
    captured_requests = []
    client = capturing_client(captured_requests)

    await client.push.admin.live_activity.end(
        apns_broadcast='broadcast-1',
        apns={'aps': {'event': 'end', 'content-state': {'homeScore': 112}, 'dismissal-date': 1700000000}},
    )

    assert len(captured_requests) == 1

    request = captured_requests[0]
    assert request.method == 'POST'
    assert request.url.path == '/push/apnsBroadcastChannels/broadcast-1/end'

    body = msgpack.unpackb(request.body)
    assert body['apns']['aps']['event'] == 'end'
    assert body['apns']['aps']['dismissal-date'] == 1700000000
    assert request.headers['Authorization'].startswith('Basic ')


# UTS: rest/unit/RSH1e1/server-error-2
async def test_rsh1e1_server_error():
    client = failing_client()

    with pytest.raises(AblyException) as excinfo:
        await client.push.admin.live_activity.start(
            recipient={'channels': ['nba:lakers']},
            apns_broadcast='broadcast-1',
            apns={},
        )

    assert excinfo.value.code == 40000


# UTS: rest/unit/RSH1e2/server-error-2
async def test_rsh1e2_server_error():
    client = failing_client()

    with pytest.raises(AblyException) as excinfo:
        await client.push.admin.live_activity.update(apns_broadcast='broadcast-1', apns={})

    assert excinfo.value.code == 40000


# UTS: rest/unit/RSH1e3/server-error-1
async def test_rsh1e3_server_error():
    client = failing_client()

    with pytest.raises(AblyException) as excinfo:
        await client.push.admin.live_activity.end(apns_broadcast='broadcast-1', apns={})

    assert excinfo.value.code == 40000
