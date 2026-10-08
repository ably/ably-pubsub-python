from ably.pubsub.util import case


class PushChannelSubscription:

    def __init__(self, channel, device_id=None, client_id=None, app_id=None):
        if not device_id and not client_id:
            raise ValueError('missing expected device or client id')

        if device_id and client_id:
            raise ValueError('both device and client id given, only one expected')

        self.__channel = channel
        self.__device_id = device_id
        self.__client_id = client_id
        self.__app_id = app_id

    @property
    def channel(self):
        return self.__channel

    @property
    def device_id(self):
        return self.__device_id

    @property
    def client_id(self):
        return self.__client_id

    @property
    def app_id(self):
        return self.__app_id

    def as_dict(self):
        keys = ['channel', 'device_id', 'client_id', 'app_id']

        obj = {}
        for key in keys:
            value = getattr(self, key)
            if value is not None:
                key = case.snake_to_camel(key)
                obj[key] = value

        return obj

    @classmethod
    def from_dict(cls, obj):
        obj = {case.camel_to_snake(key): value for key, value in obj.items()}
        return cls(**obj)

    @classmethod
    def from_array(cls, array):
        return [cls.from_dict(d) for d in array]

    @classmethod
    def factory(cls, subscription):
        if isinstance(subscription, cls):
            return subscription

        return cls.from_dict(subscription)


def channel_subscriptions_response_processor(response):
    native = response.to_native()
    return PushChannelSubscription.from_array(native)


def channels_response_processor(response):
    native = response.to_native()
    return native
