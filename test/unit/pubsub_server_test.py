import inspect
import typing

import pytest

import ably.pubsub.server as server
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
