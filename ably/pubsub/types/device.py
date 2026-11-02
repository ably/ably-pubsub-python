from ably.pubsub.util import case
from ably.pubsub.util.exceptions import AblyException

DevicePushTransportType = {'fcm', 'gcm', 'apns', 'web'}
DevicePlatform = {'android', 'ios', 'browser'}
DeviceFormFactor = {'phone', 'tablet', 'desktop', 'tv', 'watch', 'car', 'embedded', 'other'}


class DevicePushDetails:
    """The push registration of a device (PCP1).

    `recipient` is a dict naming the push transport and address, `state` is the state as
    the server sends it, such as 'Active', and `error_reason` is an AblyException.
    """

    def __init__(self, recipient=None, state=None, error_reason=None):
        if recipient:
            transport_type = recipient.get('transportType')
            if transport_type is not None and transport_type not in DevicePushTransportType:
                raise ValueError(f'unexpected transport type {transport_type}')

        self.__recipient = recipient
        self.__state = state
        self.__error_reason = error_reason

    @property
    def recipient(self):
        return self.__recipient

    @property
    def state(self):
        return self.__state

    @property
    def error_reason(self):
        return self.__error_reason

    def as_dict(self):
        obj = {}
        if self.recipient is not None:
            obj['recipient'] = self.recipient
        if self.state is not None:
            obj['state'] = self.state
        if self.error_reason is not None:
            obj['errorReason'] = {
                'message': self.error_reason.message,
                'statusCode': self.error_reason.status_code,
                'code': self.error_reason.code,
            }

        return obj

    @classmethod
    def from_dict(cls, obj):
        error_reason = obj.get('errorReason')
        if isinstance(error_reason, dict):
            error_reason = AblyException.from_dict(error_reason)

        # Fields this version does not model are ignored, so the server can add them
        return cls(recipient=obj.get('recipient'), state=obj.get('state'), error_reason=error_reason)

    @classmethod
    def factory(cls, push):
        if isinstance(push, cls):
            return push

        return cls.from_dict(push)


class DeviceDetails:

    _fields = ['id', 'client_id', 'form_factor', 'metadata', 'platform',
               'push', 'update_token', 'app_id', 'device_identity_token', 'modified', 'device_secret']

    def __init__(self, id, client_id=None, form_factor=None, metadata=None,
                 platform=None, push=None, update_token=None, app_id=None,
                 device_identity_token=None, modified=None, device_secret=None):

        if push is not None:
            push = DevicePushDetails.factory(push)

        if platform is not None and platform not in DevicePlatform:
            raise ValueError(f'unexpected platform {platform}')

        if form_factor is not None and form_factor not in DeviceFormFactor:
            raise ValueError(f'unexpected form factor {form_factor}')

        self.__id = id
        self.__client_id = client_id
        self.__form_factor = form_factor
        self.__metadata = metadata
        self.__platform = platform
        self.__push = push
        self.__update_token = update_token
        self.__app_id = app_id
        self.__device_identity_token = device_identity_token
        self.__modified = modified
        self.__device_secret = device_secret

    @property
    def id(self):
        return self.__id

    @property
    def client_id(self):
        return self.__client_id

    @property
    def form_factor(self):
        return self.__form_factor

    @property
    def metadata(self):
        return self.__metadata

    @property
    def platform(self):
        return self.__platform

    @property
    def push(self):
        return self.__push

    @property
    def update_token(self):
        return self.__update_token

    @property
    def app_id(self):
        return self.__app_id

    @property
    def device_identity_token(self):
        return self.__device_identity_token

    @property
    def modified(self):
        return self.__modified

    @property
    def device_secret(self):
        return self.__device_secret

    def as_dict(self):
        obj = {}
        for key in self._fields:
            value = getattr(self, key)
            if value is not None:
                if key == 'push':
                    value = value.as_dict()
                key = case.snake_to_camel(key)
                obj[key] = value

        return obj

    @classmethod
    def from_dict(cls, obj):
        obj = {case.camel_to_snake(key): value for key, value in obj.items()}
        # Fields this version does not model are ignored, so the server can add them
        return cls(**{key: value for key, value in obj.items() if key in cls._fields})

    @classmethod
    def from_array(cls, array):
        return [cls.from_dict(d) for d in array]

    @classmethod
    def factory(cls, device):
        if isinstance(device, cls):
            return device

        return cls.from_dict(device)


def device_details_response_processor(response):
    native = response.to_native()
    return DeviceDetails.from_array(native)
