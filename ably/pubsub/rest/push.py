from typing import Optional

from ably.pubsub.http.paginatedresult import PaginatedResult, format_params
from ably.pubsub.types.channelsubscription import (
    PushChannelSubscription,
    channel_subscriptions_response_processor,
    channels_response_processor,
)
from ably.pubsub.types.device import DeviceDetails, device_details_response_processor


class Push:

    def __init__(self, ably):
        self.__ably = ably
        self.__admin = PushAdmin(ably)

    @property
    def admin(self):
        return self.__admin


class PushAdmin:

    def __init__(self, ably):
        self.__ably = ably
        self.__device_registrations = PushDeviceRegistrations(ably)
        self.__channel_subscriptions = PushChannelSubscriptions(ably)

    @property
    def ably(self):
        return self.__ably

    @property
    def device_registrations(self):
        return self.__device_registrations

    @property
    def channel_subscriptions(self):
        return self.__channel_subscriptions

    async def publish(self, recipient: dict, data: dict, timeout: Optional[float] = None):
        """Publish a push notification to a single device.

        :Parameters:
        - `recipient`: the recipient of the notification
        - `data`: the data of the notification
        """
        if not isinstance(recipient, dict):
            raise TypeError(f'Unexpected {type(recipient)} recipient, expected a dict')

        if not isinstance(data, dict):
            raise TypeError(f'Unexpected {type(data)} data, expected a dict')

        if not recipient:
            raise ValueError('recipient is empty')

        if not data:
            raise ValueError('data is empty')

        body = data.copy()
        body.update({'recipient': recipient})
        await self.ably.http.post('/push/publish', body=body, timeout=timeout)


class PushDeviceRegistrations:

    def __init__(self, ably):
        self.__ably = ably

    @property
    def ably(self):
        return self.__ably

    async def get(self, device_id: str):
        """Returns a DeviceDetails object if the device id is found or results
        in a not found error if the device cannot be found.

        :Parameters:
        - `device_id`: the id of the device
        """
        path = f'/push/deviceRegistrations/{device_id}'
        response = await self.ably.http.get(path)
        obj = response.to_native()
        return DeviceDetails.from_dict(obj)

    async def list(self, **params):
        """Returns a PaginatedResult object with the list of DeviceDetails
        objects, filtered by the given parameters.

        :Parameters:
        - `**params`: the parameters used to filter the list
        """
        path = '/push/deviceRegistrations' + format_params(params)
        return await PaginatedResult.paginated_query(
            self.ably.http, url=path,
            response_processor=device_details_response_processor)

    async def save(self, device: dict):
        """Creates or updates the device. Returns a DeviceDetails object.

        :Parameters:
        - `device`: a dictionary with the device information
        """
        device_details = DeviceDetails.factory(device)
        path = f'/push/deviceRegistrations/{device_details.id}'
        body = device_details.as_dict()
        response = await self.ably.http.put(path, body=body)
        obj = response.to_native()
        return DeviceDetails.from_dict(obj)

    async def remove(self, device_id: str):
        """Deletes the registered device identified by the given device id.

        :Parameters:
        - `device_id`: the id of the device
        """
        path = f'/push/deviceRegistrations/{device_id}'
        return await self.ably.http.delete(path)

    async def remove_where(self, **params):
        """Deletes the registered devices identified by the given parameters.

        :Parameters:
        - `**params`: the parameters that identify the devices to remove
        """
        path = '/push/deviceRegistrations' + format_params(params)
        return await self.ably.http.delete(path)


class PushChannelSubscriptions:

    def __init__(self, ably):
        self.__ably = ably

    @property
    def ably(self):
        return self.__ably

    async def list(self, **params):
        """Returns a PaginatedResult object with the list of
        PushChannelSubscription objects, filtered by the given parameters.

        :Parameters:
        - `**params`: the parameters used to filter the list
        """
        path = '/push/channelSubscriptions' + format_params(params)
        return await PaginatedResult.paginated_query(self.ably.http, url=path,
                                                     response_processor=channel_subscriptions_response_processor)

    async def list_channels(self, **params):
        """Returns a PaginatedResult object with the list of
        PushChannelSubscription objects, filtered by the given parameters.

        :Parameters:
        - `**params`: the parameters used to filter the list
        """
        path = '/push/channels' + format_params(params)
        return await PaginatedResult.paginated_query(self.ably.http, url=path,
                                                     response_processor=channels_response_processor)

    async def save(self, subscription: dict):
        """Creates or updates the subscription. Returns a
        PushChannelSubscription object.

        :Parameters:
        - `subscription`: a dictionary with the subscription information
        """
        subscription = PushChannelSubscription.factory(subscription)
        path = '/push/channelSubscriptions'
        body = subscription.as_dict()
        response = await self.ably.http.post(path, body=body)
        obj = response.to_native()
        return PushChannelSubscription.from_dict(obj)

    async def remove(self, subscription: dict):
        """Deletes the given subscription.

        :Parameters:
        - `subscription`: the subscription object to remove
        """
        subscription = PushChannelSubscription.factory(subscription)
        params = subscription.as_dict()
        return await self.remove_where(**params)

    async def remove_where(self, **params):
        """Deletes the subscriptions identified by the given parameters.

        :Parameters:
        - `**params`: the parameters that identify the subscriptions to remove
        """
        path = '/push/channelSubscriptions' + format_params(**params)
        return await self.ably.http.delete(path)
