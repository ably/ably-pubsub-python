"""Derived from uts/rest/integration/push_channels.md in ably/specification.

Spec points: RSH7a, RSH7b, RSH7c, RSH7d

DEVIATION: ably-python implements neither the PushChannel interface (RSH7, the `push`
field on a channel) nor LocalDevice (RSH8). `ably/rest/channel.py` gives a channel no
`push`, `AblyRest` no `device`, and `ably/types/device.py` defines only `DeviceDetails`.
Both tests here therefore depart from the specification and are gated behind
RUN_DEVIATIONS, against the same spelling
[test/uts/rest/unit/push/push_channels_test.py](../unit/push/push_channels_test.py)
gates on — `ably.types.device.LocalDevice`, `client.device` and
`channel.push.subscribe_device()` and friends — so that dropping the marker is the only
change either tier needs when RSH7 lands.

The halves that do not depend on the missing API are real, and were confirmed by hand
against the sandbox: a device registered under the id and APNs token shape the
specification builds, an admin-created channel subscription in the `pushenabled`
namespace, and `channel_subscriptions.list(...)` finding it and then not finding it
once removed. Those filter keys must be camelCase — `list(**params)` hands the dict to
`format_params` positionally, which converts only its own `**kw`
(`ably/rest/push.py:147`, `ably/http/paginatedresult.py:18`), so `device_id=` reaches
the server as an unknown `device_id` query parameter that it ignores, leaving the
channel filter to match on its own.

That confirmation also turned up a fault in the specification, recorded against the
RSH7a setup below: the `deviceIdentityToken` it hard-codes is rejected, and the real
one from the registration response is used instead.

See [deviations.md](../../deviations.md): the gating under *Failing Tests* ->
*Unimplemented features*, and the hard-coded device identity token under *UTS Spec
Errors*.
"""

from ably import AblyException, DeviceDetails
from test.uts.helpers.client import sandbox_rest_client
from test.uts.helpers.deviations import deviation
from test.uts.helpers.sandbox import random_id

# A channel subscription may only be saved against a channel whose namespace carries
# `pushEnabled: true`, which in the canonical app setup is this one.
PUSH_NAMESPACE = 'pushenabled'

# The specifications' `deviceIdentityToken: "test-device-identity-token"`, which stands
# in wherever no registration issued a real one. `subscribeClient` and
# `unsubscribeClient` do not authenticate as the device — RSH7b2 and RSH7d2 send the
# clientId, and the unit tier pins that neither sends `X-Ably-DeviceToken` — so a
# placeholder is all the RSH7b test needs.
PLACEHOLDER_DEVICE_IDENTITY_TOKEN = 'test-device-identity-token'


def set_local_device(client, device_id, device_identity_token=PLACEHOLDER_DEVICE_IDENTITY_TOKEN,
                     client_id=None):
    """The specifications' `client.device = LocalDevice(...)`.

    The import is deliberately inside the call, so that a file-level import of a name
    that does not exist does not take the collection of the whole package down with it.
    """
    from ably.types.device import LocalDevice

    client.device = LocalDevice(
        id=device_id,
        device_identity_token=device_identity_token,
        client_id=client_id,
    )


def issued_device_identity_token(registration):
    """The device identity token `deviceRegistrations.save` came back with.

    `DeviceDetails.device_identity_token` holds the whole object the server sends —
    `{token, keyName, issued, expires, capability}` — where a `LocalDevice` carries the
    token itself, which is what push device authentication puts in `X-Ably-DeviceToken`.
    """
    issued = registration.device_identity_token
    assert issued, 'the registration response carried no deviceIdentityToken'
    return issued['token'] if isinstance(issued, dict) else issued


async def remove_device_quietly(client, device_id):
    try:
        await client.push.admin.device_registrations.remove(device_id)
    except AblyException:
        pass


@deviation
# UTS: rest/integration/RSH7a/subscribe-unsubscribe-device-0
async def test_rsh7a_subscribe_unsubscribe_device(sandbox):
    client = sandbox_rest_client(sandbox.key(0).key_str)

    device_id = 'test-device-pushchan-' + random_id()
    channel_name = f'{PUSH_NAMESPACE}:test-rsh7a-' + random_id()
    device_token = 'test-apns-token-' + random_id()

    # A device has to be registered before a device channel subscription will take.
    # There is no `DevicePushDetails` type in ably-python; `DeviceDetails.push` is the
    # plain dict the wire carries, so the recipient goes in directly.
    registration = await client.push.admin.device_registrations.save(DeviceDetails(
        id=device_id,
        platform='ios',
        form_factor='phone',
        push={'recipient': {'transportType': 'apns', 'deviceToken': device_token}},
    ))
    try:
        # SPEC FAULT: the specification's own comment says the deviceIdentityToken is
        # obtained from the registration response, and then its pseudocode hard-codes
        # "test-device-identity-token". The sandbox will not have it: RSH7a2 and RSH7c2
        # authenticate as the device, and a token the server did not issue comes back
        # 40005 / 400, `Invalid accessToken in request`. The comment is right and the
        # code beside it is not, so the issued token is what goes in.
        set_local_device(client, device_id,
                         device_identity_token=issued_device_identity_token(registration))

        channel = client.channels.get(channel_name)

        await channel.push.subscribe_device()

        result = await client.push.admin.channel_subscriptions.list(
            channel=channel_name, deviceId=device_id)
        assert len(result.items) >= 1
        assert any(
            subscription.device_id == device_id and subscription.channel == channel_name
            for subscription in result.items)

        await channel.push.unsubscribe_device()

        result_after = await client.push.admin.channel_subscriptions.list(
            channel=channel_name, deviceId=device_id)
        assert len(result_after.items) == 0
    finally:
        # Removing the registration removes the device's channel subscriptions with it.
        await remove_device_quietly(client, device_id)


@deviation
# UTS: rest/integration/RSH7b/subscribe-unsubscribe-client-0
async def test_rsh7b_subscribe_unsubscribe_client(sandbox):
    client = sandbox_rest_client(sandbox.key(0).key_str)

    client_id = 'test-client-pushchan-' + random_id()
    channel_name = f'{PUSH_NAMESPACE}:test-rsh7b-' + random_id()

    # `subscribeClient` subscribes by clientId rather than by deviceId, so no device
    # registration is needed here.
    set_local_device(client, 'test-device-' + random_id(), client_id=client_id)

    channel = client.channels.get(channel_name)

    await channel.push.subscribe_client()

    result = await client.push.admin.channel_subscriptions.list(
        channel=channel_name, clientId=client_id)
    assert len(result.items) >= 1
    assert any(
        subscription.client_id == client_id and subscription.channel == channel_name
        for subscription in result.items)

    await channel.push.unsubscribe_client()

    result_after = await client.push.admin.channel_subscriptions.list(
        channel=channel_name, clientId=client_id)
    assert len(result_after.items) == 0
