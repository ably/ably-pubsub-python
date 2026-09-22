"""Derived from uts/rest/unit/push/push_device_registrations.md in ably/specification.

Spec points: RSH1b, RSH1b1, RSH1b2, RSH1b3, RSH1b4, RSH1b5
"""

from urllib.parse import quote

import msgpack
import pytest

from ably.http.paginatedresult import PaginatedResult
from ably.types.device import DeviceDetails
from ably.util.exceptions import AblyException
from test.uts.helpers.client import rest_client
from test.uts.helpers.deviations import deviation
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


# UTS: rest/unit/RSH1b1/get-device-details-0
async def test_rsh1b1_get_device_details():
    captured_requests = []
    mock_http = success_mock(capture_and_respond(captured_requests, 200, {
        'id': 'device-001',
        'clientId': 'client-abc',
        'formFactor': 'phone',
        'platform': 'ios',
        'metadata': {'model': 'iPhone 14'},
        'push': {
            'recipient': {'transportType': 'apns', 'deviceToken': 'token-123'},
            'state': 'Active',
        },
    }))
    client = rest_client(mock_http)

    device = await client.push.admin.device_registrations.get('device-001')

    assert len(captured_requests) == 1

    request = captured_requests[0]
    assert request.method == 'GET'
    assert request.url.path == '/push/deviceRegistrations/' + 'device-001'

    assert isinstance(device, DeviceDetails)
    assert device.id == 'device-001'
    assert device.client_id == 'client-abc'
    assert device.form_factor == 'phone'
    assert device.platform == 'ios'
    assert device.metadata['model'] == 'iPhone 14'
    # NOTE: the spec models push as a DevicePushDetails object. DeviceDetails.push is a
    # plain dict here, so the same values are read by key.
    assert device.push['recipient']['transportType'] == 'apns'
    assert device.push['state'] == 'Active'


# UTS: rest/unit/RSH1b1/get-unknown-device-error-1
async def test_rsh1b1_get_unknown_device_error():
    mock_http = success_mock(lambda request: request.respond_with(404, {
        'error': {
            'code': 40400,
            'statusCode': 404,
            'message': 'Device not found',
        },
    }))
    client = rest_client(mock_http)

    with pytest.raises(AblyException) as excinfo:
        await client.push.admin.device_registrations.get('nonexistent-device')

    assert excinfo.value.code == 40400
    assert excinfo.value.status_code == 404


# UTS: rest/unit/RSH1b1/get-url-encodes-deviceid-2
@deviation
async def test_rsh1b1_get_url_encodes_deviceid():
    # DEVIATION: PushDeviceRegistrations.get interpolates device_id into the path without
    # percent-encoding it, so "device/with special:chars" becomes extra path segments.
    device_id = 'device/with special:chars'
    captured_requests = []
    mock_http = success_mock(capture_and_respond(captured_requests, 200, {
        'id': device_id,
        'platform': 'ios',
        'formFactor': 'phone',
        'push': {'recipient': {}, 'state': 'Active'},
    }))
    client = rest_client(mock_http)

    await client.push.admin.device_registrations.get(device_id)

    # NOTE: the spec asserts on url.path, which the mock exposes percent-decoded, so the
    # encoding is only observable in the raw request URL.
    assert str(captured_requests[0].url).endswith(
        '/push/deviceRegistrations/' + quote(device_id, safe=''))


# UTS: rest/unit/RSH1b2/list-filtered-by-deviceid-0
async def test_rsh1b2_list_filtered_by_deviceid():
    captured_requests = []
    mock_http = success_mock(capture_and_respond(captured_requests, 200, [
        {
            'id': 'device-001',
            'clientId': 'client-abc',
            'platform': 'ios',
            'formFactor': 'phone',
            'push': {'recipient': {}, 'state': 'Active'},
        },
    ]))
    client = rest_client(mock_http)

    result = await client.push.admin.device_registrations.list(deviceId='device-001')

    assert len(captured_requests) == 1

    request = captured_requests[0]
    assert request.method == 'GET'
    assert request.url.path == '/push/deviceRegistrations'
    assert request.url.query_params['deviceId'] == 'device-001'

    assert isinstance(result, PaginatedResult)
    assert len(result.items) == 1
    assert isinstance(result.items[0], DeviceDetails)
    assert result.items[0].id == 'device-001'


