"""The synchronous flavour of the Ably Pub/Sub client for servers.

Exposes the same HTTP surface as :mod:`ably.pubsub.server`, generated without
``async``/``await`` so it can be driven from a thread rather than an event
loop. There is no synchronous realtime client, so a server that needs to
subscribe to channels should use :func:`ably.pubsub.server.create_realtime_client`
instead.
"""

from ably.pubsub.sync.http.auth import AuthSync
from ably.pubsub.sync.http.channel import ChannelsSync as HttpChannelsSync
from ably.pubsub.sync.http.http import DefaultPubSubHttpClientSync as _DefaultPubSubHttpClientSync
from ably.pubsub.sync.http.push import PushSync
from ably.pubsub.sync.prototypes import PubSubHttpClient
from ably.pubsub.sync.request.paginatedresult import HttpPaginatedResponseSync, PaginatedResultSync
from ably.pubsub.sync.types.annotation import Annotation, AnnotationAction
from ably.pubsub.sync.types.capability import Capability
from ably.pubsub.sync.types.channelmode import ChannelMode
from ably.pubsub.sync.types.channeloptions import ChannelOptions
from ably.pubsub.sync.types.channelsubscription import PushChannelSubscription
from ably.pubsub.sync.types.device import DeviceDetails
from ably.pubsub.sync.types.message import MessageAction, MessageVersion
from ably.pubsub.sync.types.operations import MessageOperation, PublishResult, UpdateDeleteResult
from ably.pubsub.sync.types.options import Options, VCDiffDecoder
from ably.pubsub.sync.types.tokendetails import TokenDetails
from ably.pubsub.sync.util.construction import factory_construction
from ably.pubsub.sync.util.crypto import CipherParams
from ably.pubsub.sync.util.exceptions import AblyAuthException, AblyException, IncompatibleClientIdException
from ably.pubsub.sync.vcdiff.defaultvcdiffdecoder import AblyVCDiffDecoder
from ably.pubsub.version import api_version, lib_version


def create_http_client(**kwargs) -> PubSubHttpClient:
    """Create a synchronous server Pub/Sub client that operates entirely over HTTP.

    Accepts every option :func:`ably.pubsub.server.create_http_client` does — see there
    for credentials, token authentication, connection and HTTP behaviour — and behaves
    identically, without the event loop. The realtime-only options have no effect here.

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
        return _DefaultPubSubHttpClientSync(**kwargs)


__all__ = [
    'AblyAuthException',
    'AblyException',
    'AblyVCDiffDecoder',
    'Annotation',
    'AnnotationAction',
    'AuthSync',
    'Capability',
    'ChannelMode',
    'ChannelOptions',
    'CipherParams',
    'DeviceDetails',
    'HttpChannelsSync',
    'HttpPaginatedResponseSync',
    'IncompatibleClientIdException',
    'MessageAction',
    'MessageOperation',
    'MessageVersion',
    'Options',
    'PaginatedResultSync',
    'PubSubHttpClient',
    'PublishResult',
    'PushChannelSubscription',
    'PushSync',
    'TokenDetails',
    'UpdateDeleteResult',
    'VCDiffDecoder',
    'api_version',
    'create_http_client',
    'lib_version',
]
