"""Derived from uts/realtime/unit/channels/channel_message_versions.md in ably/specification.

Spec points: RTL31

The specification points at uts/rest/unit/channel/message_versions.md (RSL14) rather
than listing steps of its own, so its single Test ID becomes one test driving an
`AblyRealtime` over the HTTP mock and asserting the core observable of the derived
REST suite: the endpoint the call reaches and the paginated versions it returns.
"""

import uuid

from ably.http.paginatedresult import PaginatedResult
from ably.types.message import Message, MessageAction
from test.uts.helpers.client import realtime_client
from test.uts.helpers.mock_http import MockHttpClient


def random_id():
    return uuid.uuid4().hex[:8]


# UTS: realtime/unit/RTL31/identical-to-rest-0
async def test_rtl31_identical_to_rest():
    channel_name = f'test-RTL31-{random_id()}'
    captured_requests = []

    def on_request(request):
        captured_requests.append(request)
        request.respond_with(200, [
            {
                'name': 'evt',
                'data': 'v2-data',
                'serial': 'msg-serial-1',
                'action': 1,
                'version': {'serial': 'vs2', 'timestamp': 1700000002000},
            },
            {
                'name': 'evt',
                'data': 'v1-data',
                'serial': 'msg-serial-1',
                'action': 0,
                'version': {'serial': 'vs1', 'timestamp': 1700000001000},
            },
        ])

    mock_http = MockHttpClient(
        on_connection_attempt=lambda conn: conn.respond_with_success(),
        on_request=on_request,
    )
    # `auto_connect` is left at `realtime_client`'s false, so no websocket is opened
    client = realtime_client(mock_http=mock_http)
    channel = client.channels.get(channel_name)

    result = await channel.get_message_versions('msg-serial-1')

    assert len(captured_requests) == 1
    request = captured_requests[0]
    assert request.method == 'GET'
    assert request.url.path == f'/channels/{channel_name}/messages/msg-serial-1/versions'

    assert isinstance(result, PaginatedResult)
    assert len(result.items) == 2
    assert all(isinstance(item, Message) for item in result.items)
    assert result.items[0].action == MessageAction.MESSAGE_UPDATE
    assert result.items[0].version.serial == 'vs2'
    assert result.items[1].action == MessageAction.MESSAGE_CREATE
    assert result.items[1].version.serial == 'vs1'
