"""Derived from uts/realtime/unit/channels/channel_history.md in ably/specification.

Spec points: RTL10, RTL10a, RTL10b, RTL10c

RTL10a points at uts/rest/unit/channel/history.md (RSL2) rather than listing steps of
its own, so its Test ID becomes one test driving an `AblyRealtime` over the HTTP mock
and asserting the core observable of the derived REST suite.

The two RTL10b tests cover `untilAttach`, which ably-python does not implement; see
[deviations-channels-messages.md](../../../deviations-channels-messages.md).
"""

import uuid

import pytest

from ably.http.paginatedresult import PaginatedResult
from ably.realtime.connection import ConnectionState
from ably.transport.websockettransport import ProtocolMessageAction
from ably.types.channelstate import ChannelState
from ably.util.exceptions import AblyException
from test.uts.helpers.client import await_connection_state, realtime_client
from test.uts.helpers.deviations import deviation
from test.uts.helpers.mock_http import MockHttpClient
from test.uts.helpers.mock_websocket import MockWebSocket, attached_message, connected_message

CONNECTED_MESSAGE = connected_message('connection-id', connectionKey='connection-key')

ATTACH_SERIAL = 'serial-abc:0'


def random_id():
    return uuid.uuid4().hex[:8]


def capture_and_respond(captured_requests, body):
    def on_request(request):
        captured_requests.append(request)
        request.respond_with(200, body)

    return on_request


def attaching_mock(channel_name, channel_serial=None):
    """A mock which connects and confirms the channel's attach."""
    mock_ws = MockWebSocket(
        on_connection_attempt=lambda conn: conn.respond_with_success(CONNECTED_MESSAGE),
    )

    def on_message_from_client(msg):
        if msg.get('action') == ProtocolMessageAction.ATTACH:
            fields = {} if channel_serial is None else {'channelSerial': channel_serial}
            mock_ws.send_to_client(attached_message(channel_name, **fields))

    mock_ws.on_message_from_client = on_message_from_client
    return mock_ws


# UTS: realtime/unit/RTL10a/supports-rest-params-0
async def test_rtl10a_supports_rest_params():
    # The specification directs uts/rest/unit/channel/history.md (RSL2) at a realtime
    # channel in place of a REST one. `AblyRealtime` subclasses `AblyRest`, so the same
    # HTTP mock serves it, and this mirrors that suite's `RSL2a/returns-paginated-result-0`
    # and `RSL2b/query-parameters-0`.
    channel_name = f'test-RTL10a-{random_id()}'
    captured_requests = []

    mock_http = MockHttpClient(
        on_connection_attempt=lambda conn: conn.respond_with_success(),
        on_request=capture_and_respond(captured_requests, [
            {'id': 'msg1', 'name': 'event1', 'data': 'data1', 'timestamp': 1000},
            {'id': 'msg2', 'name': 'event2', 'data': 'data2', 'timestamp': 2000},
        ]),
    )
    # `auto_connect` is left at `realtime_client`'s false, so no websocket is opened
    client = realtime_client(mock_http=mock_http)
    channel = client.channels.get(channel_name)

    # RTL10c: the first page of messages
    result = await channel.history()

    assert isinstance(result, PaginatedResult)
    assert len(result.items) == 2
    assert result.items[0].id == 'msg1'
    assert result.items[0].data == 'data1'

    assert captured_requests[0].url.path == f'/channels/{channel_name}/messages'

    # RTL10a: the parameters `RestChannel#history` takes
    await channel.history(direction='forwards', limit=50, start=1000, end=2000)

    query_params = captured_requests[1].url.query_params
    assert query_params['direction'] == 'forwards'
    assert query_params['limit'] == '50'
    assert query_params['start'] == '1000'
    assert query_params['end'] == '2000'


# UTS: realtime/unit/RTL10b/adds-from-serial-0
@deviation
async def test_rtl10b_adds_from_serial():
    channel_name = f'test-RTL10b-{random_id()}'
    captured_requests = []

    mock_http = MockHttpClient(
        on_connection_attempt=lambda conn: conn.respond_with_success(),
        on_request=capture_and_respond(captured_requests, []),
    )
    mock_ws = attaching_mock(channel_name, channel_serial=ATTACH_SERIAL)
    client = realtime_client(mock_ws, mock_http=mock_http)
    channel = client.channels.get(channel_name)

    client.connect()
    await await_connection_state(client, ConnectionState.CONNECTED)
    await channel.attach()
    assert channel.state == ChannelState.ATTACHED

    await channel.history(until_attach=True)

    assert captured_requests[0].url.query_params['fromSerial'] == ATTACH_SERIAL


# UTS: realtime/unit/RTL10b/errors-when-not-attached-1
async def test_rtl10b_errors_when_not_attached():
    # The specification asks for an error when `untilAttach` is requested on a channel
    # that is not attached. ably-python raises one, but for a different reason: `history`
    # takes no `until_attach` parameter at all, and `catch_all`
    # (`ably/util/exceptions.py:93`) turns the resulting TypeError into an AblyException
    # whatever the channel's state. See the deviations file.
    channel_name = f'test-RTL10b-err-{random_id()}'
    captured_requests = []

    mock_http = MockHttpClient(
        on_connection_attempt=lambda conn: conn.respond_with_success(),
        on_request=capture_and_respond(captured_requests, []),
    )
    mock_ws = attaching_mock(channel_name)
    client = realtime_client(mock_ws, mock_http=mock_http)
    channel = client.channels.get(channel_name)

    client.connect()
    await await_connection_state(client, ConnectionState.CONNECTED)

    assert channel.state == ChannelState.INITIALIZED

    with pytest.raises(AblyException):
        await channel.history(until_attach=True)

    # Nothing was requested: the call failed before it reached the HTTP layer
    assert captured_requests == []
