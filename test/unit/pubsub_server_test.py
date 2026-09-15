import pytest

import ably.pubsub.server as server
import ably.pubsub.server.sync as server_sync
from ably.pubsub.prototypes import RealtimeClient, RestClient
from ably.pubsub.realtime.realtime import AblyRealtime
from ably.pubsub.rest.rest import AblyRest
from ably.pubsub.server import create_http_client, create_realtime_client
from ably.pubsub.sync.rest.rest import AblyRestSync


def protocol_members(protocol):
    # Protocol records its declared members here; fall back to the class body
    # on interpreters that do not expose it.
    return getattr(protocol, '__protocol_attrs__', None) or {
        name for name in vars(protocol) if not name.startswith('_abc_') and name != '_is_protocol'
    }


class TestFactories:
    def test_http_factory_returns_a_client(self):
        client = create_http_client(token='foo')
        assert isinstance(client, AblyRest)

    async def test_realtime_factory_returns_a_client(self):
        client = create_realtime_client(key='foo:bar', auto_connect=False)
        assert isinstance(client, AblyRealtime)
        await client.close()

    def test_sync_http_factory_returns_a_client(self):
        assert isinstance(server_sync.create_http_client(token='foo'), AblyRestSync)

    def test_factory_passes_options_through(self):
        client = create_http_client(token='foo', client_id='me')
        assert client.client_id == 'me'


class TestConstructorsAreInternal:
    def test_rest_constructor_is_rejected(self):
        with pytest.raises(TypeError) as excinfo:
            AblyRest(token='foo')
        assert 'ably.pubsub.server.create_http_client' in str(excinfo.value)

    def test_realtime_constructor_is_rejected(self):
        with pytest.raises(TypeError) as excinfo:
            AblyRealtime(key='foo:bar', auto_connect=False)
        assert 'ably.pubsub.server.create_realtime_client' in str(excinfo.value)

    def test_sync_rest_constructor_is_rejected(self):
        with pytest.raises(TypeError) as excinfo:
            AblyRestSync(token='foo')
        assert 'ably.pubsub.server.sync.create_http_client' in str(excinfo.value)

    def test_permission_does_not_leak_past_the_factory(self):
        create_http_client(token='foo')
        with pytest.raises(TypeError):
            AblyRest(token='foo')

    @pytest.mark.parametrize('name', ['AblyRest', 'AblyRealtime'])
    def test_client_classes_are_not_exported(self, name):
        assert not hasattr(server, name)
        assert name not in server.__all__

    def test_sync_client_class_is_not_exported(self):
        assert not hasattr(server_sync, 'AblyRestSync')
        assert 'AblyRestSync' not in server_sync.__all__


class TestPrototypes:
    @pytest.mark.parametrize('protocol,cls', [(RestClient, AblyRest), (RealtimeClient, AblyRealtime)])
    def test_client_satisfies_its_prototype(self, protocol, cls):
        missing = sorted(member for member in protocol_members(protocol) if not hasattr(cls, member))
        assert missing == []

    @pytest.mark.parametrize('name', ['RestClient', 'RealtimeClient'])
    def test_prototypes_are_exported(self, name):
        assert name in server.__all__

    def test_sync_prototype_is_exported(self):
        assert 'RestClient' in server_sync.__all__
