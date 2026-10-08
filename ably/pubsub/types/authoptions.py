from ably.pubsub.util.exceptions import AblyException


class AuthOptions:
    def __init__(self, auth_callback=None, auth_url=None, auth_method='GET',
                 auth_token=None, auth_headers=None, auth_params=None,
                 key_name=None, key_secret=None, key=None, query_time=False,
                 token_details=None, use_token_auth=None,
                 default_token_params=None):
        self.__auth_options = {}
        self.auth_options['auth_callback'] = auth_callback
        self.auth_options['auth_url'] = auth_url
        self.auth_options['auth_method'] = auth_method
        self.auth_options['auth_headers'] = auth_headers
        self.auth_options['auth_params'] = auth_params
        self.auth_options['query_time'] = query_time
        self.auth_options['key_name'] = key_name
        self.auth_options['key_secret'] = key_secret
        self.set_key(key)

        self.__auth_token = auth_token
        self.__token_details = token_details
        self.__use_token_auth = use_token_auth
        default_token_params = default_token_params or {}
        default_token_params.pop('timestamp', None)
        self.default_token_params = default_token_params

    def set_key(self, key):
        if key is None:
            return

        try:
            key_name, key_secret = key.split(':')
            self.auth_options['key_name'] = key_name
            self.auth_options['key_secret'] = key_secret
        except ValueError:
            raise AblyException("key of not len 2 parameters: {}"
                                .format(key.split(':')),
                                401, 40101) from None

    def replace(self, auth_options):
        if type(auth_options) is dict:
            auth_options = dict(auth_options)
            key = auth_options.pop('key', None)
            self.auth_options = auth_options
            self.set_key(key)
        elif type(auth_options) is AuthOptions:
            self.auth_options = dict(auth_options.auth_options)
        else:
            raise KeyError('Expected dict or AuthOptions')

    @property
    def auth_options(self):
        return self.__auth_options

    @auth_options.setter
    def auth_options(self, value):
        self.__auth_options = value

    @property
    def auth_callback(self):
        return self.auth_options['auth_callback']

    @auth_callback.setter
    def auth_callback(self, value):
        self.auth_options['auth_callback'] = value

    @property
    def auth_url(self):
        return self.auth_options['auth_url']

    @auth_url.setter
    def auth_url(self, value):
        self.auth_options['auth_url'] = value

    @property
    def auth_method(self):
        return self.auth_options['auth_method']

    @auth_method.setter
    def auth_method(self, value):
        self.auth_options['auth_method'] = value.upper()

    @property
    def key_name(self):
        return self.auth_options['key_name']

    @key_name.setter
    def key_name(self, value):
        self.auth_options['key_name'] = value

    @property
    def key_secret(self):
        return self.auth_options['key_secret']

    @key_secret.setter
    def key_secret(self, value):
        self.auth_options['key_secret'] = value

    @property
    def auth_token(self):
        return self.__auth_token

    @auth_token.setter
    def auth_token(self, value):
        self.__auth_token = value

    @property
    def auth_headers(self):
        return self.auth_options['auth_headers']

    @auth_headers.setter
    def auth_headers(self, value):
        self.auth_options['auth_headers'] = value

    @property
    def auth_params(self):
        return self.auth_options['auth_params']

    @auth_params.setter
    def auth_params(self, value):
        self.auth_options['auth_params'] = value

    @property
    def query_time(self):
        return self.auth_options['query_time']

    @query_time.setter
    def query_time(self, value):
        self.auth_options['query_time'] = value

    @property
    def token_details(self):
        return self.__token_details

    @token_details.setter
    def token_details(self, value):
        self.__token_details = value

    @property
    def use_token_auth(self):
        return self.__use_token_auth

    @use_token_auth.setter
    def use_token_auth(self, value):
        self.__use_token_auth = value

    @property
    def default_token_params(self):
        return self.__default_token_params

    @default_token_params.setter
    def default_token_params(self, value):
        self.__default_token_params = value

    def __str__(self):
        return str(self.__dict__)
