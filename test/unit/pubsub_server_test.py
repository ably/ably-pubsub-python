import importlib
import inspect
import typing

import pytest

import ably.pubsub.server as server
import ably.pubsub.server.liveobjects as server_liveobjects
import ably.pubsub.server.sync as server_sync
from ably.pubsub.http.http import DefaultPubSubHttpClient
from ably.pubsub.prototypes import PubSubHttpClient, PubSubRealtimeClient
from ably.pubsub.realtime.realtime import DefaultPubSubRealtimeClient
from ably.pubsub.server import create_http_client, create_realtime_client
from ably.pubsub.sync.http.http import DefaultPubSubHttpClientSync
from ably.pubsub.sync.prototypes import PubSubHttpClient as PubSubHttpClientSync


def protocol_members(protocol):
    """The members `protocol` declares.

    Python 3.12 records these on the class. Earlier versions only have typing's
    own helper, which is the function that builds that attribute, so the two
    agree. Reading `vars(protocol)` instead would sweep in `__init__`,
    `__abstractmethods__`, `__parameters__` and the rest of the Protocol
    machinery, and report them as members the client fails to implement.
    """
    members = getattr(protocol, '__protocol_attrs__', None)
    if members is None:
        members = typing._get_protocol_attrs(protocol)
    return set(members)


def implementation_classes(protocol, cls):
    """The classes in `cls`'s MRO that implement, rather than declare, the prototype.

    The clients subclass their prototype, so every prototype member is reachable
    on them whether or not they implement it — an unimplemented one resolves to
    the prototype's `...` stub and silently returns None. Dropping the
    prototype's own MRO leaves only the classes that can genuinely define a
    member.
    """
    return [k for k in cls.__mro__ if k not in protocol.__mro__]


def declared_member(classes, name):
    """The attribute `name` as the first class in `classes` defines it, if any."""
    for k in classes:
        if name in k.__dict__:
            return k.__dict__[name]
    return None


def parameter_shape(member):
    """A member's callable shape: whether it awaits, and its parameters.

    Annotations are left out deliberately — the prototype spells its types as
    strings under `from __future__ import annotations` while the clients
    evaluate theirs, and return types are a type checker's business. Parameter
    names, kinds and which ones are required are what callers depend on.
    """
    fn = member.fget if isinstance(member, property) else member
    parameters = [
        (p.name, p.kind, p.default is inspect.Parameter.empty)
        for p in inspect.signature(fn).parameters.values()
    ]
    return inspect.iscoroutinefunction(fn), parameters


class TestFactories:
    def test_http_factory_returns_a_client(self):
        client = create_http_client(token='foo')
        assert isinstance(client, DefaultPubSubHttpClient)

    async def test_realtime_factory_returns_a_client(self):
        client = create_realtime_client(key='foo:bar', auto_connect=False)
        assert isinstance(client, DefaultPubSubRealtimeClient)
        await client.close()

    def test_sync_http_factory_returns_a_client(self):
        assert isinstance(server_sync.create_http_client(token='foo'), DefaultPubSubHttpClientSync)

    def test_factory_passes_options_through(self):
        client = create_http_client(token='foo', client_id='me')
        assert client.client_id == 'me'


class TestConstructorsAreInternal:
    def test_rest_constructor_is_rejected(self):
        with pytest.raises(TypeError) as excinfo:
            DefaultPubSubHttpClient(token='foo')
        assert 'ably.pubsub.server.create_http_client' in str(excinfo.value)

    def test_realtime_constructor_is_rejected(self):
        with pytest.raises(TypeError) as excinfo:
            DefaultPubSubRealtimeClient(key='foo:bar', auto_connect=False)
        assert 'ably.pubsub.server.create_realtime_client' in str(excinfo.value)

    def test_sync_rest_constructor_is_rejected(self):
        with pytest.raises(TypeError) as excinfo:
            DefaultPubSubHttpClientSync(token='foo')
        assert 'ably.pubsub.server.sync.create_http_client' in str(excinfo.value)

    def test_permission_does_not_leak_past_the_factory(self):
        create_http_client(token='foo')
        with pytest.raises(TypeError):
            DefaultPubSubHttpClient(token='foo')

    @pytest.mark.parametrize('name', ['DefaultPubSubHttpClient', 'DefaultPubSubRealtimeClient'])
    def test_client_classes_are_not_exported(self, name):
        assert not hasattr(server, name)
        assert name not in server.__all__

    def test_sync_client_class_is_not_exported(self):
        assert not hasattr(server_sync, 'DefaultPubSubHttpClientSync')
        assert 'DefaultPubSubHttpClientSync' not in server_sync.__all__