# UTS: rest/unit/RSH1b2/list-filtered-by-clientid-1
async def test_rsh1b2_list_filtered_by_clientid():
    captured_requests = []
    mock_http = success_mock(capture_and_respond(captured_requests, 200, [
        {
            'id': 'device-001',
            'clientId': 'client-abc',
            'platform': 'ios',
            'formFactor': 'phone',
            'push': {'recipient': {}, 'state': 'Active'},
        },
        {
            'id': 'device-002',
            'clientId': 'client-abc',
            'platform': 'android',
            'formFactor': 'tablet',
            'push': {'recipient': {}, 'state': 'Active'},
        },
    ]))
    client = rest_client(mock_http)

    result = await client.push.admin.device_registrations.list(clientId='client-abc')

    assert captured_requests[0].url.query_params['clientId'] == 'client-abc'
    assert len(result.items) == 2
    assert result.items[0].client_id == 'client-abc'
    assert result.items[1].client_id == 'client-abc'


# UTS: rest/unit/RSH1b2/list-with-limit-param-2
async def test_rsh1b2_list_with_limit_param():
    captured_requests = []
    mock_http = success_mock(capture_and_respond(captured_requests, 200, [
        {
            'id': 'device-001',
            'platform': 'ios',
            'formFactor': 'phone',
            'push': {'recipient': {}, 'state': 'Active'},
        },
    ]))
    client = rest_client(mock_http)

    await client.push.admin.device_registrations.list(limit='2')

    assert captured_requests[0].url.query_params['limit'] == '2'


# UTS: rest/unit/RSH1b3/save-put-device-details-0
async def test_rsh1b3_save_put_device_details():
    captured_requests = []
    mock_http = success_mock(capture_and_respond(captured_requests, 200, {
        'id': 'device-001',
        'clientId': 'client-abc',
        'platform': 'ios',
        'formFactor': 'phone',
        'metadata': {},
        'push': {
            'recipient': {'transportType': 'apns', 'deviceToken': 'token-123'},
            'state': 'Active',
        },
    }))
    client = rest_client(mock_http)

    device = DeviceDetails(
        id='device-001',
        client_id='client-abc',
        platform='ios',
        form_factor='phone',
        push={'recipient': {'transportType': 'apns', 'deviceToken': 'token-123'}},
    )

    result = await client.push.admin.device_registrations.save(device)

    assert len(captured_requests) == 1

    request = captured_requests[0]
    assert request.method == 'PUT'
    assert request.url.path == '/push/deviceRegistrations/' + 'device-001'

    body = msgpack.unpackb(request.body)
    assert body['id'] == 'device-001'
    assert body['clientId'] == 'client-abc'
    assert body['platform'] == 'ios'
    assert body['formFactor'] == 'phone'
    assert body['push']['recipient']['transportType'] == 'apns'

    assert isinstance(result, DeviceDetails)
    assert result.id == 'device-001'
    assert result.push['state'] == 'Active'


