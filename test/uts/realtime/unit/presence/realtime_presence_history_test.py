"""Derived from uts/realtime/unit/presence/realtime_presence_history.md in ably/specification.

Spec points: RTP12, RTP12a, RTP12c, RTP12d

The specification points `RealtimePresence#history` at `RestPresence#history`, so each
test here drives a realtime client whose HTTP layer is a `MockHttpClient` and asserts the
same observables as the derived REST tests in
`test/uts/rest/unit/presence/rest_presence_test.py`. The websocket mock is still needed
for the channel setup the specification asks for.

`RealtimePresence` has no `history` at all, so both tests are gated; see
test/uts/deviations-presence-rest.md.
"""

import uuid

from ably.http.paginatedresult import PaginatedResult
from ably.realtime.connection import ConnectionState
from ably.transport.websockettransport import ProtocolMessageAction
from ably.types.presence import PresenceAction, PresenceMessage
from test.uts.helpers.client import await_connection_state, realtime_client
from test.uts.helpers.deviations import deviation
from test.uts.helpers.mock_http import MockHttpClient
from test.uts.helpers.mock_websocket import MockWebSocket, attached_message, connected_message

CONNECTED_MESSAGE = connected_message('conn-1', connectionKey='connection-key')


def random_id():
    return uuid.uuid4().hex[:8]


def attaching_server(mock_ws, channel_name):
    """Answers each ATTACH with an ATTACHED."""
    def on_message_from_client(msg):
        if msg['action'] == ProtocolMessageAction.ATTACH:
            mock_ws.send_to_client(attached_message(channel_name))

    mock_ws.on_message_from_client = on_message_from_client
    return mock_ws


def capturing_mock(captured_requests, body=None):
    """A mock serving every HTTP request with the same response."""
    def on_request(request):
        captured_requests.append(request)
        request.respond_with(200, [] if body is None else body)

    return MockHttpClient(
        on_connection_attempt=lambda conn: conn.respond_with_success(),
        on_request=on_request,
    )


async def attached_channel(mock_ws, mock_http, channel_name):
    """A channel attached over `mock_ws`, on a client whose REST calls `mock_http` serves."""
    client = realtime_client(mock_ws, mock_http=mock_http)
    client.connect()
    await await_connection_state(client, ConnectionState.CONNECTED)
    channel = client.channels.get(channel_name)
    await channel.attach()
    return channel


# UTS: realtime/unit/RTP12a/history-supports-rest-params-0
@deviation
async def test_rtp12a_history_supports_rest_params():
    channel_name = f'test-RTP12a-{random_id()}'
    captured_requests = []

    mock_ws = MockWebSocket(
        on_connection_attempt=lambda conn: conn.respond_with_success(CONNECTED_MESSAGE),
    )
    attaching_server(mock_ws, channel_name)
    mock_http = capturing_mock(captured_requests)

    channel = await attached_channel(mock_ws, mock_http, channel_name)

    await channel.presence.history(start=1000, end=2000, direction='backwards', limit=50)

    assert len(captured_requests) == 1
    assert captured_requests[0].url.path == f'/channels/{channel_name}/presence/history'
    query_params = captured_requests[0].url.query_params
    assert query_params['start'] == '1000'
    assert query_params['end'] == '2000'
    assert query_params['direction'] == 'backwards'
    assert query_params['limit'] == '50'


# UTS: realtime/unit/RTP12c/history-returns-paginated-result-0
@deviation
async def test_rtp12c_history_returns_paginated_result():
    channel_name = f'test-RTP12c-{random_id()}'
    captured_requests = []

    mock_ws = MockWebSocket(
        on_connection_attempt=lambda conn: conn.respond_with_success(CONNECTED_MESSAGE),
    )
    attaching_server(mock_ws, channel_name)
    # The REST layer reads the numeric wire actions: ENTER is 2, UPDATE 4, LEAVE 3
    mock_http = capturing_mock(captured_requests, [
        {'action': 2, 'clientId': 'alice', 'timestamp': 1000},
        {'action': 4, 'clientId': 'alice', 'timestamp': 2000},
        {'action': 3, 'clientId': 'alice', 'timestamp': 3000},
    ])

    channel = await attached_channel(mock_ws, mock_http, channel_name)

    result = await channel.presence.history()

    assert isinstance(result, PaginatedResult)
    assert len(result.items) == 3
    assert all(isinstance(item, PresenceMessage) for item in result.items)
    assert result.items[0].client_id == 'alice'
    assert result.items[0].action == PresenceAction.ENTER
    assert result.items[2].action == PresenceAction.LEAVE
