"""Derived from uts/realtime/unit/channels/channel_get_message.md in ably/specification.

Spec points: RTL28

The specification points at uts/rest/unit/channel/get_message.md (RSL11) rather than
listing steps of its own, so its single Test ID becomes one test driving an
`AblyRealtime` over the HTTP mock and asserting the core observable of the derived
REST suite: the endpoint the call reaches and the `Message` it returns.
"""

import uuid

from ably.types.message import Message
from test.uts.helpers.client import realtime_client
from test.uts.helpers.mock_http import MockHttpClient


def random_id():
    return uuid.uuid4().hex[:8]


# UTS: realtime/unit/RTL28/identical-to-rest-0
async def test_rtl28_identical_to_rest():
    channel_name = f'test-RTL28-{random_id()}'
    captured_requests = []

    def on_request(request):
        captured_requests.append(request)
        request.respond_with(200, {
            'name': 'evt',
            'data': 'hello',
            'serial': 'msg-serial-123',
            'timestamp': 1700000000000,
        })

    mock_http = MockHttpClient(
        on_connection_attempt=lambda conn: conn.respond_with_success(),
        on_request=on_request,
    )
    # `auto_connect` is left at `realtime_client`'s false, so no websocket is opened
    client = realtime_client(mock_http=mock_http)
    channel = client.channels.get(channel_name)

    message = await channel.get_message('msg-serial-123')

    assert len(captured_requests) == 1
    request = captured_requests[0]
    assert request.method == 'GET'
    assert request.url.path == f'/channels/{channel_name}/messages/msg-serial-123'
    assert not request.body

    assert isinstance(message, Message)
    assert message.serial == 'msg-serial-123'
    assert message.name == 'evt'
    assert message.data == 'hello'
