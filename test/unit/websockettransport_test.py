from unittest.mock import MagicMock, patch

from ably.transport.websockettransport import WebSocketTransport
from ably.types.options import Options


def _connect_url(host='example.com', **option_kwargs):
    connection_manager = MagicMock()
    connection_manager.options = Options(auth_token='foo', **option_kwargs)
    transport = WebSocketTransport(connection_manager, host, {'format': 'json'})
    with patch.object(transport, 'ws_connect', MagicMock()) as mock_ws_connect:
        with patch('ably.transport.websockettransport.asyncio.create_task') as mock_create_task:
            mock_create_task.return_value = MagicMock()
            transport.connect()
    return mock_ws_connect.call_args[0][0]


# TO3d, TO3o
def test_websocket_url_uses_wss_and_tls_port_when_tls_enabled():
    url = _connect_url(tls=True, tls_port=9999)
    assert url == 'wss://example.com:9999?format=json'


# TO3d, TO3n
def test_websocket_url_uses_ws_and_port_when_tls_disabled():
    url = _connect_url(tls=False, port=9998)
    assert url == 'ws://example.com:9998?format=json'


# TO3d, TO3o
def test_websocket_url_defaults_to_wss_and_443():
    url = _connect_url()
    assert url == 'wss://example.com:443?format=json'


# TO3d, TO3n
def test_websocket_url_defaults_to_ws_and_80_when_tls_disabled():
    url = _connect_url(tls=False)
    assert url == 'ws://example.com:80?format=json'
