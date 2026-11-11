"""The server package declares its side in the Ably-Agent header.

On API-key auth the realtime system exempts a connection from monthly-active-user
counting only when an agent entry ends in `-server`, so every request and connection
a server factory builds must carry `ably-pubsub-server`.
"""

import httpx
import pytest

import ably.pubsub.server.sync as server_sync
from ably.pubsub.realtime.connection import ConnectionState
from ably.pubsub.server import create_http_client
from ably.pubsub.sync.types.testoptions import TestOptions as SyncTestOptions
from ably.pubsub.types.testoptions import TestOptions
from test.uts.helpers.client import await_connection_state, close_open_clients, realtime_client
from test.uts.helpers.mock_http import MockHttpClient
from test.uts.helpers.mock_websocket import CONNECTED_MESSAGE, MockWebSocket

KEY = 'app.key:secret'
TIME_RESPONSE = [1234567890000]


@pytest.fixture(autouse=True)
async def close_clients():
    yield
    await close_open_clients()


def agent_entries(header):
    return header.split(' ')


async def http_agent(**kwargs):
    mock = MockHttpClient(on_connection_attempt=lambda conn: conn.respond_with_success())
    mock.queue_response(200, TIME_RESPONSE)
    client = create_http_client(key=KEY, _test_options=TestOptions(http_transport=mock.as_transport()), **kwargs)
    try:
        await client.time()
    finally:
        await client.close()
    return mock.captured_requests[0].headers['Ably-Agent']


async def test_http_requests_declare_the_server_side():
    agents = agent_entries(await http_agent())
    assert agents[0].startswith('ably-pubsub-python/')
    assert agents[-1] == 'ably-pubsub-server'


async def test_the_realtime_connection_declares_the_server_side():
    mock = MockWebSocket(
        on_connection_attempt=lambda connection: connection.respond_with_success(CONNECTED_MESSAGE))
    client = realtime_client(mock, disconnected_retry_timeout_seconds=60)
    client.connect()
    await await_connection_state(client, ConnectionState.CONNECTED)

    agents = agent_entries(mock.connection_attempts[0].headers['Ably-Agent'])
    assert agents[0].startswith('ably-pubsub-python/')
    assert agents[-1] == 'ably-pubsub-server'


def test_sync_http_requests_declare_the_server_side():
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(200, json=TIME_RESPONSE)

    client = server_sync.create_http_client(
        key=KEY, _test_options=SyncTestOptions(http_transport=httpx.MockTransport(handler)))
    try:
        client.time()
    finally:
        client.close()

    agents = agent_entries(requests[0].headers['Ably-Agent'])
    assert agents[0].startswith('ably-pubsub-python/')
    assert agents[-1] == 'ably-pubsub-server'


async def test_caller_agents_are_kept_alongside_the_server_side():
    caller_agents = {'my-sdk': '1.2.3', 'my-flag': None}

    agents = agent_entries(await http_agent(agents=caller_agents))

    assert 'my-sdk/1.2.3' in agents
    assert 'my-flag' in agents
    assert agents[-1] == 'ably-pubsub-server'
    assert caller_agents == {'my-sdk': '1.2.3', 'my-flag': None}


async def test_a_caller_cannot_redeclare_the_side():
    agents = agent_entries(await http_agent(agents={'ably-pubsub-server': '9.9.9'}))

    assert agents.count('ably-pubsub-server') == 1
    assert 'ably-pubsub-server/9.9.9' not in agents
