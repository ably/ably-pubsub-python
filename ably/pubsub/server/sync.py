"""The synchronous flavour of the Ably Pub/Sub client for servers.

Exposes the same HTTP surface as :mod:`ably.pubsub.server`, generated without
``async``/``await`` so it can be driven from a thread rather than an event
loop. There is no synchronous realtime client, so a server that needs to
subscribe to channels should use :func:`ably.pubsub.server.create_realtime_client`
instead.

It exports every name :mod:`ably.pubsub.server` does except those of the realtime
client, its connection and channel states and its realtime channel, presence and
annotations. The classes of the objects the client hands out keep a ``Sync``
suffix, as in :class:`ChannelSync` and :class:`PresenceSync`; data types, enums
and exceptions keep their plain names.
"""

from ably.pubsub.sync.http.annotations import HttpAnnotationsSync
from ably.pubsub.sync.http.auth import AuthSync
from ably.pubsub.sync.http.channel import ChannelsSync as HttpChannelsSync
from ably.pubsub.sync.http.channel import ChannelSync
from ably.pubsub.sync.http.http import DefaultPubSubHttpClientSync as _DefaultPubSubHttpClientSync
from ably.pubsub.sync.http.push import (
    PushAdminSync,
    PushChannelSubscriptionsSync,
    PushDeviceRegistrationsSync,
    PushSync,
)
from ably.pubsub.sync.prototypes import PubSubHttpClient
from ably.pubsub.sync.request.paginatedresult import HttpPaginatedResponseSync, PaginatedResultSync
from ably.pubsub.sync.types.annotation import Annotation, AnnotationAction
from ably.pubsub.sync.types.batch import (
    BatchPresenceFailureResult,
    BatchPresenceSuccessResult,
    BatchPublishFailureResult,
    BatchPublishSpec,
    BatchPublishSuccessResult,
    BatchResult,
)
from ably.pubsub.sync.types.capability import Capability
from ably.pubsub.sync.types.channeldetails import ChannelDetails, ChannelMetrics, ChannelOccupancy, ChannelStatus
from ably.pubsub.sync.types.channelmode import ChannelMode
from ably.pubsub.sync.types.channeloptions import ChannelOptions
from ably.pubsub.sync.types.channelsubscription import PushChannelSubscription
from ably.pubsub.sync.types.device import DeviceDetails, DevicePushDetails
from ably.pubsub.sync.types.message import Message, MessageAction, MessageVersion
from ably.pubsub.sync.types.operations import MessageOperation, PublishResult, UpdateDeleteResult
from ably.pubsub.sync.types.options import Options, VCDiffDecoder
from ably.pubsub.sync.types.presence import PresenceAction, PresenceMessage, PresenceSync
from ably.pubsub.sync.types.stats import Stats
from ably.pubsub.sync.types.tokendetails import TokenDetails
from ably.pubsub.sync.types.tokenrequest import TokenRequest
from ably.pubsub.sync.util.construction import factory_construction
from ably.pubsub.sync.util.crypto import CipherParams, generate_random_key, get_default_params
from ably.pubsub.sync.util.exceptions import (
    AblyAuthException,
    AblyException,
    IncompatibleClientIdException,
    InvalidArgumentException,
)
from ably.pubsub.sync.vcdiff.defaultvcdiffdecoder import AblyVCDiffDecoder
from ably.pubsub.version import api_version, lib_version


def create_http_client(**kwargs) -> PubSubHttpClient:
    """Create a synchronous server Pub/Sub client that operates entirely over HTTP.

    Accepts every option :func:`ably.pubsub.server.create_http_client` does — see there
    for credentials, token authentication, connection and HTTP behaviour — and behaves
    identically, without the event loop. The realtime-only options have no effect here.
    It logs to the `ably.pubsub` logger, as that function describes.

    Returns
    -------
    PubSubHttpClient
        A client ready to use. It opens no connection until its first request.

    Raises
    ------
    AblyException
        With code 40106, if no means of authenticating is given, or if `key` is
        combined with `key_name` or `key_secret`; with code 40000 if a `*_seconds`
        timing option is not a finite, non-negative int or float. It is also a
        ValueError.
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
    'BatchPresenceFailureResult',
    'BatchPresenceSuccessResult',
    'BatchPublishFailureResult',
    'BatchPublishSpec',
    'BatchPublishSuccessResult',
    'BatchResult',
    'Capability',
    'ChannelDetails',
    'ChannelMetrics',
    'ChannelMode',
    'ChannelOccupancy',
    'ChannelOptions',
    'ChannelStatus',
    'ChannelSync',
    'CipherParams',
    'DeviceDetails',
    'DevicePushDetails',
    'HttpAnnotationsSync',
    'HttpChannelsSync',
    'HttpPaginatedResponseSync',
    'IncompatibleClientIdException',
    'InvalidArgumentException',
    'Message',
    'MessageAction',
    'MessageOperation',
    'MessageVersion',
    'Options',
    'PaginatedResultSync',
    'PresenceAction',
    'PresenceMessage',
    'PresenceSync',
    'PubSubHttpClient',
    'PublishResult',
    'PushAdminSync',
    'PushChannelSubscription',
    'PushChannelSubscriptionsSync',
    'PushDeviceRegistrationsSync',
    'PushSync',
    'Stats',
    'TokenDetails',
    'TokenRequest',
    'UpdateDeleteResult',
    'VCDiffDecoder',
    'api_version',
    'create_http_client',
    'generate_random_key',
    'get_default_params',
    'lib_version',
]
