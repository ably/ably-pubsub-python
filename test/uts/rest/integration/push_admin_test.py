"""Derived from uts/rest/integration/push_admin.md in ably/specification.

Spec points: RSH1, RSH1a, RSH1b1, RSH1b2, RSH1b3, RSH1b4, RSH1b5, RSH1c1, RSH1c2,
RSH1c3, RSH1c4, RSH1c5
"""

import pytest

from ably import AblyException, DeviceDetails, PushChannelSubscription
from ably.http.paginatedresult import PaginatedResult
from test.uts.helpers.client import sandbox_rest_client, wall_clock_poll_until
from test.uts.helpers.sandbox import random_id

# The push-enabled namespace the canonical app setup provisions. A channel
# subscription may only be saved against a channel whose namespace carries
# `pushEnabled: true`.
PUSH_NAMESPACE = 'pushenabled'

# An APNs device token as the sandbox expects to receive one: 32 bytes, hex.
# `test/ably/rest/restpush_test.py` registers the same value.
DEVICE_TOKEN = '740f4707bebcf74f9b7c25d48e3358945f6aa01da5ddb387462c7eaf61bb78ad'


def apns_device(device_id, client_id=None, device_token=DEVICE_TOKEN, platform='ios',
                form_factor='phone'):
    """The specifications' `DeviceDetails(... push: DevicePushDetails(recipient: ...))`.

    There is no `DevicePushDetails` type in ably-python; `DeviceDetails.push` is
    the plain dict the wire carries, so the recipient goes in directly.
    """
    return DeviceDetails(
        id=device_id,
        client_id=client_id,
        platform=platform,
        form_factor=form_factor,
        push={'recipient': {'transportType': 'apns', 'deviceToken': device_token}},
    )


async def remove_device_quietly(client, device_id):
    try:
        await client.push.admin.device_registrations.remove(device_id)
    except AblyException:
        pass


async def remove_subscription_quietly(client, subscription):
    try:
        await client.push.admin.channel_subscriptions.remove(subscription)
    except AblyException:
        pass


# UTS: rest/integration/RSH1a/push-publish-clientid-0
async def test_rsh1a_push_publish_clientid(sandbox):
    client = sandbox_rest_client(sandbox.key(0).key_str)

    result = await client.push.admin.publish(
        {'clientId': 'test-client-push'},
        {'notification': {'title': 'Integration Test', 'body': 'Hello from push admin'}},
    )

    # The spec only requires the call not to throw. `publish` returns nothing.
    assert result is None


# UTS: rest/integration/RSH1a/push-publish-invalid-recipient-1
async def test_rsh1a_push_publish_invalid_recipient(sandbox):
    client = sandbox_rest_client(sandbox.key(0).key_str)

    # NOTE: the spec expects the server to reject the empty recipient and the
    # error to carry a `code`. `PushAdmin.publish` validates the recipient
    # itself (`ably/rest/push.py:57`) and raises `ValueError` before any request
    # is made, so there is no server error and no code to read. See the RSH1a row
    # under Adapted Tests -> REST behaviours asserted as they are, in
    # test/uts/deviations.md.
    with pytest.raises(ValueError):
        await client.push.admin.publish({}, {'notification': {'title': 'Test'}})


# UTS: rest/integration/RSH1b3/save-and-get-device-0
async def test_rsh1b3_save_and_get_device(sandbox):
    client = sandbox_rest_client(sandbox.key(0).key_str)
    registrations = client.push.admin.device_registrations
    device_id = f'test-device-{random_id()}'
    device_token = f'{random_id(16)}{random_id(16)}'

    saved = await registrations.save(apns_device(device_id, device_token=device_token))
    try:
        assert isinstance(saved, DeviceDetails)
        assert saved.id == device_id
        assert saved.platform == 'ios'
        assert saved.form_factor == 'phone'
        assert saved.push['recipient']['transportType'] == 'apns'

        retrieved = await registrations.get(device_id)
        assert isinstance(retrieved, DeviceDetails)
        assert retrieved.id == device_id
        assert retrieved.platform == 'ios'
    finally:
        await remove_device_quietly(client, device_id)


