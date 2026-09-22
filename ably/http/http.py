import functools
import json
import logging
import time
from urllib.parse import urljoin

import httpx
import msgpack

from ably.http.httputils import HttpUtils
from ably.rest.auth import Auth
from ably.transport.defaults import Defaults
from ably.util.exceptions import AblyException
from ably.util.helper import extract_url_params, is_token_error

log = logging.getLogger(__name__)


def reauth_if_expired(func):
    @functools.wraps(func)
    async def wrapper(rest, *args, **kwargs):
        if kwargs.get("skip_auth"):
            return await func(rest, *args, **kwargs)

        # RSA4b1 Detect expired token to avoid round-trip request
        auth = rest.auth
        token_details = auth.token_details
        if token_details and auth.time_offset is not None and auth.token_details_has_expired():
            await auth.authorize()
            retried = True
        else:
            retried = False

        try:
            return await func(rest, *args, **kwargs)
        except AblyException as e:
            if is_token_error(e) and not retried:
                await auth.authorize()
                return await func(rest, *args, **kwargs)

            raise e

    return wrapper


class Request:
    def __init__(self, method='GET', url='/', version=None, headers=None, body=None,
                 skip_auth=False, raise_on_error=True):
        self.__method = method
        self.__headers = headers or {}
        self.__body = body
        self.__skip_auth = skip_auth
        self.__url = url
        self.__version = version
        self.raise_on_error = raise_on_error

    def with_relative_url(self, relative_url):
        url = urljoin(self.url, relative_url)
        return Request(self.method, url, self.version, self.headers, self.body,
                       self.skip_auth, self.raise_on_error)

    @property
    def method(self):
        return self.__method

    @property
    def url(self):
        return self.__url

    @property
    def headers(self):
        return self.__headers

    @property
    def body(self):
        return self.__body

    @property
    def skip_auth(self):
        return self.__skip_auth

    @property
    def version(self):
        return self.__version


class Response:
    """
    Composition for httpx.Response with delegation
    """

    def __init__(self, response):
        self.__response = response

    def to_native(self):
        content = self.__response.content
        if not content:
            return None

        content_type = self.__response.headers.get('content-type')
        if isinstance(content_type, str):
            if content_type.startswith('application/x-msgpack'):
                return msgpack.unpackb(content)
            elif content_type.startswith('application/json'):
                return self.__response.json()

        raise ValueError("Unsupported content type")

    @property
    def response(self):
        return self.__response

    def __getattr__(self, attr):
        return getattr(self.__response, attr)


