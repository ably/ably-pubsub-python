import json
import logging
from typing import List, Optional, Union
from urllib.parse import urlencode

import msgpack

from ably.pubsub.http.auth import Auth
from ably.pubsub.http.channel import Channels
from ably.pubsub.http.push import Push
from ably.pubsub.prototypes import PubSubHttpClient
from ably.pubsub.request.http import Http
from ably.pubsub.request.paginatedresult import HttpPaginatedResponse, PaginatedResult, format_params
from ably.pubsub.types.batch import (
    BatchPublishSpec,
    BatchResult,
    batch_presence_result_from_dict,
    batch_publish_result_from_dict,
)
from ably.pubsub.types.message import assign_idempotent_ids
from ably.pubsub.types.options import Options
from ably.pubsub.types.stats import stats_response_processor
from ably.pubsub.types.tokendetails import TokenDetails
from ably.pubsub.util.construction import reject_direct_construction
from ably.pubsub.util.exceptions import AblyException, catch_all

log = logging.getLogger(__name__)


class DefaultPubSubHttpClient(PubSubHttpClient):
    """The default :class:`~ably.pubsub.prototypes.PubSubHttpClient` implementation.

    Built by :func:`ably.pubsub.server.create_http_client`, which is the only
    way to construct one.
    """

    def __init__(self, key: Optional[str] = None, token: Optional[str] = None,
                 token_details: Optional[TokenDetails] = None, **kwargs):
        """Create an DefaultPubSubHttpClient instance.

        :Parameters:
          **Credentials**
          - `key`: a valid key string

          **Or**
          - `token`: a valid token string
          - `token_details`: an instance of TokenDetails class

          **Optional Parameters**
          - `client_id`: Undocumented
          - `endpoint`: Endpoint specifies either a routing policy name or
            fully qualified domain name to connect to Ably.
          - `rest_host`: Deprecated: this property is deprecated and will
            be removed in a future version. The host to connect to.
            Defaults to rest.ably.io
          - `environment`: Deprecated: this property is deprecated and
            will be removed in a future version. The environment to use.
            Defaults to 'production'
          - `port`: The port to connect to. Defaults to 80
          - `tls_port`: The tls_port to connect to. Defaults to 443
          - `tls`: Specifies whether the client should use TLS. Defaults
            to True
          - `auth_token`: Undocumented
          - `auth_callback`: Undocumented
          - `auth_url`: Undocumented
        """
        reject_direct_construction(type(self), 'ably.pubsub.server.create_http_client')

        if key is not None and ('key_name' in kwargs or 'key_secret' in kwargs):
            raise ValueError("key and key_name or key_secret are mutually exclusive. "
                             "Provider either a key or key_name & key_secret")
        if key is not None:
            options = Options(key=key, **kwargs)
        elif token is not None:
            options = Options(auth_token=token, **kwargs)
        elif token_details is not None:
            if not isinstance(token_details, TokenDetails):
                raise ValueError("token_details must be an instance of TokenDetails")
            options = Options(token_details=token_details, **kwargs)
        elif not ('auth_callback' in kwargs or 'auth_url' in kwargs or
                  # and don't have both key_name and key_secret
                  ('key_name' in kwargs and 'key_secret' in kwargs)):
            raise ValueError("key is missing. Either an API key, token, or token auth method must be provided")
        else:
            options = Options(**kwargs)

        if not hasattr(self, '_is_realtime'):
            self._is_realtime = False

        self.__http = Http(self, options)
        self.__auth = Auth(self, options)
        self.__http.auth = self.__auth

        self.__channels = Channels(self)
        self.__options = options
        self.__push = Push(self)

    async def __aenter__(self):
        return self

    @catch_all
    async def stats(self, direction: Optional[str] = None, start=None, end=None, params: Optional[dict] = None,
                    limit: Optional[int] = None, paginated=None, unit=None, timeout=None):
        """Returns the stats for this application"""
        formatted_params = format_params(params, direction=direction, start=start, end=end, limit=limit, unit=unit)
        url = '/stats' + formatted_params
        return await PaginatedResult.paginated_query(
            self.http, url=url, response_processor=stats_response_processor)

    @catch_all
    async def time(self, timeout: Optional[float] = None) -> float:
        """Returns the current server time in ms since the unix epoch"""
        r = await self.http.get('/time', skip_auth=True, timeout=timeout)
        AblyException.raise_for_response(r)
        return r.to_native()[0]

    async def batch_publish(self, specs) -> Union[BatchResult, List[BatchResult]]:
        """Publishes messages to several channels in a single request (RSC22)

        :Parameters:
        - `specs`: a `BatchPublishSpec`, or a list of them. A dict with
          `channels` and `messages` keys may stand in for a `BatchPublishSpec`.

        Returns a `BatchResult` holding a `BatchPublishSuccessResult` or a
        `BatchPublishFailureResult` for each channel the spec names, or, given
        a list of specs, a list of `BatchResult`s in the same order.
        """
        single = not isinstance(specs, (list, tuple))
        specs = [BatchPublishSpec.factory(spec) for spec in ([specs] if single else specs)]

        for spec in specs:
            if not spec.channels:
                raise AblyException('A batch publish spec must name at least one channel', 400, 40000)
            if not spec.messages:
                raise AblyException('A batch publish spec must include at least one message', 400, 40000)

        # RSC22d: RSL1k1 applies to each spec separately
        if self.options.idempotent_rest_publishing:
            for spec in specs:
                assign_idempotent_ids(spec.messages)

        binary = self.options.use_binary_protocol
        body = [spec.as_dict(binary=binary) for spec in specs]
        if single:
            body = body[0]
        if binary:
            body = msgpack.packb(body, use_bin_type=True)
        else:
            body = json.dumps(body, separators=(',', ':'))

        response = await self.http.post('/messages', body=body)

        # RSC22b: the response is an array with a result for each spec, even when a single spec was sent
        results = [BatchResult.from_dict(result, batch_publish_result_from_dict)
                   for result in response.to_native()]
        return results[0] if single else results

    async def batch_presence(self, channels: List[str]) -> BatchResult:
        """Retrieves the members present on several channels in a single request (RSC24)

        :Parameters:
        - `channels`: the names of the channels

        Returns a `BatchResult` holding a `BatchPresenceSuccessResult` or a
        `BatchPresenceFailureResult` for each channel.
        """
        if isinstance(channels, str):
            raise TypeError('Unexpected str channels, expected a list of channel names')

        path = '/presence?' + urlencode({'channels': ','.join(channels)})
        response = await self.http.get(path)
        return BatchResult.from_dict(response.to_native(), batch_presence_result_from_dict)

    @property
    def client_id(self) -> Optional[str]:
        return self.options.client_id

    @property
    def channels(self):
        """Returns the channels container object"""
        return self.__channels

    @property
    def auth(self):
        return self.__auth

    @property
    def http(self):
        return self.__http

    @property
    def options(self):
        return self.__options

    @property
    def push(self):
        return self.__push

    async def request(self, method: str, path: str, version: str, params:
                      Optional[dict] = None, body=None, headers=None):
        if version is None:
            raise AblyException("No version parameter", 400, 40000)

        url = path
        if params:
            url += '?' + urlencode(params)

        def response_processor(response):
            items = response.to_native()
            if not items:
                return []
            if type(items) is not list:
                items = [items]
            return items

        return await HttpPaginatedResponse.paginated_query(
            self.http, method, url, version=version, body=body, headers=headers,
            response_processor=response_processor,
            raise_on_error=False)

    async def __aexit__(self, *excinfo):
        await self.close()

    async def close(self):
        await self.http.close()
