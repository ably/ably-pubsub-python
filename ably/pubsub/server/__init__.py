"""The Ably Pub/Sub client for servers.

Servers are trusted environments which typically authenticate with an API key,
and whose connections are exempt from monthly-active-user counting. This
package names that side, so the client an application reaches for is the one
whose package matches where it runs.

This is the public API of the ``ably-pubsub-server`` distribution. Both
``ably`` and ``ably.pubsub`` are PEP 420 namespace packages shared with the
other ``ably-*`` distributions, so neither carries an ``__init__.py`` of its
own and neither exports anything; everything the library offers is reachable
from here.
"""

from ably.pubsub.realtime.realtime import AblyRealtime
from ably.pubsub.rest.auth import Auth
from ably.pubsub.rest.push import Push
from ably.pubsub.rest.rest import AblyRest
from ably.pubsub.types.annotation import Annotation, AnnotationAction
from ably.pubsub.types.capability import Capability
from ably.pubsub.types.channelmode import ChannelMode
from ably.pubsub.types.channeloptions import ChannelOptions
from ably.pubsub.types.channelsubscription import PushChannelSubscription
from ably.pubsub.types.device import DeviceDetails
from ably.pubsub.types.message import MessageAction, MessageVersion
from ably.pubsub.types.operations import MessageOperation, PublishResult, UpdateDeleteResult
from ably.pubsub.types.options import Options, VCDiffDecoder
from ably.pubsub.util.crypto import CipherParams
from ably.pubsub.util.exceptions import AblyAuthException, AblyException, IncompatibleClientIdException
from ably.pubsub.vcdiff.defaultvcdiffdecoder import AblyVCDiffDecoder
from ably.pubsub.version import api_version, lib_version

__all__ = [
    'AblyAuthException',
    'AblyException',
    'AblyRealtime',
    'AblyRest',
    'AblyVCDiffDecoder',
    'Annotation',
    'AnnotationAction',
    'Auth',
    'Capability',
    'ChannelMode',
    'ChannelOptions',
    'CipherParams',
    'DeviceDetails',
    'IncompatibleClientIdException',
    'MessageAction',
    'MessageOperation',
    'MessageVersion',
    'Options',
    'PublishResult',
    'Push',
    'PushChannelSubscription',
    'UpdateDeleteResult',
    'VCDiffDecoder',
    'api_version',
    'lib_version',
]