class Http:
    CONNECTION_RETRY_DEFAULTS = {
        'http_open_timeout': 4,
        'http_request_timeout': 10,
        'http_max_retry_duration': 15,
    }

    def __init__(self, ably, options):
        options = options or {}
        self.__ably = ably
        self.__options = options
        self.__auth = None
        # Cached fallback host (RSC15f)
        self.__host = None
        self.__host_expires = None
        self.__client = self.__create_client(options)

    @staticmethod
    def __create_client(options):
        test_options = getattr(options, 'test_options', None)
        if test_options is not None and test_options.http_transport is not None:
            return httpx.AsyncClient(transport=test_options.http_transport)
        return httpx.AsyncClient(http2=True)

    async def close(self):
        await self.__client.aclose()

    def dump_body(self, body):
        if self.options.use_binary_protocol:
            return msgpack.packb(body, use_bin_type=False)
        else:
            return json.dumps(body, separators=(',', ':'))

    def get_hosts(self):
        hosts = self.options.get_hosts()
        host = self.__host or self.options.fallback_host
        if host is None:
            return hosts

        # unstore saved fallback host after fallbackRetryTimeout (RSC15f)
        if self.__host_expires is not None and time.time() > self.__host_expires:
            self.__host = None
            self.__host_expires = None
            return hosts

        hosts = list(hosts)
        hosts.remove(host)
        hosts.insert(0, host)
        return hosts

    @reauth_if_expired
    async def make_request(self, method, path, version=None, headers=None, body=None,
                           skip_auth=False, timeout=None, raise_on_error=True):

        if body is not None and type(body) not in (bytes, str):
            body = self.dump_body(body)

        if body:
            all_headers = HttpUtils.default_post_headers(self.options.use_binary_protocol, version=version)
        else:
            all_headers = HttpUtils.default_get_headers(self.options.use_binary_protocol, version=version)

        params = HttpUtils.get_query_params(self.options)

        if not skip_auth:
            if self.auth.auth_mechanism == Auth.Method.BASIC and self.preferred_scheme.lower() == 'http':
                raise AblyException(
                    "Cannot use Basic Auth over non-TLS connections",
                    401,
                    40103)
            auth_headers = await self.auth._get_auth_headers()
            all_headers.update(auth_headers)
        if headers:
            all_headers.update(headers)

        timeout = (self.http_open_timeout, self.http_request_timeout)
        http_max_retry_duration = self.http_max_retry_duration
        requested_at = time.time()

        hosts = self.get_hosts()
        for retry_count, host in enumerate(hosts):
            def should_stop_retrying(retry_count=retry_count):
                time_passed = time.time() - requested_at
                # if it's the last try or cumulative timeout is done, we stop retrying
                return retry_count == len(hosts) - 1 or time_passed > http_max_retry_duration

            base_url = f"{self.preferred_scheme}://{host}:{self.preferred_port}"
            url = urljoin(base_url, path)

            (clean_url, url_params) = extract_url_params(url)

            request = self.__client.build_request(
                method=method,
                url=clean_url,
                content=body,
                params=dict(url_params, **params),
                headers=all_headers,
                timeout=timeout,
            )
            try:
                response = await self.__client.send(request)
            except Exception as e:
                if should_stop_retrying():
                    raise e
            else:
                # RSC15l4
                cloud_front_error = (response.headers.get('Server', '').lower() == 'cloudfront'
                                     and response.status_code >= 400)
                # RSC15l3
                retryable_server_error = response.status_code >= 500 and response.status_code <= 504
                # Resending requests that have failed for other failure conditions will not fix the problem
                # and will simply increase the load on other datacenters unnecessarily
                should_fallback = cloud_front_error or retryable_server_error

                try:
                    if raise_on_error:
                        AblyException.raise_for_response(response)

                    if should_fallback and not should_stop_retrying():
                        continue

                    # Keep fallback host for later (RSC15f)
                    if retry_count > 0 and host != self.options.get_host():
                        self.__host = host
                        self.__host_expires = time.time() + (self.options.fallback_retry_timeout / 1000.0)

                    return Response(response)
                except AblyException as e:
                    if should_stop_retrying() or not should_fallback:
                        raise e

    async def request_external(self, method, url, headers=None, params=None, body=None):
        """Performs a request to a URL outside the Ably endpoint.

        Host fallback, authentication and the default headers do not apply.
        """
        return await self.__client.request(method=method, url=url, headers=headers, params=params, data=body)

    async def delete(self, url, headers=None, skip_auth=False, timeout=None):
        result = await self.make_request('DELETE', url, headers=headers,
                                         skip_auth=skip_auth, timeout=timeout)
        return result

    async def get(self, url, headers=None, skip_auth=False, timeout=None):
        result = await self.make_request('GET', url, headers=headers,
                                         skip_auth=skip_auth, timeout=timeout)
        return result

    async def patch(self, url, headers=None, body=None, skip_auth=False, timeout=None):
        result = await self.make_request('PATCH', url, headers=headers, body=body,
                                         skip_auth=skip_auth, timeout=timeout)
        return result

    async def post(self, url, headers=None, body=None, skip_auth=False, timeout=None):
        result = await self.make_request('POST', url, headers=headers, body=body,
                                         skip_auth=skip_auth, timeout=timeout)
        return result

    async def put(self, url, headers=None, body=None, skip_auth=False, timeout=None):
        result = await self.make_request('PUT', url, headers=headers, body=body,
                                         skip_auth=skip_auth, timeout=timeout)
        return result

    @property
    def auth(self):
        return self.__auth

    @auth.setter
    def auth(self, value):
        self.__auth = value

    @property
    def options(self):
        return self.__options

    @property
    def preferred_host(self):
        return self.options.get_host()

    @property
    def preferred_port(self):
        return Defaults.get_port(self.options)

    @property
    def preferred_scheme(self):
        return Defaults.get_scheme(self.options)

    @property
    def http_open_timeout(self):
        if self.options.http_open_timeout is not None:
            return self.options.http_open_timeout
        return self.CONNECTION_RETRY_DEFAULTS['http_open_timeout']

    @property
    def http_request_timeout(self):
        if self.options.http_request_timeout is not None:
            return self.options.http_request_timeout
        return self.CONNECTION_RETRY_DEFAULTS['http_request_timeout']

    @property
    def http_max_retry_count(self):
        if self.options.http_max_retry_count is not None:
            return self.options.http_max_retry_count
        return self.CONNECTION_RETRY_DEFAULTS['http_max_retry_count']

    @property
    def http_max_retry_duration(self):
        if self.options.http_max_retry_duration is not None:
            return self.options.http_max_retry_duration
        return self.CONNECTION_RETRY_DEFAULTS['http_max_retry_duration']
