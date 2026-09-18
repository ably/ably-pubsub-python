"""The Ably Pub/Sub client for servers.

Servers are trusted environments which typically authenticate with an API key,
and whose connections are exempt from monthly-active-user counting. This
package names that side, so the client an application reaches for is the one
whose package matches where it runs.

Build a client with :func:`create_http_client` or
:func:`create_realtime_client`; the classes behind them are internal and
reject direct construction. Annotate against the prototypes they return,
:class:`~ably.pubsub.prototypes.PubSubHttpClient` and
:class:`~ably.pubsub.prototypes.PubSubRealtimeClient`.

This is the public API of the ``ably-pubsub-server`` distribution. Both
``ably`` and ``ably.pubsub`` are PEP 420 namespace packages shared with the
other ``ably-*`` distributions, so neither carries an ``__init__.py`` of its
own and neither exports anything; everything the library offers is reachable
from here.
"""

from ably.pubsub.http.auth import Auth
from ably.pubsub.http.channel import Channels as HttpChannels
from ably.pubsub.http.http import DefaultPubSubHttpClient as _DefaultPubSubHttpClient
from ably.pubsub.http.push import Push
from ably.pubsub.prototypes import PubSubHttpClient, PubSubRealtimeClient
from ably.pubsub.realtime.channel import Channels as RealtimeChannels
from ably.pubsub.realtime.connection import Connection
from ably.pubsub.realtime.realtime import DefaultPubSubRealtimeClient as _DefaultPubSubRealtimeClient
from ably.pubsub.request.paginatedresult import HttpPaginatedResponse, PaginatedResult
from ably.pubsub.types.annotation import Annotation, AnnotationAction
from ably.pubsub.types.capability import Capability
from ably.pubsub.types.channelmode import ChannelMode
from ably.pubsub.types.channeloptions import ChannelOptions
from ably.pubsub.types.channelsubscription import PushChannelSubscription
from ably.pubsub.types.device import DeviceDetails
from ably.pubsub.types.message import MessageAction, MessageVersion
from ably.pubsub.types.operations import MessageOperation, PublishResult, UpdateDeleteResult
from ably.pubsub.types.options import Options, VCDiffDecoder
from ably.pubsub.types.tokendetails import TokenDetails
from ably.pubsub.util.construction import factory_construction
from ably.pubsub.util.crypto import CipherParams
from ably.pubsub.util.exceptions import AblyAuthException, AblyException, IncompatibleClientIdException
from ably.pubsub.vcdiff.defaultvcdiffdecoder import AblyVCDiffDecoder
from ably.pubsub.version import api_version, lib_version


def create_http_client(**kwargs) -> PubSubHttpClient:
    """Create a server Pub/Sub client that operates entirely over HTTP.

    Handles publish, history, presence reads, stats and token issuing. Give the client one
    of `key`, `token` or `token_details` to authenticate, or configure token auth through
    `auth_callback` or `auth_url`.

    Parameters
    ----------
    **kwargs: client options
        **Credentials**

        key: str
            A valid Ably API key, in `name:secret` form. Mutually exclusive with `key_name`
            and `key_secret`.
        token: str
            A valid token string to authenticate with in place of an API key.
        token_details: TokenDetails
            A TokenDetails instance to authenticate with in place of an API key.
        key_name: str
            The first half of an API key, as an alternative to passing `key`.
        key_secret: str
            The second half of an API key, as an alternative to passing `key`.

        **Token authentication**

        auth_callback: callable
            Called when a new token is needed, and returns a token string, a TokenDetails,
            a TokenRequest or a signed token request dict. Prefer this to `auth_url` when
            the token source is in-process.
        auth_url: str
            A URL to request a token from when a new token is needed. The client issues a
            request to this URL and uses the response as the token.
        auth_method: str
            The HTTP method used for the `auth_url` request. Defaults to `GET`.
        auth_headers: dict
            Headers to include in the `auth_url` request.
        auth_params: dict
            Query parameters to include in the `auth_url` request.
        use_token_auth: bool
            Force token authentication even when an API key is available. By default the
            client uses basic auth where a key is present.
        query_time: bool
            Query the Ably service for the current time when signing token requests, rather
            than trusting the local clock. Defaults to False.
        default_token_params: dict
            Parameters applied to every token request this client makes.

        **Connection**

        client_id: str
            The ID this client identifies as. Messages it publishes carry this ID, and it
            cannot be changed once the client has authenticated.
        endpoint: str
            Either a routing policy name or a fully qualified domain name to connect to.
            Defaults to `main`. Incompatible with `environment`, `rest_host` and
            `realtime_host`.
        tls: bool
            Whether the client should use TLS. Defaults to True.
        port: int
            The non-TLS port to connect to. Defaults to 80.
        tls_port: int
            The TLS port to connect to. Defaults to 443.
        fallback_hosts: list[str]
            Hosts to fall back to when the primary endpoint is unreachable. Set this only
            if Ably has provided you with a custom set.
        fallback_retry_timeout: float
            How long (in milliseconds) a fallback host stays preferred once the client has
            failed over to it. The default is 10 minutes (600000 milliseconds).

        **HTTP behaviour**

        http_open_timeout: float
            Timeout (in seconds) for establishing an HTTP connection. The default is 4
            seconds.
        http_request_timeout: float
            Timeout (in seconds) for a complete HTTP request. The default is 10 seconds.
        http_max_retry_duration: float
            How long (in seconds) the client keeps retrying a request across hosts before
            giving up. The default is 15 seconds.
        http_max_retry_count: int
            The most hosts the client will try for a single request.

        **Protocol**

        use_binary_protocol: bool
            Encode messages with MessagePack rather than JSON. Defaults to True.
        idempotent_rest_publishing: bool
            Assign an ID to published messages so that a retried publish is not duplicated.
            Defaults to True.
        add_request_ids: bool
            Add a `request_id` query parameter to every request, which makes a request
            traceable in Ably's logs. Defaults to False.
        log_level: int
            Verbosity of the library's own logging. Defaults to 0.

        **Deprecated**

        rest_host: str
            Deprecated: this option will be removed in a future version. Use `endpoint`.
        environment: str
            Deprecated: this option will be removed in a future version. Use `endpoint`.

    Returns
    -------
    PubSubHttpClient
        A client ready to use. It opens no connection until its first request.

    Raises
    ------
    ValueError
        If `key` is combined with `key_name` or `key_secret`.
    AblyException
        If no means of authenticating is given, or if `endpoint` is combined with
        `environment`, `rest_host` or `realtime_host`.
    """
    with factory_construction():
        return _DefaultPubSubHttpClient(**kwargs)


