"""Derived from uts/rest/unit/channel/get_message.md in ably/specification.

Spec points: RSL11, RSL11a, RSL11a1, RSL11b, RSL11c
"""

import uuid

import pytest

from ably.types.message import Message
from ably.util.exceptions import AblyException
from test.uts.helpers.client import rest_client
from test.uts.helpers.mock_http import MockHttpClient


def random_id():
    return uuid.uuid4().hex[:8]


def wire_path(request):
    """The request path as it went on the wire, percent-encoding intact.

    `request.url.path` is percent-decoded by the URL type the mock records, so
    `%2F` reads back as `/` and the encoding the specification asserts on is no
    longer visible there. The encoded form survives in the full URL.
    """
    without_scheme = str(request.url).split('://', 1)[-1]
    path = without_scheme[without_scheme.index('/'):]
    return path.split('?', 1)[0]


# UTS: rest/unit/RSL11b/get-correct-endpoint-0
async def test_rsl11b_get_correct_endpoint():
    channel_name = f'test-RSL11b-{random_id()}'
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
    client = rest_client(mock_http)
    channel = client.channels.get(channel_name)

    await channel.get_message('msg-serial-123')

    assert len(captured_requests) == 1

    request = captured_requests[0]
    assert request.method == 'GET'
    assert request.url.path == f'/channels/{channel_name}/messages/msg-serial-123'
    assert not request.body


# UTS: rest/unit/RSL11c/returns-decoded-message-0
async def test_rsl11c_returns_decoded_message():
    channel_name = f'test-RSL11c-{random_id()}'

    def on_request(request):
        request.respond_with(200, {
            'id': 'msg-id-1',
            'name': 'test-event',
            'data': 'hello world',
            'serial': 'serial-xyz',
            'clientId': 'client-1',
            'timestamp': 1700000000000,
            'extras': {'push': {'notification': {'title': 'Test'}}},
            'version': {
                'serial': 'version-serial-1',
                'timestamp': 1700000000000,
                'clientId': 'client-1',
            },
        })

    mock_http = MockHttpClient(
        on_connection_attempt=lambda conn: conn.respond_with_success(),
        on_request=on_request,
    )
    client = rest_client(mock_http)
    channel = client.channels.get(channel_name)

    msg = await channel.get_message('serial-xyz')

    assert isinstance(msg, Message)
    assert msg.id == 'msg-id-1'
    assert msg.name == 'test-event'
    assert msg.data == 'hello world'
    assert msg.serial == 'serial-xyz'
    assert msg.client_id == 'client-1'
    assert msg.timestamp == 1700000000000
    assert msg.version.serial == 'version-serial-1'


# UTS: rest/unit/RSL11b/url-encodes-serial-1
async def test_rsl11b_url_encodes_serial():
    channel_name = f'test-RSL11b-encode-{random_id()}'
    captured_requests = []
    serial_with_special_chars = 'serial/with:special+chars'

    def on_request(request):
        captured_requests.append(request)
        request.respond_with(200, {
            'name': 'evt',
            'data': 'hello',
            'serial': serial_with_special_chars,
        })

    mock_http = MockHttpClient(
        on_connection_attempt=lambda conn: conn.respond_with_success(),
        on_request=on_request,
    )
    client = rest_client(mock_http)
    channel = client.channels.get(channel_name)

    await channel.get_message(serial_with_special_chars)

    request = captured_requests[0]
    # DEVIATION RSL11b: the spec asserts the serial is encoded as encodeURIComponent
    # would, giving "serial%2Fwith%3Aspecial%2Bchars". ably-python encodes the serial
    # with `quote_plus(serial, safe=':')`, so the colon travels literally. A colon is a
    # legal path character, so the server still receives the same serial; the slash and
    # the plus, which would otherwise change the serial, are both encoded.
    assert wire_path(request) == (
        f'/channels/{channel_name}/messages/serial%2Fwith:special%2Bchars')


# UTS: rest/unit/RSL11a/missing-serial-error-0
async def test_rsl11a_missing_serial_error():
    channel_name = f'test-RSL11a-error-{random_id()}'

    mock_http = MockHttpClient(
        on_connection_attempt=lambda conn: conn.respond_with_success(),
        on_request=lambda request: request.respond_with(200, {}),
    )
    client = rest_client(mock_http)
    channel = client.channels.get(channel_name)

    # Empty string serial
    with pytest.raises(AblyException) as excinfo:
        await channel.get_message('')

    assert excinfo.value.code == 40003