# UTS: rest/integration/RSH1b3/update-device-registration-1
async def test_rsh1b3_update_device_registration(sandbox):
    client = sandbox_rest_client(sandbox.key(0).key_str)
    registrations = client.push.admin.device_registrations
    device_id = f'test-device-update-{random_id()}'
    token_v1 = f'{random_id(16)}{random_id(16)}'
    token_v2 = f'{random_id(16)}{random_id(16)}'

    await registrations.save(apns_device(device_id, device_token=token_v1))
    try:
        updated = await registrations.save(apns_device(device_id, device_token=token_v2))

        assert updated.id == device_id
        assert updated.push['recipient']['deviceToken'] == token_v2

        retrieved = await registrations.get(device_id)
        assert retrieved.push['recipient']['deviceToken'] == token_v2
    finally:
        await remove_device_quietly(client, device_id)


# UTS: rest/integration/RSH1b1/get-unknown-device-error-0
async def test_rsh1b1_get_unknown_device_error(sandbox):
    client = sandbox_rest_client(sandbox.key(0).key_str)

    with pytest.raises(AblyException) as excinfo:
        await client.push.admin.device_registrations.get(f'nonexistent-device-{random_id()}')

    assert excinfo.value.status_code == 404


# UTS: rest/integration/RSH1b2/list-devices-filtered-0
async def test_rsh1b2_list_devices_filtered(sandbox):
    client = sandbox_rest_client(sandbox.key(0).key_str)
    registrations = client.push.admin.device_registrations
    device_id = f'test-device-list-{random_id()}'
    # A second registration the filter has to exclude. Without it a `deviceId`
    # filter that was dropped altogether would still leave one item behind.
    decoy_id = f'test-device-decoy-{random_id()}'

    await registrations.save(DeviceDetails(
        id=device_id,
        platform='android',
        form_factor='tablet',
        push={'recipient': {'transportType': 'gcm', 'registrationToken': f'token-{random_id()}'}},
    ))
    await registrations.save(apns_device(decoy_id))
    try:
        result = await registrations.list(deviceId=device_id)

        assert isinstance(result, PaginatedResult)
        assert len(result.items) == 1
        assert result.items[0].id == device_id
        assert result.items[0].platform == 'android'
    finally:
        await remove_device_quietly(client, device_id)
        await remove_device_quietly(client, decoy_id)


# UTS: rest/integration/RSH1b2/list-devices-pagination-1
async def test_rsh1b2_list_devices_pagination(sandbox):
    client = sandbox_rest_client(sandbox.key(0).key_str)
    registrations = client.push.admin.device_registrations
    client_id = f'test-client-list-{random_id()}'
    device_ids = []

    for i in (1, 2, 3):
        device_id = f'test-device-limit-{i}-{random_id()}'
        device_ids.append(device_id)
        await registrations.save(apns_device(device_id, client_id=client_id))
    try:
        # The filter has to hold before the limit means anything: three
        # registrations share this clientId and nothing else does.
        unlimited = await registrations.list(clientId=client_id)
        assert len(unlimited.items) == 3

        result = await registrations.list(clientId=client_id, limit=2)

        assert len(result.items) <= 2
        # NOTE: the spec writes `result.hasNext == true`. `has_next` is a method
        # here, and a bound method is truthy whatever the page holds.
        assert result.has_next() is True
    finally:
        for device_id in device_ids:
            await remove_device_quietly(client, device_id)


# UTS: rest/integration/RSH1b4/remove-device-0
async def test_rsh1b4_remove_device(sandbox):
    client = sandbox_rest_client(sandbox.key(0).key_str)
    registrations = client.push.admin.device_registrations
    device_id = f'test-device-remove-{random_id()}'

    await registrations.save(apns_device(device_id))

    response = await registrations.remove(device_id)
    # `remove` answers with the raw response rather than nothing.
    assert response.status_code == 204

    with pytest.raises(AblyException) as excinfo:
        await registrations.get(device_id)
    assert excinfo.value.status_code == 404


