"""Unit tests for the push admin types.

Tests cover:
- PCD7, PCP1-PCP4: DeviceDetails.push as a DevicePushDetails
- fields the server adds that the types do not model are ignored when decoding
"""

import pytest

from ably.pubsub.types.channelsubscription import PushChannelSubscription
from ably.pubsub.types.device import DeviceDetails, DevicePushDetails
from ably.pubsub.util.exceptions import AblyException

DEVICE = {
    'id': 'device-001',
    'clientId': 'client-abc',
    'platform': 'ios',
    'formFactor': 'phone',
    'push': {
        'recipient': {'transportType': 'apns', 'deviceToken': 'token-123'},
        'state': 'Failing',
        'errorReason': {'message': 'Bad token', 'statusCode': 400, 'code': 40000},
    },
}


def test_device_push_is_device_push_details():
    device = DeviceDetails.from_dict(DEVICE)
    assert isinstance(device.push, DevicePushDetails)
    assert device.push.recipient == {'transportType': 'apns', 'deviceToken': 'token-123'}
    assert device.push.state == 'Failing'
    assert isinstance(device.push.error_reason, AblyException)
    assert device.push.error_reason.code == 40000
    assert device.push.error_reason.status_code == 400
    assert device.push.error_reason.message == 'Bad token'


def test_device_as_dict_round_trips():
    assert DeviceDetails.from_dict(DEVICE).as_dict() == DEVICE


def test_device_accepts_push_as_dict_or_details():
    recipient = {'transportType': 'apns', 'deviceToken': 'token-123'}
    from_dict = DeviceDetails('device-001', push={'recipient': recipient})
    from_details = DeviceDetails('device-001', push=DevicePushDetails(recipient=recipient))
    assert from_dict.push.recipient == recipient
    assert from_details.push.recipient == recipient
    assert from_dict.as_dict() == from_details.as_dict() == {'id': 'device-001', 'push': {'recipient': recipient}}


def test_push_rejects_unknown_transport_type():
    with pytest.raises(ValueError):
        DevicePushDetails(recipient={'transportType': 'xyz'})
    with pytest.raises(ValueError):
        DeviceDetails('device-001', push={'recipient': {'transportType': 'xyz'}})


def test_device_ignores_unknown_fields():
    device = DeviceDetails.from_dict({
        **DEVICE,
        'someNewField': 'value',
        'push': {**DEVICE['push'], 'someNewPushField': 'value'},
    })
    assert device.id == 'device-001'
    assert device.as_dict() == DEVICE


def test_channel_subscription_ignores_unknown_fields():
    subscription = PushChannelSubscription.from_dict({
        'channel': 'pushenabled:test',
        'clientId': 'client-abc',
        'someNewField': 'value',
    })
    assert subscription.channel == 'pushenabled:test'
    assert subscription.client_id == 'client-abc'
    assert subscription.as_dict() == {'channel': 'pushenabled:test', 'clientId': 'client-abc'}
