from __future__ import annotations

import base64
import logging
import time
import uuid
from datetime import timedelta
from typing import TYPE_CHECKING

import httpx

from ably.pubsub.types.options import Options

if TYPE_CHECKING:
    from ably.pubsub.http.http import AblyHttp
    from ably.pubsub.realtime.realtime import AblyRealtime

from ably.pubsub.types.capability import Capability
from ably.pubsub.types.tokendetails import TokenDetails
from ably.pubsub.types.tokenrequest import TokenRequest
from ably.pubsub.util.exceptions import AblyAuthException, AblyException, IncompatibleClientIdException
from ably.pubsub.util.helper import extract_url_params

__all__ = ["Auth"]

log = logging.getLogger(__name__)


class Auth:
    class Method:
        BASIC = "BASIC"
        TOKEN = "TOKEN"

    def __init__(self, ably: AblyHttp | AblyRealtime, options: Options):
        self.__ably = ably
        self.__auth_options = options

        if not self.ably._is_realtime:
            self.__client_id = options.client_id
            if not self.__client_id and options.token_details:
                self.__client_id = options.token_details.client_id
        else:
            self.__client_id = None
        self.__client_id_validated: bool = False

        self.__basic_credentials: str | None = None
        self.__auth_params: dict | None = None
        self.__token_details: TokenDetails | None = None
        self.__time_offset: int | None = None

        must_use_token_auth = options.use_token_auth is True
        must_not_use_token_auth = options.use_token_auth is False
        can_use_basic_auth = options.key_secret is not None
        if not must_use_token_auth and can_use_basic_auth:
            # We have the key, no need to authenticate the client
            # default to using basic auth
            log.debug("anonymous, using basic auth")
            self.__auth_mechanism = Auth.Method.BASIC
            basic_key = f"{options.key_name}:{options.key_secret}"
            basic_key = base64.b64encode(basic_key.encode('utf-8'))
            self.__basic_credentials = basic_key.decode('ascii')
            return
        elif must_not_use_token_auth and not can_use_basic_auth:
            raise ValueError('If use_token_auth is False you must provide a key')

        # Using token auth
        self.__auth_mechanism = Auth.Method.TOKEN

        if options.token_details:
            self.__token_details = options.token_details
        elif options.auth_token:
            self.__token_details = TokenDetails(token=options.auth_token)
        else:
            self.__token_details = None

        if options.auth_callback:
            log.debug("using token auth with auth_callback")
        elif options.auth_url:
            log.debug("using token auth with auth_url")
        elif options.key_secret:
            log.debug("using token auth with client-side signing")
        elif options.auth_token:
            log.debug("using token auth with supplied token only")
        elif options.token_details:
            log.debug("using token auth with supplied token_details")
        else:
            raise ValueError("Can't authenticate via token, must provide "
                             "auth_callback, auth_url, key, token or a TokenDetail")

    async def get_auth_transport_param(self):
        auth_credentials = {}
        if self.auth_options.client_id and self.auth_options.client_id != '*':
            auth_credentials["clientId"] = self.auth_options.client_id
        if self.__auth_mechanism == Auth.Method.BASIC:
            key_name = self.__auth_options.key_name
            key_secret = self.__auth_options.key_secret
            auth_credentials["key"] = f"{key_name}:{key_secret}"
        elif self.__auth_mechanism == Auth.Method.TOKEN:
            token_details = await self._ensure_valid_auth_credentials()
            auth_credentials["accessToken"] = token_details.token
        return auth_credentials

    async def __authorize_when_necessary(self, token_params=None, auth_options=None, force=False):
        token_details = await self._ensure_valid_auth_credentials(token_params, auth_options, force)

        if self.ably._is_realtime:
            await self.ably.connection.connection_manager.on_auth_updated(token_details)

        return token_details

    async def _ensure_valid_auth_credentials(self, token_params=None, auth_options=None, force=False):
        self.__auth_mechanism = Auth.Method.TOKEN
        if token_params is None:
            token_params = dict(self.auth_options.default_token_params)
        else:
            self.auth_options.default_token_params = dict(token_params)
            self.auth_options.default_token_params.pop('timestamp', None)

        if auth_options is not None:
            self.auth_options.replace(auth_options)
        auth_options = dict(self.auth_options.auth_options)
        if self.client_id is not None:
            token_params['client_id'] = self.client_id

        token_details = self.__token_details
        if not force and not self.token_details_has_expired():
            log.debug("using cached token; expires = %d",
                      token_details.expires)
            return token_details

        self.__token_details = await self.request_token(token_params, **auth_options)
        self._configure_client_id(self.__token_details.client_id)

        return self.__token_details

    def token_details_has_expired(self):
        token_details = self.__token_details
        if token_details is None:
            return True

        if not self.__time_offset:
            return False

        expires = token_details.expires
        if expires is None:
            return False

        timestamp = self._timestamp()
        if self.__time_offset:
            timestamp += self.__time_offset

        return expires < timestamp + token_details.TOKEN_EXPIRY_BUFFER

    async def authorize(self, token_params: dict | None = None, auth_options=None):
        return await self.__authorize_when_necessary(token_params, auth_options, force=True)

    async def request_token(self, token_params: dict | None = None,
                            # auth_options
                            key_name: str | None = None, key_secret: str | None = None, auth_callback=None,
                            auth_url: str | None = None, auth_method: str | None = None,
                            auth_headers: dict | None = None, auth_params: dict | None = None,
                            query_time=None):
        token_params = token_params or {}
        token_params = dict(self.auth_options.default_token_params,
                            **token_params)
        key_name = key_name or self.auth_options.key_name
        key_secret = key_secret or self.auth_options.key_secret

        log.debug(f"Auth callback: {auth_callback}")
        log.debug(f"Auth options: {self.auth_options}")
        if query_time is None:
            query_time = self.auth_options.query_time
        query_time = bool(query_time)
        auth_callback = auth_callback or self.auth_options.auth_callback
        auth_url = auth_url or self.auth_options.auth_url

        auth_params = auth_params or self.auth_options.auth_params or {}

        auth_method = (auth_method or self.auth_options.auth_method).upper()

        auth_headers = auth_headers or self.auth_options.auth_headers or {}

        log.debug(f"Token Params: {token_params}")
        if auth_callback:
            log.debug("using token auth with authCallback")
            try:
                token_request = await auth_callback(token_params)
            except Exception as e:
                raise AblyException("auth_callback raised an exception", 401, 40170, cause=e) from e
        elif auth_url:
            log.debug("using token auth with authUrl")

            token_request = await self.token_request_from_auth_url(
                auth_method, auth_url, token_params, auth_headers, auth_params)
        elif key_name is not None and key_secret is not None:
            token_request = await self.create_token_request(
                token_params, key_name=key_name, key_secret=key_secret,
                query_time=query_time)
        else:
            msg = "Need a new token but auth_options does not include a way to request one"
            log.exception(msg)
            raise AblyAuthException(msg, 403, 40171)
        if isinstance(token_request, TokenDetails):
            return token_request
        elif isinstance(token_request, dict) and 'issued' in token_request:
            return TokenDetails.from_dict(token_request)
        elif isinstance(token_request, dict):
            try:
                token_request = TokenRequest.from_json(token_request)
            except TypeError as e:
                msg = "Expected token request callback to call back with a token string, token request object, or \
                token details object"
                raise AblyAuthException(msg, 401, 40170, cause=e) from e
        elif isinstance(token_request, str):
            if len(token_request) == 0:
                raise AblyAuthException("Token string is empty", 401, 4017)
            return TokenDetails(token=token_request)
        elif token_request is None:
            raise AblyAuthException("Token string was None", 401, 40170)

        token_path = f"/keys/{token_request.key_name}/requestToken"

        response = await self.ably.http.post(
            token_path,
            headers=auth_headers,
            body=token_request.to_dict(),
            skip_auth=True
        )

        AblyException.raise_for_response(response)
        response_dict = response.to_native()
        log.debug("Token: {}".format(str(response_dict.get("token"))))
        return TokenDetails.from_dict(response_dict)

    async def create_token_request(self, token_params: dict | str | None = None, key_name: str | None = None,
                                   key_secret: str | None = None, query_time=None):
        token_params = token_params or {}
        token_request = {}

        key_name = key_name or self.auth_options.key_name
        key_secret = key_secret or self.auth_options.key_secret
        if not key_name or not key_secret:
            log.debug('key_name or key_secret blank')
            raise AblyException("No key specified: no means to generate a token", 401, 40101)

        token_request['key_name'] = key_name
        if token_params.get('timestamp'):
            token_request['timestamp'] = token_params['timestamp']
        else:
            if query_time is None:
                query_time = self.auth_options.query_time

            if query_time:
                if self.__time_offset is None:
                    server_time = await self.ably.time()
                    local_time = self._timestamp()
                    self.__time_offset = server_time - local_time
                    token_request['timestamp'] = server_time
                else:
                    local_time = self._timestamp()
                    token_request['timestamp'] = local_time + self.__time_offset
            else:
                token_request['timestamp'] = self._timestamp()

        token_request['timestamp'] = int(token_request['timestamp'])

        ttl = token_params.get('ttl')
        if ttl is not None:
            if isinstance(ttl, timedelta):
                ttl = ttl.total_seconds() * 1000
            token_request['ttl'] = int(ttl)

        capability = token_params.get('capability')
        if capability is not None:
            token_request['capability'] = str(Capability(capability))

        token_request["client_id"] = token_params.get('client_id') or self.client_id

        # Note: There is no expectation that the client
        # specifies the nonce; this is done by the library
        # However, this can be overridden by the client
        # simply for testing purposes
        token_request["nonce"] = token_params.get('nonce') or self._random_nonce()

        token_req = TokenRequest(**token_request)

        if token_params.get('mac') is None:
            # Note: There is no expectation that the client
            # specifies the mac; this is done by the library
            # However, this can be overridden by the client
            # simply for testing purposes.
            token_req.sign_request(key_secret.encode('utf8'))
        else:
            token_req.mac = token_params['mac']

        return token_req

    @property
    def ably(self):
        return self.__ably

    @property
    def auth_mechanism(self):
        return self.__auth_mechanism

    @property
    def auth_options(self):
        return self.__auth_options

    @property
    def auth_params(self):
        return self.__auth_params

    @property
    def basic_credentials(self):
        return self.__basic_credentials

    @property
    def token_credentials(self):
        if self.__token_details:
            token = self.__token_details.token
            token_key = base64.b64encode(token.encode('utf-8'))
            return token_key.decode('ascii')

    @property
    def token_details(self):
        return self.__token_details

    @property
    def client_id(self):
        return self.__client_id

    @property
    def time_offset(self):
        return self.__time_offset

    def _configure_client_id(self, new_client_id):
        log.debug("Auth._configure_client_id(): new client_id = %s", new_client_id)
        original_client_id = self.client_id or self.auth_options.client_id

        # If new client ID from Ably is a wildcard, but preconfigured clientId is set,
        # then keep the existing clientId
        if original_client_id != '*' and new_client_id == '*':
            self.__client_id_validated = True
            self.__client_id = original_client_id
            return

        # If client_id is defined and not a wildcard, prevent it changing, this is not supported
        if original_client_id is not None and original_client_id != '*' and new_client_id != original_client_id:
            raise IncompatibleClientIdException(
                "Client ID is immutable once configured for a client. "
                f"Client ID cannot be changed to '{new_client_id}'", 400, 40102)

        self.__client_id_validated = True
        self.__client_id = new_client_id

    def can_assume_client_id(self, assumed_client_id):
        original_client_id = self.client_id or self.auth_options.client_id

        if self.__client_id_validated:
            return self.client_id == '*' or self.client_id == assumed_client_id
        elif original_client_id is None or original_client_id == '*':
            return True  # client ID is unknown
        else:
            return original_client_id == assumed_client_id

    async def _get_auth_headers(self):
        if self.__auth_mechanism == Auth.Method.BASIC:
            # RSA7e2
            if self.client_id:
                return {
                    'Authorization': f'Basic {self.basic_credentials}',
                    'X-Ably-ClientId': base64.b64encode(self.client_id.encode('utf-8'))
                }
            return {
                'Authorization': f'Basic {self.basic_credentials}',
            }
        else:
            await self.__authorize_when_necessary()
            return {
                'Authorization': f'Bearer {self.token_credentials}',
            }

    def _timestamp(self):
        """Returns the local time in milliseconds since the unix epoch"""
        return int(time.time() * 1000)

    def _random_nonce(self):
        return uuid.uuid4().hex[:16]

    async def token_request_from_auth_url(self, method: str, url: str, token_params,
                                          headers, auth_params):
        # Extract URL parameters using utility function
        clean_url, url_params = extract_url_params(url)

        body = None
        params = None
        if method == 'GET':
            body = {}
            # Merge URL params, auth_params, and token_params (later params override earlier ones)
            # we do this because httpx version has inconsistency and some versions override query params
            # that are specified in url string
            params = {**url_params, **auth_params, **token_params}
        elif method == 'POST':
            if isinstance(auth_params, TokenDetails):
                auth_params = auth_params.to_dict()
            # For POST, URL params go in query string, auth_params and token_params go in body
            params = url_params
            body = dict(auth_params, **token_params)

        # Use clean URL for the request
        url = clean_url

        from ably.pubsub.request.http import Response
        async with httpx.AsyncClient(http2=True) as client:
            resp = await client.request(method=method, url=url, headers=headers, params=params, data=body)
            response = Response(resp)

        AblyException.raise_for_response(response)

        content_type = response.response.headers.get('content-type')

        if not content_type:
            raise AblyAuthException("auth_url response missing a content-type header", 401, 40170)

        is_json = "application/json" in content_type
        is_text = "application/jwt" in content_type or "text/plain" in content_type

        if is_json:
            token_request = response.to_native()
        elif is_text:
            token_request = response.text
        else:
            msg = 'auth_url responded with unacceptable content-type ' + content_type + \
                  ', should be either text/plain, application/jwt or application/json',
            raise AblyAuthException(msg, 401, 40170)
        return token_request