# UTS: rest/integration/RSH1b4/remove-nonexistent-device-1
async def test_rsh1b4_remove_nonexistent_device(sandbox):
    client = sandbox_rest_client(sandbox.key(0).key_str)

    response = await client.push.admin.device_registrations.remove(
        f'nonexistent-device-{random_id()}')

    assert response.status_code == 204


# UTS: rest/integration/RSH1b5/remove-where-clientid-0
async def test_rsh1b5_remove_where_clientid(sandbox):
    client = sandbox_rest_client(sandbox.key(0).key_str)
    registrations = client.push.admin.device_registrations
    client_id = f'test-client-removeWhere-{random_id()}'
    survivor_client_id = f'test-client-survivor-{random_id()}'
    survivor_id = f'test-device-survivor-{random_id()}'
    device_ids = []

    for i in (1, 2):
        device_id = f'test-device-rw-{i}-{random_id()}'
        device_ids.append(device_id)
        await registrations.save(apns_device(device_id, client_id=client_id))
    # A registration under a different clientId, which removeWhere must leave alone.
    await registrations.save(apns_device(survivor_id, client_id=survivor_client_id))
    try:
        response = await registrations.remove_where(clientId=client_id)
        assert response.status_code == 204

        # Deletion is asynchronous on the server side.
        async def removed():
            result = await registrations.list(clientId=client_id)
            return result if len(result.items) == 0 else None

        result = await wall_clock_poll_until(
            removed, timeout=20.0,
            description='the devices registered under the clientId to be removed')
        assert len(result.items) == 0

        assert (await registrations.get(survivor_id)).id == survivor_id
    finally:
        for device_id in device_ids + [survivor_id]:
            await remove_device_quietly(client, device_id)


# UTS: rest/integration/RSH1c3/save-and-list-subscriptions-0
async def test_rsh1c3_save_and_list_subscriptions(sandbox):
    client = sandbox_rest_client(sandbox.key(0).key_str)
    subscriptions = client.push.admin.channel_subscriptions
    device_id = f'test-device-sub-{random_id()}'
    channel_name = f'{PUSH_NAMESPACE}:test-sub-{random_id()}'
    decoy_channel = f'{PUSH_NAMESPACE}:test-sub-decoy-{random_id()}'

    await client.push.admin.device_registrations.save(apns_device(device_id))
    decoy = PushChannelSubscription(decoy_channel, device_id=device_id)
    await subscriptions.save(decoy)
    try:
        saved = await subscriptions.save(
            PushChannelSubscription(channel_name, device_id=device_id))

        assert isinstance(saved, PushChannelSubscription)
        assert saved.channel == channel_name
        assert saved.device_id == device_id

        result = await subscriptions.list(channel=channel_name)
        assert isinstance(result, PaginatedResult)
        assert len(result.items) >= 1
        # The same device is subscribed to a second channel, so a `channel`
        # filter that was dropped would show that subscription too.
        assert {sub.channel for sub in result.items} == {channel_name}

        found = False
        for sub in result.items:
            if sub.device_id == device_id:
                found = True
                assert sub.channel == channel_name
        assert found is True
    finally:
        await remove_subscription_quietly(
            client, PushChannelSubscription(channel_name, device_id=device_id))
        await remove_subscription_quietly(client, decoy)
        await remove_device_quietly(client, device_id)


# UTS: rest/integration/RSH1c3/save-subscription-clientid-1
async def test_rsh1c3_save_subscription_clientid(sandbox):
    client = sandbox_rest_client(sandbox.key(0).key_str)
    subscriptions = client.push.admin.channel_subscriptions
    client_id = f'test-client-sub-{random_id()}'
    channel_name = f'{PUSH_NAMESPACE}:test-clientsub-{random_id()}'

    subscription = PushChannelSubscription(channel_name, client_id=client_id)
    saved = await subscriptions.save(subscription)
    try:
        assert saved.channel == channel_name
        assert saved.client_id == client_id
    finally:
        await remove_subscription_quietly(client, subscription)