# Every prototype paired with the client declared to implement it, the
# synchronous flavour included — unasync generates both sides of that pair,
# so the pairing is worth checking rather than assuming.
PROTOTYPE_IMPLEMENTATIONS = [
    (PubSubHttpClient, DefaultPubSubHttpClient),
    (PubSubRealtimeClient, DefaultPubSubRealtimeClient),
    (PubSubHttpClientSync, DefaultPubSubHttpClientSync),
]


class TestPrototypes:
    @pytest.mark.parametrize('protocol,cls', PROTOTYPE_IMPLEMENTATIONS)
    def test_client_is_declared_to_satisfy_its_prototype(self, protocol, cls):
        assert protocol in cls.__mro__

    @pytest.mark.parametrize('protocol,cls', PROTOTYPE_IMPLEMENTATIONS)
    def test_client_implements_every_prototype_member(self, protocol, cls):
        owners = implementation_classes(protocol, cls)
        missing = sorted(
            member for member in protocol_members(protocol)
            if declared_member(owners, member) is None
        )
        assert missing == []

    @pytest.mark.parametrize('protocol,cls', PROTOTYPE_IMPLEMENTATIONS)
    def test_client_members_match_the_prototype_signature(self, protocol, cls):
        owners = implementation_classes(protocol, cls)
        mismatched = {}
        for member in sorted(protocol_members(protocol)):
            expected = parameter_shape(declared_member(protocol.__mro__, member))
            actual = parameter_shape(declared_member(owners, member))
            if expected != actual:
                mismatched[member] = {'prototype': expected, 'client': actual}
        assert mismatched == {}

    @pytest.mark.parametrize('name', ['PubSubHttpClient', 'PubSubRealtimeClient'])
    def test_prototypes_are_exported(self, name):
        assert name in server.__all__

    def test_sync_prototype_is_exported(self):
        assert 'PubSubHttpClient' in server_sync.__all__


class TestPublicTypes:
    # update_message() takes a Message, so callers need a public way to build one
    def test_message_is_exported(self):
        assert 'Message' in server.__all__
        assert 'Message' in server_sync.__all__

    # RSE2: channel encryption needs a public way to generate a key and build cipher params
    @pytest.mark.parametrize('name', ['generate_random_key', 'get_default_params'])
    def test_crypto_helpers_are_exported(self, name):
        assert name in server.__all__
        assert name in server_sync.__all__

    # LiveObjects names live in their own module, named for the product (PDR-080), so
    # that generic ones such as Batch and Subscription stay apart from the Pub/Sub names
    @pytest.mark.parametrize('name', ['Batch', 'LiveCounter', 'LiveMap', 'PathObject', 'Subscription'])
    def test_liveobjects_names_are_exported_from_their_own_module(self, name):
        assert name in server_liveobjects.__all__
        assert name not in server.__all__
        assert not hasattr(server, name)

    def test_liveobjects_names_are_all_importable(self):
        for name in server_liveobjects.__all__:
            assert getattr(server_liveobjects, name) is not None


