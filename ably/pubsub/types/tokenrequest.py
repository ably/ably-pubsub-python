import base64
import hashlib
import hmac
import json


class TokenRequest:

    def __init__(self, key_name=None, client_id=None, nonce=None, mac=None,
                 capability=None, ttl=None, timestamp=None):
        self.__key_name = key_name
        self.__client_id = client_id
        self.__nonce = nonce
        self.__mac = mac
        self.__capability = capability
        self.__ttl = ttl
        self.__timestamp = timestamp

    def sign_request(self, key_secret):
        sign_text = "\n".join([str(x) for x in [
            self.key_name or "",
            self.ttl or "",
            self.capability or "",
            self.client_id or "",
            f"{self.timestamp or 0}",
            self.nonce or "",
            "",  # to get the trailing new line
        ]])
        try:
            key_secret = key_secret.encode('utf8')
        except AttributeError:
            pass
        try:
            sign_text = sign_text.encode('utf8')
        except AttributeError:
            pass
        mac = hmac.new(key_secret, sign_text, hashlib.sha256).digest()
        self.mac = base64.b64encode(mac).decode('utf8')

    def to_dict(self):
        return {
            'keyName': self.key_name,
            'clientId': self.client_id,
            'ttl': self.ttl,
            'nonce': self.nonce,
            'capability': self.capability,
            'timestamp': self.timestamp,
            'mac': self.mac
        }

    @staticmethod
    def from_json(data):
        if isinstance(data, str):
            data = json.loads(data)

        mapping = {
            'keyName': 'key_name',
            'clientId': 'client_id',
        }
        for name, py_name in mapping.items():
            if name in data:
                data[py_name] = data.pop(name)

        return TokenRequest(**data)

    def __eq__(self, other):
        if isinstance(other, TokenRequest):
            return (self.key_name == other.key_name
                    and self.client_id == other.client_id
                    and self.nonce == other.nonce
                    and self.mac == other.mac
                    and self.capability == other.capability
                    and self.ttl == other.ttl
                    and self.timestamp == other.timestamp)
        return NotImplemented

    @property
    def key_name(self):
        return self.__key_name

    @property
    def client_id(self):
        return self.__client_id

    @property
    def nonce(self):
        return self.__nonce

    @property
    def mac(self):
        return self.__mac

    @mac.setter
    def mac(self, mac):
        self.__mac = mac

    @property
    def capability(self):
        return self.__capability

    @property
    def ttl(self):
        return self.__ttl

    @property
    def timestamp(self):
        return self.__timestamp