# UTS: rest/integration/RSH1c2/list-channels-with-subscriptions-0
async def test_rsh1c2_list_channels_with_subscriptions(sandbox):
    client = sandbox_rest_client(sandbox.key(0).key_str)
    subscriptions = client.push.admin.channel_subscriptions
    client_id = f'test-client-lc-{random_id()}'
    channel_name = f'{PUSH_NAMESPACE}:test-listchannels-{random_id()}'

    subscription = PushChannelSubscription(channel_name, client_id=client_id)
    await subscriptions.save(subscription)
    try:
        # The channel appears once the subscription has propagated.
        async def listed():
            result = await subscriptions.list_channels()
            return result if channel_name in result.items else None

        result = await wall_clock_poll_until(
            listed, timeout=20.0,
            description='the subscribed channel to appear in listChannels')

        assert isinstance(result, PaginatedResult)
        assert channel_name in result.items
    finally:
        await remove_subscription_quietly(client, subscription)


# UTS: rest/integration/RSH1c4/remove-channel-subscription-0
async def test_rsh1c4_remove_channel_subscription(sandbox):
    client = sandbox_rest_client(sandbox.key(0).key_str)
    subscriptions = client.push.admin.channel_subscriptions
    client_id = f'test-client-rm-{random_id()}'
    channel_name = f'{PUSH_NAMESPACE}:test-remove-{random_id()}'

    subscription = PushChannelSubscription(channel_name, client_id=client_id)
    await subscriptions.save(subscription)
    # The filter has to narrow for the assertion below to mean anything.
    assert len((await subscriptions.list(channel=channel_name, clientId=client_id)).items) == 1

    response = await subscriptions.remove(subscription)
    assert response.status_code == 204

    async def removed():
        result = await subscriptions.list(channel=channel_name, clientId=client_id)
        return result if len(result.items) == 0 else None

    result = await wall_clock_poll_until(
        removed, timeout=20.0, description='the removed subscription to disappear')
    assert len(result.items) == 0


# UTS: rest/integration/RSH1c4/remove-nonexistent-subscription-1
async def test_rsh1c4_remove_nonexistent_subscription(sandbox):
    client = sandbox_rest_client(sandbox.key(0).key_str)

    response = await client.push.admin.channel_subscriptions.remove(PushChannelSubscription(
        f'{PUSH_NAMESPACE}:nonexistent-{random_id()}', client_id='nonexistent-client'))

    assert response.status_code == 204


# UTS: rest/integration/RSH1c5/remove-where-subscriptions-0
async def test_rsh1c5_remove_where_subscriptions(sandbox):
    client = sandbox_rest_client(sandbox.key(0).key_str)
    subscriptions = client.push.admin.channel_subscriptions
    client_id = f'test-client-rwsub-{random_id()}'
    survivor_client_id = f'test-client-rwsub-keep-{random_id()}'
    survivor_channel = f'{PUSH_NAMESPACE}:test-rwsub-keep-{random_id()}'
    created = []

    for i in (1, 2):
        channel_name = f'{PUSH_NAMESPACE}:test-rwsub-{i}-{random_id()}'
        subscription = PushChannelSubscription(channel_name, client_id=client_id)
        created.append(subscription)
        await subscriptions.save(subscription)
    # A subscription under a different clientId, which removeWhere must leave alone.
    survivor = PushChannelSubscription(survivor_channel, client_id=survivor_client_id)
    await subscriptions.save(survivor)
    try:
        response = await subscriptions.remove_where(clientId=client_id)
        assert response.status_code == 204

        async def removed():
            result = await subscriptions.list(clientId=client_id)
            return result if len(result.items) == 0 else None

        result = await wall_clock_poll_until(
            removed, timeout=20.0,
            description='the subscriptions under the clientId to be removed')
        assert len(result.items) == 0

        survived = await subscriptions.list(clientId=survivor_client_id)
        assert len(survived.items) == 1
    finally:
        for subscription in created + [survivor]:
            await remove_subscription_quietly(client, subscription)
