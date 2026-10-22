from typing import Optional
from urllib import parse

from ably.http.paginatedresult import PaginatedResult, format_params
from ably.types.apnsbroadcast import PushApnsBroadcast
from ably.types.channelsubscription import (
    PushChannelSubscription,
    channel_subscriptions_response_processor,
    channels_response_processor,
)
from ably.types.device import DeviceDetails, device_details_response_processor
from ably.util.exceptions import AblyException


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
        self.__live_activity = PushLiveActivity(ably)

    @property
    def ably(self):
        return self.__ably

    @property
    def device_registrations(self):
        return self.__device_registrations

    @property
    def channel_subscriptions(self):
        return self.__channel_subscriptions

    @property
    def live_activity(self):
        """Controls iOS Live Activities over an APNs broadcast channel created
        with `create_apns_broadcast`. Experimental."""
        return self.__live_activity

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

    async def create_apns_broadcast(self, message_storage_policy: int) -> PushApnsBroadcast:
        """Creates an APNs broadcast channel for use with an iOS Live Activity.
        Call once before starting the Live Activity and persist the returned
        ids for the session.

        Experimental: this is a preview feature and may change in a future
        non-major release.

        :Parameters:
        - `message_storage_policy`: 1 to cache the last update so that devices
          subscribing late receive the current content state, 0 to disable caching
        """
        body = {'messageStoragePolicy': message_storage_policy}
        response = await self.ably.http.post('/push/apnsBroadcastChannels', body=body)
        return PushApnsBroadcast.from_dict(response.to_native())


class PushLiveActivity:
    """Controls the lifecycle of an iOS Live Activity over an APNs broadcast
    channel created with `PushAdmin.create_apns_broadcast`.

    Experimental: this is a preview feature and may change in a future
    non-major release.
    """

    def __init__(self, ably):
        self.__ably = ably

    @property
    def ably(self):
        return self.__ably

    async def start(self, recipient: dict, apns_broadcast: str, apns: dict, headers: Optional[dict] = None):
        """Sends a push-to-start notification, starting a new Live Activity on
        each targeted device.

        :Parameters:
        - `recipient`: either `{'channels': [...]}`, targeting the devices
          subscribed to any of those channels, or `{'deviceId': ...}`,
          targeting a single device
        - `apns_broadcast`: the id returned by `create_apns_broadcast`
        - `apns`: the APNs Live Activity start payload, passed through as-is
        - `headers`: optional APNs delivery headers, such as `apns-priority`
          and `apns-expiration`
        """
        channels = recipient.get('channels')
        device_id = recipient.get('deviceId')
        if bool(channels) == bool(device_id):
            raise AblyException(
                'PushLiveActivity.start() requires exactly one of recipient channels or deviceId', 400, 40000)

        body = {'apns': apns}
        if channels:
            body['channels'] = channels
        else:
            body['deviceId'] = device_id
        await self._post(apns_broadcast, 'start', body, headers)

    async def update(self, apns_broadcast: str, apns: dict, headers: Optional[dict] = None):
        """Sends a content-state update to every device with an active Live
        Activity on the broadcast channel. APNs fans the single push out to
        the subscribed devices.

        :Parameters:
        - `apns_broadcast`: the id returned by `create_apns_broadcast`
        - `apns`: the APNs Live Activity update payload, passed through as-is
        - `headers`: optional APNs delivery headers, such as `apns-priority`
          and `apns-expiration`
        """
        await self._post(apns_broadcast, 'broadcast', {'apns': apns}, headers)

    async def end(self, apns_broadcast: str, apns: dict, headers: Optional[dict] = None):
        """Ends the Live Activity on every subscribed device and cleans up the
        APNs channel. The broadcast id is no longer valid afterwards.

        :Parameters:
        - `apns_broadcast`: the id returned by `create_apns_broadcast`
        - `apns`: the APNs Live Activity end payload, passed through as-is
        - `headers`: optional APNs delivery headers, such as `apns-priority`
          and `apns-expiration`
        """
        await self._post(apns_broadcast, 'end', {'apns': apns}, headers)

    async def _post(self, apns_broadcast: str, action: str, body: dict, headers: Optional[dict]):
        # The APNs delivery headers travel in the request body, not as HTTP headers
        if headers:
            body['headers'] = headers
        path = f'/push/apnsBroadcastChannels/{parse.quote(apns_broadcast, safe="")}/{action}'
        await self.ably.http.post(path, body=body)


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