# Every name ably.pubsub.server exports, as (name, defining module, name there). The list
# is the public API: a name added or removed here is a change to it.
ASYNC_EXPORTS = [
    ('AblyAuthException', 'ably.pubsub.util.exceptions', 'AblyAuthException'),
    ('AblyException', 'ably.pubsub.util.exceptions', 'AblyException'),
    ('AblyVCDiffDecoder', 'ably.pubsub.vcdiff.defaultvcdiffdecoder', 'AblyVCDiffDecoder'),
    ('Annotation', 'ably.pubsub.types.annotation', 'Annotation'),
    ('AnnotationAction', 'ably.pubsub.types.annotation', 'AnnotationAction'),
    ('Auth', 'ably.pubsub.http.auth', 'Auth'),
    ('BatchPresenceFailureResult', 'ably.pubsub.types.batch', 'BatchPresenceFailureResult'),
    ('BatchPresenceSuccessResult', 'ably.pubsub.types.batch', 'BatchPresenceSuccessResult'),
    ('BatchPublishFailureResult', 'ably.pubsub.types.batch', 'BatchPublishFailureResult'),
    ('BatchPublishSpec', 'ably.pubsub.types.batch', 'BatchPublishSpec'),
    ('BatchPublishSuccessResult', 'ably.pubsub.types.batch', 'BatchPublishSuccessResult'),
    ('BatchResult', 'ably.pubsub.types.batch', 'BatchResult'),
    ('Capability', 'ably.pubsub.types.capability', 'Capability'),
    ('Channel', 'ably.pubsub.http.channel', 'Channel'),
    ('ChannelDetails', 'ably.pubsub.types.channeldetails', 'ChannelDetails'),
    ('ChannelMetrics', 'ably.pubsub.types.channeldetails', 'ChannelMetrics'),
    ('ChannelMode', 'ably.pubsub.types.channelmode', 'ChannelMode'),
    ('ChannelOccupancy', 'ably.pubsub.types.channeldetails', 'ChannelOccupancy'),
    ('ChannelOptions', 'ably.pubsub.types.channeloptions', 'ChannelOptions'),
    ('ChannelState', 'ably.pubsub.types.channelstate', 'ChannelState'),
    ('ChannelStateChange', 'ably.pubsub.types.channelstate', 'ChannelStateChange'),
    ('ChannelStatus', 'ably.pubsub.types.channeldetails', 'ChannelStatus'),
    ('CipherParams', 'ably.pubsub.util.crypto', 'CipherParams'),
    ('Connection', 'ably.pubsub.realtime.connection', 'Connection'),
    ('ConnectionEvent', 'ably.pubsub.types.connectionstate', 'ConnectionEvent'),
    ('ConnectionState', 'ably.pubsub.types.connectionstate', 'ConnectionState'),
    ('ConnectionStateChange', 'ably.pubsub.types.connectionstate', 'ConnectionStateChange'),
    ('DeviceDetails', 'ably.pubsub.types.device', 'DeviceDetails'),
    ('DevicePushDetails', 'ably.pubsub.types.device', 'DevicePushDetails'),
    ('HttpAnnotations', 'ably.pubsub.http.annotations', 'HttpAnnotations'),
    ('HttpChannels', 'ably.pubsub.http.channel', 'Channels'),
    ('HttpPaginatedResponse', 'ably.pubsub.request.paginatedresult', 'HttpPaginatedResponse'),
    ('IncompatibleClientIdException', 'ably.pubsub.util.exceptions', 'IncompatibleClientIdException'),
    ('InvalidArgumentException', 'ably.pubsub.util.exceptions', 'InvalidArgumentException'),
    ('Message', 'ably.pubsub.types.message', 'Message'),
    ('MessageAction', 'ably.pubsub.types.message', 'MessageAction'),
    ('MessageOperation', 'ably.pubsub.types.operations', 'MessageOperation'),
    ('MessageVersion', 'ably.pubsub.types.message', 'MessageVersion'),
    ('Options', 'ably.pubsub.types.options', 'Options'),
    ('PaginatedResult', 'ably.pubsub.request.paginatedresult', 'PaginatedResult'),
    ('Presence', 'ably.pubsub.types.presence', 'Presence'),
    ('PresenceAction', 'ably.pubsub.types.presence', 'PresenceAction'),
    ('PresenceMessage', 'ably.pubsub.types.presence', 'PresenceMessage'),
    ('PubSubHttpClient', 'ably.pubsub.prototypes', 'PubSubHttpClient'),
    ('PubSubRealtimeClient', 'ably.pubsub.prototypes', 'PubSubRealtimeClient'),
    ('PublishResult', 'ably.pubsub.types.operations', 'PublishResult'),
    ('Push', 'ably.pubsub.http.push', 'Push'),
    ('PushAdmin', 'ably.pubsub.http.push', 'PushAdmin'),
    ('PushChannelSubscription', 'ably.pubsub.types.channelsubscription', 'PushChannelSubscription'),
    ('PushChannelSubscriptions', 'ably.pubsub.http.push', 'PushChannelSubscriptions'),
    ('PushDeviceRegistrations', 'ably.pubsub.http.push', 'PushDeviceRegistrations'),
    ('RealtimeAnnotations', 'ably.pubsub.realtime.annotations', 'RealtimeAnnotations'),
    ('RealtimeChannel', 'ably.pubsub.realtime.channel', 'RealtimeChannel'),
    ('RealtimeChannels', 'ably.pubsub.realtime.channel', 'Channels'),
    ('RealtimePresence', 'ably.pubsub.realtime.presence', 'RealtimePresence'),
    ('Stats', 'ably.pubsub.types.stats', 'Stats'),
    ('TokenDetails', 'ably.pubsub.types.tokendetails', 'TokenDetails'),
    ('TokenRequest', 'ably.pubsub.types.tokenrequest', 'TokenRequest'),
    ('UpdateDeleteResult', 'ably.pubsub.types.operations', 'UpdateDeleteResult'),
    ('VCDiffDecoder', 'ably.pubsub.types.options', 'VCDiffDecoder'),
    ('api_version', 'ably.pubsub.version', 'api_version'),
    ('create_http_client', 'ably.pubsub.server', 'create_http_client'),
    ('create_realtime_client', 'ably.pubsub.server', 'create_realtime_client'),
    ('generate_random_key', 'ably.pubsub.util.crypto', 'generate_random_key'),
    ('get_default_params', 'ably.pubsub.util.crypto', 'get_default_params'),
    ('lib_version', 'ably.pubsub.version', 'lib_version'),
]