def create_realtime_client(**kwargs) -> PubSubRealtimeClient:
    """Create a server Pub/Sub client with a persistent realtime connection.

    Everything the HTTP client does, plus subscribing to channels and entering presence.
    Accepts every option :func:`create_http_client` does — see there for credentials,
    token authentication, connection and HTTP behaviour — and the following in addition.

    Parameters
    ----------
    **kwargs: client options
        **Connection lifecycle**

        loop: asyncio.AbstractEventLoop
            The event loop the client runs on. Defaults to the running loop; the client
            logs a warning if it is created outside one.
        auto_connect: bool
            Connect as soon as the client is created. Set this to False to connect later
            with `connect()`. Defaults to True.
        recover: str
            A recovery key from a previous connection, used to resume that connection's
            state and message continuity rather than starting fresh.
        queue_messages: bool
            Hold messages published while the connection is not yet established and send
            them once it is, rather than failing them. Defaults to True.
        transport_params: dict
            Additional query parameters to send when opening the realtime connection.

        **Timeouts and retries**

        realtime_request_timeout: float
            How long (in milliseconds) to wait for acknowledgement of an operation
            performed over the realtime connection, such as establishing a connection or
            sending a HEARTBEAT, CONNECT, ATTACH, DETACH or CLOSE request. The default is
            10 seconds (10000 milliseconds).
        disconnected_retry_timeout: float
            How long (in milliseconds) to stay DISCONNECTED before attempting to reconnect
            automatically. The default is 15 seconds (15000 milliseconds).
        suspended_retry_timeout: float
            How long (in milliseconds) to stay SUSPENDED before attempting to reconnect
            automatically. The default is 30 seconds (30000 milliseconds).
        channel_retry_timeout: float
            How long (in milliseconds) a channel stays SUSPENDED, following a server
            initiated DETACHED, before the client re-attaches it — provided the connection
            is CONNECTED. The default is 15 seconds (15000 milliseconds).
        connectivity_check_url: str
            The URL the client requests to decide whether the internet is reachable. On
            failing to reach the primary endpoint, a success response from this URL tells
            the client to try a fallback host instead of giving up.

        **Deltas**

        vcdiff_decoder: VCDiffDecoder
            The decoder used to apply delta-encoded messages on channels configured with
            `params={"delta": "vcdiff"}`. Pass an :class:`AblyVCDiffDecoder`.

        **Deprecated**

        realtime_host: str
            Deprecated: this option will be removed in a future version. Use `endpoint`.

    Returns
    -------
    PubSubRealtimeClient
        A client which, unless `auto_connect=False`, is already connecting.

    Raises
    ------
    ValueError
        If `key` is combined with `key_name` or `key_secret`.
    AblyException
        If no means of authenticating is given, or if `endpoint` is combined with
        `environment`, `rest_host` or `realtime_host`.
    """
    with factory_construction():
        return _DefaultPubSubRealtimeClient(**kwargs)


__all__ = [
    'AblyAuthException',
    'AblyException',
    'AblyVCDiffDecoder',
    'Annotation',
    'AnnotationAction',
    'Auth',
    'Capability',
    'ChannelMode',
    'ChannelOptions',
    'CipherParams',
    'Connection',
    'DeviceDetails',
    'HttpChannels',
    'HttpPaginatedResponse',
    'IncompatibleClientIdException',
    'MessageAction',
    'MessageOperation',
    'MessageVersion',
    'Options',
    'PaginatedResult',
    'PubSubHttpClient',
    'PubSubRealtimeClient',
    'PublishResult',
    'Push',
    'PushChannelSubscription',
    'RealtimeChannels',
    'TokenDetails',
    'UpdateDeleteResult',
    'VCDiffDecoder',
    'api_version',
    'create_http_client',
    'create_realtime_client',
    'lib_version',
]