# UTS: rest/unit/RSH1b3/save-updates-existing-1
async def test_rsh1b3_save_updates_existing():
    request_count = 0

    def on_request(request):
        nonlocal request_count
        request_count += 1
        if request_count == 1:
            request.respond_with(200, {
                'id': 'device-001',
                'platform': 'ios',
                'formFactor': 'phone',
                'push': {
                    'recipient': {'transportType': 'apns', 'deviceToken': 'token-old'},
                    'state': 'Active',
                },
            })
        else:
            request.respond_with(200, {
                'id': 'device-001',
                'platform': 'ios',
                'formFactor': 'phone',
                'push': {
                    'recipient': {'transportType': 'apns', 'deviceToken': 'token-new'},
                    'state': 'Active',
                },
            })

    mock_http = success_mock(on_request)
    client = rest_client(mock_http)

    device = DeviceDetails(
        id='device-001',
        platform='ios',
        form_factor='phone',
        push={'recipient': {'transportType': 'apns', 'deviceToken': 'token-old'}},
    )

    result1 = await client.push.admin.device_registrations.save(device)

    updated_device = DeviceDetails(
        id='device-001',
        platform='ios',
        form_factor='phone',
        push={'recipient': {'transportType': 'apns', 'deviceToken': 'token-new'}},
    )

    result2 = await client.push.admin.device_registrations.save(updated_device)

    assert result1.push['recipient']['deviceToken'] == 'token-old'
    assert result2.push['recipient']['deviceToken'] == 'token-new'
    assert request_count == 2


# UTS: rest/unit/RSH1b3/save-error-propagated-2
async def test_rsh1b3_save_error_propagated():
    mock_http = success_mock(lambda request: request.respond_with(400, {
        'error': {
            'code': 40000,
            'statusCode': 400,
            'message': 'Invalid device details',
        },
    }))
    client = rest_client(mock_http)

    device = DeviceDetails(
        id='device-001',
        platform='ios',
        form_factor='phone',
        push={'recipient': {}},
    )

    with pytest.raises(AblyException) as excinfo:
        await client.push.admin.device_registrations.save(device)

    assert excinfo.value.code == 40000
    assert excinfo.value.status_code == 400


# UTS: rest/unit/RSH1b4/remove-delete-device-0
async def test_rsh1b4_remove_delete_device():
    captured_requests = []
    mock_http = success_mock(capture_and_respond(captured_requests, 204))
    client = rest_client(mock_http)

    await client.push.admin.device_registrations.remove('device-001')

    assert len(captured_requests) == 1

    request = captured_requests[0]
    assert request.method == 'DELETE'
    assert request.url.path == '/push/deviceRegistrations/' + 'device-001'


# UTS: rest/unit/RSH1b4/remove-nonexistent-succeeds-1
async def test_rsh1b4_remove_nonexistent_succeeds():
    mock_http = success_mock(lambda request: request.respond_with(204, None))
    client = rest_client(mock_http)

    await client.push.admin.device_registrations.remove('nonexistent-device')


# UTS: rest/unit/RSH1b5/remove-where-clientid-0
async def test_rsh1b5_remove_where_clientid():
    captured_requests = []
    mock_http = success_mock(capture_and_respond(captured_requests, 204))
    client = rest_client(mock_http)

    await client.push.admin.device_registrations.remove_where(clientId='client-abc')

    assert len(captured_requests) == 1

    request = captured_requests[0]
    assert request.method == 'DELETE'
    assert request.url.path == '/push/deviceRegistrations'
    assert request.url.query_params['clientId'] == 'client-abc'


# UTS: rest/unit/RSH1b5/remove-where-deviceid-1
async def test_rsh1b5_remove_where_deviceid():
    captured_requests = []
    mock_http = success_mock(capture_and_respond(captured_requests, 204))
    client = rest_client(mock_http)

    await client.push.admin.device_registrations.remove_where(deviceId='device-001')

    assert captured_requests[0].method == 'DELETE'
    assert captured_requests[0].url.path == '/push/deviceRegistrations'
    assert captured_requests[0].url.query_params['deviceId'] == 'device-001'


# UTS: rest/unit/RSH1b5/remove-where-no-match-succeeds-2
async def test_rsh1b5_remove_where_no_match_succeeds():
    mock_http = success_mock(lambda request: request.respond_with(204, None))
    client = rest_client(mock_http)

    await client.push.admin.device_registrations.remove_where(clientId='nonexistent-client')