# The names that belong to the realtime client. There is no synchronous realtime client, so
# ably.pubsub.server.sync exports none of them, though the generated tree has classes for some.
REALTIME_ONLY = {
    'ChannelState',
    'ChannelStateChange',
    'Connection',
    'ConnectionEvent',
    'ConnectionState',
    'ConnectionStateChange',
    'PubSubRealtimeClient',
    'RealtimeAnnotations',
    'RealtimeChannel',
    'RealtimeChannels',
    'RealtimePresence',
    'create_realtime_client',
}

# The synchronous name of an export whose generated class takes a Sync suffix. Every other
# export keeps its name in ably.pubsub.server.sync.
SYNC_NAMES = {
    'Auth': 'AuthSync',
    'Channel': 'ChannelSync',
    'HttpAnnotations': 'HttpAnnotationsSync',
    'HttpChannels': 'HttpChannelsSync',
    'HttpPaginatedResponse': 'HttpPaginatedResponseSync',
    'PaginatedResult': 'PaginatedResultSync',
    'Presence': 'PresenceSync',
    'Push': 'PushSync',
    'PushAdmin': 'PushAdminSync',
    'PushChannelSubscriptions': 'PushChannelSubscriptionsSync',
    'PushDeviceRegistrations': 'PushDeviceRegistrationsSync',
}

