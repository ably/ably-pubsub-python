import json
import time

from ably.types.capability import Capability


class TokenDetails:

    DEFAULTS = {'ttl': 60 * 60 * 1000}
    # Buffer in milliseconds before a token is considered unusable
    # For example, if buffer is 10000ms, the token can no longer be used for
    # new requests 9000ms before it expires
    TOKEN_EXPIRY_BUFFER = 15 * 1000

    def __init__(self, token=None, expires=None, issued=0,
                 capability=None, client_id=None):
        if expires is None:
            self.__expires = time.time() * 1000 + TokenDetails.DEFAULTS['ttl']
        else:
            self.__expires = expires
        self.__token = token
        self.__issued = issued
        self.__capability = Capability(capability or {})
        self.__client_id = client_id

    @property
    def token(self):
        return self.__token

    @property
    def expires(self):
        return self.__expires

    @property
    def issued(self):
        return self.__issued

    @property
    def capability(self):
        return self.__capability

    @property
    def client_id(self):
        return self.__client_id

    def to_dict(self):
        return {
            'expires': self.expires,
            'token': self.token,
            'issued': self.issued,
            'capability': self.capability.to_dict(),
            'clientId': self.client_id,
        }

    @staticmethod
    def from_dict(obj):
        kwargs = {
            'token': obj.get("token"),
            'capability': obj.get("capability"),
            'client_id': obj.get("clientId")
        }
        expires = obj.get("expires")
        kwargs['expires'] = expires if expires is None else int(expires)
        issued = obj.get("issued")
        kwargs['issued'] = issued if issued is None else int(issued)

        return TokenDetails(**kwargs)

    @staticmethod
    def from_json(data):
        if isinstance(data, str):
            data = json.loads(data)

        return TokenDetails.from_dict(data)

    def __eq__(self, other):
        if isinstance(other, TokenDetails):
            return (self.expires == other.expires
                    and self.token == other.token
                    and self.issued == other.issued
                    and self.capability == other.capability
                    and self.client_id == other.client_id)
        return NotImplemented
