import itertools
import random
import string
import time

import pytest

from ably.pubsub.request.paginatedresult import PaginatedResult
from ably.pubsub.server import AblyAuthException, AblyException, DeviceDetails, PushChannelSubscription
from test.ably.testapp import TestApp
from test.ably.utils import (
    BaseAsyncTestCase,
    VaryByProtocolTestsMetaclass,
    get_random_key,
    new_dict,
    random_string,
)

DEVICE_TOKEN = '740f4707bebcf74f9b7c25d48e3358945f6aa01da5ddb387462c7eaf61bb78ad'


class TestPush(BaseAsyncTestCase, metaclass=VaryByProtocolTestsMetaclass):

    @pytest.fixture(autouse=True)
    async def setup(self):
        self.ably = await TestApp.get_ably_rest()

        # Register several devices for later use
        self.devices = {}
        for _ in range(10):
            await self.save_device()

        # Register several subscriptions for later use
        self.channels = {'canpublish:test1': [], 'canpublish:test2': [], 'canpublish:test3': []}
        for key, channel in zip(self.devices, itertools.cycle(self.channels)):
            device = self.devices[key]
            await self.save_subscription(channel, device_id=device.id)
        assert len(list(itertools.chain(*self.channels.values()))) == len(self.devices)
        yield
        for key, channel in zip(self.devices, itertools.cycle(self.channels)):
            device = self.devices[key]
            await self.remove_subscription(channel, device_id=device.id)
            await self.ably.push.admin.device_registrations.remove(device_id=device.id)
        await self.ably.close()

    def per_protocol_setup(self, use_binary_protocol):
        self.ably.options.use_binary_protocol = use_binary_protocol

    def get_client_id(self):
        return random_string(12)

    def get_device_id(self):
        return random_string(26, string.ascii_uppercase + string.digits)

    def gen_device_data(self, data=None, **kw):
        if data is None:
            data = {
                'id': self.get_device_id(),
                'clientId': self.get_client_id(),
                'platform': random.choice(['android', 'ios']),
                'formFactor': 'phone',
                'deviceSecret': 'test-secret',
                'push': {
                    'recipient': {
                        'transportType': 'apns',
                        'deviceToken': DEVICE_TOKEN,
                    }
                },
            }
        else:
            data = data.copy()

        data.update(kw)
        return data

    async def save_device(self, data=None, **kw):
        """
        Helper method to register a device, to not have this code repeated
        everywhere. Returns the input dict that was sent to Ably, and the
        device details returned by Ably.
        """
        data = self.gen_device_data(data, **kw)
        device = await self.ably.push.admin.device_registrations.save(data)
        self.devices[device.id] = device
        return device

    async def remove_device(self, device_id):
        result = await self.ably.push.admin.device_registrations.remove(device_id)
        self.devices.pop(device_id, None)
        return result

    async def remove_device_where(self, **kw):
        remove_where = self.ably.push.admin.device_registrations.remove_where
        result = await remove_where(**kw)

        aux = {'deviceId': 'id', 'clientId': 'client_id'}
        for device in list(self.devices.values()):
            for key, value in kw.items():
                key = aux[key]
                if getattr(device, key) == value:
                    del self.devices[device.id]

        return result

    def get_device(self):
        key = get_random_key(self.devices)
        return self.devices[key]

    def get_channel(self):
        key = get_random_key(self.channels)
        return key, self.channels[key]

    async def save_subscription(self, channel, **kw):
        """
        Helper method to register a device, to not have this code repeated
        everywhere. Returns the input dict that was sent to Ably, and the
        device details returned by Ably.
        """
        subscription = PushChannelSubscription(channel, **kw)
        subscription = await self.ably.push.admin.channel_subscriptions.save(subscription)
        self.channels.setdefault(channel, []).append(subscription)
        return subscription

    async def remove_subscription(self, channel, **kw):
        subscription = PushChannelSubscription(channel, **kw)
        subscription = await self.ably.push.admin.channel_subscriptions.remove(subscription)
        return subscription

    # RSH1a
    async def test_admin_publish(self):
        recipient = {'clientId': 'ablyChannel'}
        data = {
            'data': {'foo': 'bar'},
        }

        publish = self.ably.push.admin.publish
        with pytest.raises(TypeError):
            await publish('ablyChannel', data)
        with pytest.raises(TypeError):
            await publish(recipient, 25)
        with pytest.raises(ValueError):
            await publish({}, data)
        with pytest.raises(ValueError):
            await publish(recipient, {})

        with pytest.raises(AblyException):
            await publish(recipient, {'xxx': 5})

        assert await publish(recipient, data) is None

    # RSH1b1
    async def test_admin_device_registrations_get(self):
        get = self.ably.push.admin.device_registrations.get

        # Not found
        with pytest.raises(AblyException):
            await get('not-found')

        # Found
        device = self.get_device()
        device_details = await get(device.id)
        assert device_details.id == device.id
        assert device_details.platform == device.platform
        assert device_details.form_factor == device.form_factor

    # RSH1b2
    async def test_admin_device_registrations_list(self):
        list_devices = self.ably.push.admin.device_registrations.list

        list_response = await list_devices()
        assert type(list_response) is PaginatedResult
        assert type(list_response.items) is list
        assert type(list_response.items[0]) is DeviceDetails

        # limit
        list_response = await list_devices(limit=5000)
        assert len(list_response.items) == len(self.devices)
        list_response = await list_devices(limit=2)
        assert len(list_response.items) == 2

        # Filter by device id
        device = self.get_device()
        list_response = await list_devices(deviceId=device.id)
        assert len(list_response.items) == 1
        list_response = await list_devices(deviceId=self.get_device_id())
        assert len(list_response.items) == 0

        # Filter by client id
        list_response = await list_devices(clientId=device.client_id)
        assert len(list_response.items) == 1
        list_response = await list_devices(clientId=self.get_client_id())
        assert len(list_response.items) == 0

    # RSH1b3
    async def test_admin_device_registrations_save(self):
        # Create
        data = self.gen_device_data()
        device = await self.save_device(data)
        assert type(device) is DeviceDetails

        # Update
        await self.save_device(data, formFactor='tablet')

        # Invalid values
        with pytest.raises(ValueError):
            push = {'recipient': new_dict(data['push']['recipient'], transportType='xyz')}
            await self.save_device(data, push=push)
        with pytest.raises(ValueError):
            await self.save_device(data, platform='native')
        with pytest.raises(ValueError):
            await self.save_device(data, formFactor='fridge')

        # Fail
        with pytest.raises(AblyException):
            await self.save_device(data, push={'color': 'red'})

    # RSH1b4
    async def test_admin_device_registrations_remove(self):
        get = self.ably.push.admin.device_registrations.get

        device = self.get_device()

        # Remove
        get_response = await get(device.id)
        assert get_response.id == device.id  # Exists
        remove_device_response = await self.remove_device(device.id)
        assert remove_device_response.status_code == 204
        with pytest.raises(AblyException):  # Doesn't exist
            await get(device.id)

        # Remove again, it doesn't fail
        remove_device_response = await self.remove_device(device.id)
        assert remove_device_response.status_code == 204

    # RSH1b5
    async def test_admin_device_registrations_remove_where(self):
        get = self.ably.push.admin.device_registrations.get

        # Remove by device id
        device = self.get_device()
        foo_device = await get(device.id)
        assert foo_device.id == device.id  # Exists
        remove_foo_device_response = await self.remove_device_where(deviceId=device.id)
        assert remove_foo_device_response.status_code == 204
        with pytest.raises(AblyException):  # Doesn't exist
            await get(device.id)

        # Remove by client id
        device = self.get_device()
        boo_device = await get(device.id)
        assert boo_device.id == device.id  # Exists
        remove_boo_device_response = await self.remove_device_where(clientId=device.client_id)
        assert remove_boo_device_response.status_code == 204
        # Doesn't exist (Deletion is async: wait up to a few seconds before giving up)
        with pytest.raises(AblyException):
            for _ in range(5):
                time.sleep(1)
                await get(device.id)

        # Remove with no matching params
        remove_boo_device_response = await self.remove_device_where(clientId=device.client_id)
        assert remove_boo_device_response.status_code == 204

    # # RSH1c1
    async def test_admin_channel_subscriptions_list(self):
        list_ = self.ably.push.admin.channel_subscriptions.list

        channel, subscriptions = self.get_channel()

        list_response = await list_(channel=channel)

        assert type(list_response) is PaginatedResult
        assert type(list_response.items) is list
        assert type(list_response.items[0]) is PushChannelSubscription

        # limit
        list_response = await list_(channel=channel, limit=2)
        assert len(list_response.items) == 2

        list_response = await list_(channel=channel, limit=5000)
        assert len(list_response.items) == len(subscriptions)

        # Filter by device id
        device_id = subscriptions[0].device_id
        list_response = await list_(channel=channel, deviceId=device_id)
        assert len(list_response.items) == 1
        assert list_response.items[0].device_id == device_id
        assert list_response.items[0].channel == channel
        list_response = await list_(channel=channel, deviceId=self.get_device_id())
        assert len(list_response.items) == 0

        # Filter by client id
        device = self.get_device()
        list_response = await list_(channel=channel, clientId=device.client_id)
        assert len(list_response.items) == 0

    # RSH1c2
    async def test_admin_channels_list(self):
        list_ = self.ably.push.admin.channel_subscriptions.list_channels

        list_response = await list_()
        assert type(list_response) is PaginatedResult
        assert type(list_response.items) is list
        assert type(list_response.items[0]) is str

        # limit
        list_response = await list_(limit=5000)
        assert len(list_response.items) == len(self.channels)
        list_response = await list_(limit=1)
        assert len(list_response.items) == 1

    # RSH1c3
    async def test_admin_channel_subscriptions_save(self):
        save = self.ably.push.admin.channel_subscriptions.save

        # Subscribe
        device = self.get_device()
        channel = 'canpublish:testsave'
        subscription = await self.save_subscription(channel, device_id=device.id)
        assert type(subscription) is PushChannelSubscription
        assert subscription.channel == channel
        assert subscription.device_id == device.id
        assert subscription.client_id is None

        # Failures
        client_id = self.get_client_id()
        with pytest.raises(ValueError):
            PushChannelSubscription(channel, device_id=device.id, client_id=client_id)

        subscription = PushChannelSubscription('notallowed', device_id=device.id)
        with pytest.raises(AblyAuthException):
            await save(subscription)

        subscription = PushChannelSubscription(channel, device_id='notregistered')
        with pytest.raises(AblyException):
            await save(subscription)

    # RSH1c4
    async def test_admin_channel_subscriptions_remove(self):
        save = self.ably.push.admin.channel_subscriptions.save
        remove = self.ably.push.admin.channel_subscriptions.remove
        list_ = self.ably.push.admin.channel_subscriptions.list

        channel = 'canpublish:testremove'

        # Subscribe device
        device = self.get_device()
        subscription = await save(PushChannelSubscription(channel, device_id=device.id))
        list_response = await list_(channel=channel)
        assert device.id in (x.device_id for x in list_response.items)
        remove_response = await remove(subscription)
        assert remove_response.status_code == 204
        list_response = await list_(channel=channel)
        assert device.id not in (x.device_id for x in list_response.items)

        # Subscribe client
        client_id = self.get_client_id()
        subscription = await save(PushChannelSubscription(channel, client_id=client_id))
        list_response = await list_(channel=channel)
        assert client_id in (x.client_id for x in list_response.items)
        remove_response = await remove(subscription)
        assert remove_response.status_code == 204
        list_response = await list_(channel=channel)
        assert client_id not in (x.client_id for x in list_response.items)

        # Remove again, it doesn't fail
        remove_response = await remove(subscription)
        assert remove_response.status_code == 204

    # RSH1c5
    async def test_admin_channel_subscriptions_remove_where(self):
        save = self.ably.push.admin.channel_subscriptions.save
        remove = self.ably.push.admin.channel_subscriptions.remove_where
        list_ = self.ably.push.admin.channel_subscriptions.list

        channel = 'canpublish:testremovewhere'

        # Subscribe device
        device = self.get_device()
        await save(PushChannelSubscription(channel, device_id=device.id))
        list_response = await list_(channel=channel)
        assert device.id in (x.device_id for x in list_response.items)
        remove_response = await remove(channel=channel, device_id=device.id)
        assert remove_response.status_code == 204
        list_response = await list_(channel=channel)
        assert device.id not in (x.device_id for x in list_response.items)

        # Subscribe client
        client_id = self.get_client_id()
        await save(PushChannelSubscription(channel, client_id=client_id))
        list_response = await list_(channel=channel)
        assert client_id in (x.client_id for x in list_response.items)
        remove_response = await remove(channel=channel, client_id=client_id)
        assert remove_response.status_code == 204
        list_response = await list_(channel=channel)
        assert client_id not in (x.client_id for x in list_response.items)

        # Remove again, it doesn't fail
        remove_response = await remove(channel=channel, client_id=client_id)
        assert remove_response.status_code == 204