SYNC_ALL = [
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


def sync_export(name, module, attr):
    """The sync export an async one maps to, as (name, defining module, name there)."""
    if module == 'ably.pubsub.version':
        return name, module, attr
    if module == 'ably.pubsub.server':
        return name, 'ably.pubsub.server.sync', attr
    sync_module = module.replace('ably.pubsub.', 'ably.pubsub.sync.', 1)
    if name in SYNC_NAMES:
        return SYNC_NAMES[name], sync_module, attr + 'Sync'
    return name, sync_module, attr


SYNC_EXPORTS = [sync_export(*e) for e in ASYNC_EXPORTS if e[0] not in REALTIME_ONLY]


def star_import(module_name):
    namespace = {}
    exec(f'from {module_name} import *', namespace)
    namespace.pop('__builtins__')
    return namespace


class TestExports:
    def test_async_all_is_pinned(self):
        assert server.__all__ == [name for name, _, _ in ASYNC_EXPORTS]

    def test_sync_all_is_pinned(self):
        assert server_sync.__all__ == SYNC_ALL

    @pytest.mark.parametrize('module', [server, server_sync], ids=['async', 'sync'])
    def test_all_is_sorted_and_unique(self, module):
        assert len(set(module.__all__)) == len(module.__all__)
        assert module.__all__ == sorted(module.__all__, key=lambda n: (n[0].islower(), n))

    @pytest.mark.parametrize('module', [server, server_sync], ids=['async', 'sync'])
    def test_star_import_gives_every_name(self, module):
        assert sorted(star_import(module.__name__)) == sorted(module.__all__)

    @pytest.mark.parametrize('name,module,attr', ASYNC_EXPORTS, ids=[e[0] for e in ASYNC_EXPORTS])
    def test_async_export_is_the_internal_object(self, name, module, attr):
        assert getattr(server, name) is getattr(importlib.import_module(module), attr)

    @pytest.mark.parametrize('name,module,attr', SYNC_EXPORTS, ids=[e[0] for e in SYNC_EXPORTS])
    def test_sync_export_is_the_generated_object(self, name, module, attr):
        assert getattr(server_sync, name) is getattr(importlib.import_module(module), attr)

    @pytest.mark.parametrize('name,module,attr', SYNC_EXPORTS, ids=[e[0] for e in SYNC_EXPORTS])
    def test_sync_class_is_named_as_exported(self, name, module, attr):
        obj = getattr(server_sync, name)
        if isinstance(obj, type) and name != 'HttpChannelsSync':
            assert obj.__name__ == name

    def test_every_async_export_has_a_sync_counterpart_or_is_realtime_only(self):
        missing = [
            name for name, _, _ in ASYNC_EXPORTS
            if name not in REALTIME_ONLY and SYNC_NAMES.get(name, name) not in server_sync.__all__
        ]
        assert missing == []
        assert sorted(sync_export(*e)[0] for e in ASYNC_EXPORTS if e[0] not in REALTIME_ONLY) \
            == sorted(server_sync.__all__)

    @pytest.mark.parametrize('name', sorted(REALTIME_ONLY))
    def test_realtime_only_names_are_absent_from_sync(self, name):
        assert name in server.__all__
        assert name not in server_sync.__all__
        assert not hasattr(server_sync, name)

    @pytest.mark.parametrize('name', ['ConnectionDetails', 'MessageAnnotations', 'ErrorInfo', 'ResponseHeaders'])
    def test_deferred_names_are_not_exported(self, name):
        assert name not in server.__all__
        assert name not in server_sync.__all__

    def test_handle_classes_match_what_the_clients_hand_out(self):
        http = create_http_client(key='fake:key')
        channel = http.channels.get('exports')
        assert type(channel) is server.Channel
        assert type(channel.presence) is server.Presence
        assert type(channel.annotations) is server.HttpAnnotations
        assert type(http.push.admin) is server.PushAdmin
        assert type(http.push.admin.device_registrations) is server.PushDeviceRegistrations
        assert type(http.push.admin.channel_subscriptions) is server.PushChannelSubscriptions

        sync_http = server_sync.create_http_client(key='fake:key')
        sync_channel = sync_http.channels.get('exports')
        assert type(sync_channel) is server_sync.ChannelSync
        assert type(sync_channel.presence) is server_sync.PresenceSync
        assert type(sync_channel.annotations) is server_sync.HttpAnnotationsSync
        assert type(sync_http.push.admin) is server_sync.PushAdminSync
        assert type(sync_http.push.admin.device_registrations) is server_sync.PushDeviceRegistrationsSync
        assert type(sync_http.push.admin.channel_subscriptions) is server_sync.PushChannelSubscriptionsSync
        sync_http.close()

    async def test_realtime_handle_classes_match_what_the_client_hands_out(self):
        realtime = create_realtime_client(key='foo:bar', auto_connect=False)
        channel = realtime.channels.get('exports')
        assert type(channel) is server.RealtimeChannel
        assert isinstance(channel, server.Channel)
        assert type(channel.presence) is server.RealtimePresence
        assert type(channel.annotations) is server.RealtimeAnnotations
        assert type(channel.state) is server.ChannelState
        assert type(realtime.connection.state) is server.ConnectionState
        await realtime.close()
