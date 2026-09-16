"""Derived from uts/rest/unit/channel/idempotency.md in ably/specification.

Spec points: RSL1k, RSL1k1, RSL1k2, RSL1k3
"""

import re
import uuid

import msgpack

from ably.types.message import Message
from test.uts.helpers.client import rest_client
from test.uts.helpers.mock_http import MockHttpClient

# The library's base id is base64 of 12 random bytes, so 16 characters of the standard
# alphabet. The alphabet contains no ":", so splitting an id on ":" always yields two parts.
BASE_ID_PATTERN = re.compile(r'[A-Za-z0-9+/]+={0,2}')


def random_id():
    return uuid.uuid4().hex[:8]


def capture_and_respond(captured_requests, serials):
    def on_request(request):
        captured_requests.append(request)
        request.respond_with(201, {'serials': serials})

    return on_request


def published_messages(request):
    """The messages a publish request carried, in wire form.

    The body is msgpack, as `use_binary_protocol` defaults to True. RSL1b allows a single
    message to travel either as a one-element array or as a bare object, and ably-python
    sends the bare object; both are normalised here so the spec's assertions can be made
    against a list.
    """
    body = msgpack.unpackb(request.body)
    return body if isinstance(body, list) else [body]


# UTS: rest/unit/RSL1k1/idempotent-default-true-0
async def test_rsl1k1_idempotent_default_true():
    mock_http = MockHttpClient(
        on_connection_attempt=lambda conn: conn.respond_with_success(),
        on_request=lambda request: request.respond_with(201, {'serials': ['s1']}),
    )
    client = rest_client(mock_http)

    # Verify default value: the library's API version is >= 1.2
    assert client.options.idempotent_rest_publishing is True


# UTS: rest/unit/RSL1k2/message-id-format-0
async def test_rsl1k2_message_id_format():
    channel_name = f'test-RSL1k2-{random_id()}'
    captured_requests = []
    mock_http = MockHttpClient(
        on_connection_attempt=lambda conn: conn.respond_with_success(),
        on_request=capture_and_respond(captured_requests, ['s1']),
    )
    client = rest_client(mock_http, idempotent_rest_publishing=True)
    channel = client.channels.get(channel_name)

    await channel.publish(name='event', data='data')

    request = captured_requests[0]
    body = published_messages(request)[0]

    assert 'id' in body
    message_id = body['id']

    # Format: <base64>:<serial>
    parts = message_id.split(':')
    assert len(parts) == 2

    # UTS SPEC ERROR: RSL1k2 - the spec requires the base to match "[A-Za-z0-9_-]+", i.e.
    # URL-safe base64, but RSL1k1 in the features spec only asks for "a base id string by
    # base64-encoding a sequence of at least 9 bytes"; ably-python uses the standard
    # alphabet, so a base id may contain "+" or "/". Asserting plain base64.
    assert BASE_ID_PATTERN.fullmatch(parts[0])
    assert len(parts[0]) >= 12  # At least 9 bytes base64 encoded

    # Second part is a serial number (starting from 0)
    assert parts[1] == '0'


# UTS: rest/unit/RSL1k2/serial-increments-batch-1
async def test_rsl1k2_serial_increments_batch():
    channel_name = f'test-RSL1k2-batch-{random_id()}'
    captured_requests = []
    mock_http = MockHttpClient(
        on_connection_attempt=lambda conn: conn.respond_with_success(),
        on_request=capture_and_respond(captured_requests, ['s1', 's2', 's3']),
    )
    client = rest_client(mock_http, idempotent_rest_publishing=True)
    channel = client.channels.get(channel_name)

    messages = [
        Message(name='event1', data='data1'),
        Message(name='event2', data='data2'),
        Message(name='event3', data='data3'),
    ]
    await channel.publish(messages=messages)

    request = captured_requests[0]
    body = published_messages(request)

    # All messages should share the same base but different serials
    base_ids = []
    serials = []

    for msg in body:
        parts = msg['id'].split(':')
        base_ids.append(parts[0])
        serials.append(int(parts[1]))

    # Same base for all messages in batch
    assert all(base == base_ids[0] for base in base_ids)

    # Sequential serials starting from 0
    assert serials == [0, 1, 2]


# UTS: rest/unit/RSL1k3/unique-base-ids-0
async def test_rsl1k3_unique_base_ids():
    channel_name = f'test-RSL1k3-{random_id()}'
    captured_requests = []
    mock_http = MockHttpClient(
        on_connection_attempt=lambda conn: conn.respond_with_success(),
        on_request=capture_and_respond(captured_requests, ['s1']),
    )
    client = rest_client(mock_http, idempotent_rest_publishing=True)
    channel = client.channels.get(channel_name)

    await channel.publish(name='event1', data='data1')
    await channel.publish(name='event2', data='data2')

    body1 = published_messages(captured_requests[0])[0]
    body2 = published_messages(captured_requests[1])[0]

    base1 = body1['id'].split(':')[0]
    base2 = body2['id'].split(':')[0]

    # Different publish calls should have different base IDs
    assert base1 != base2


# UTS: rest/unit/RSL1k3/no-id-when-disabled-1
async def test_rsl1k3_no_id_when_disabled():
    channel_name = f'test-RSL1k3-disabled-{random_id()}'
    captured_requests = []
    mock_http = MockHttpClient(
        on_connection_attempt=lambda conn: conn.respond_with_success(),
        on_request=capture_and_respond(captured_requests, ['s1']),
    )
    client = rest_client(mock_http, idempotent_rest_publishing=False)
    channel = client.channels.get(channel_name)

    await channel.publish(name='event', data='data')

    request = captured_requests[0]
    body = published_messages(request)[0]

    # No automatic ID should be added
    assert 'id' not in body


# UTS: rest/unit/RSL1k/client-id-preserved-0
async def test_rsl1k_client_id_preserved():
    channel_name = f'test-RSL1k-preserved-{random_id()}'
    captured_requests = []
    mock_http = MockHttpClient(
        on_connection_attempt=lambda conn: conn.respond_with_success(),
        on_request=capture_and_respond(captured_requests, ['s1']),
    )
    # Even with idempotent publishing enabled
    client = rest_client(mock_http, idempotent_rest_publishing=True)
    channel = client.channels.get(channel_name)

    await channel.publish(Message(id='my-custom-id', name='event', data='data'))

    request = captured_requests[0]
    body = published_messages(request)[0]

    # Client-supplied ID should be preserved exactly
    assert body['id'] == 'my-custom-id'


# UTS: rest/unit/RSL1k2/same-id-on-retry-2
async def test_rsl1k2_same_id_on_retry():
    channel_name = f'test-RSL1k2-retry-{random_id()}'
    captured_requests = []
    request_count = 0

    def on_request(request):
        nonlocal request_count
        captured_requests.append(request)
        request_count += 1

        # First request fails with retryable error
        if request_count == 1:
            request.respond_with(500, {'error': {'code': 50000}})
        else:
            # Retry succeeds
            request.respond_with(201, {'serials': ['s1']})

    mock_http = MockHttpClient(
        on_connection_attempt=lambda conn: conn.respond_with_success(),
        on_request=on_request,
    )
    client = rest_client(mock_http, idempotent_rest_publishing=True)
    channel = client.channels.get(channel_name)

    await channel.publish(name='event', data='data')

    assert request_count == 2

    body1 = published_messages(captured_requests[0])[0]
    body2 = published_messages(captured_requests[1])[0]

    # Same ID should be used for retry
    assert body1['id'] == body2['id']


# UTS: rest/unit/RSL1k/mixed-ids-in-batch-1
async def test_rsl1k_mixed_ids_in_batch():
    channel_name = f'test-RSL1k-mixed-{random_id()}'
    captured_requests = []
    mock_http = MockHttpClient(
        on_connection_attempt=lambda conn: conn.respond_with_success(),
        on_request=capture_and_respond(captured_requests, ['s1', 's2', 's3']),
    )
    client = rest_client(mock_http, idempotent_rest_publishing=True)
    channel = client.channels.get(channel_name)

    messages = [
        Message(id='client-id-1', name='event1', data='data1'),
        Message(name='event2', data='data2'),  # No ID
        Message(id='client-id-2', name='event3', data='data3'),
    ]
    await channel.publish(messages=messages)

    request = captured_requests[0]
    body = published_messages(request)

    # Client IDs preserved
    assert body[0]['id'] == 'client-id-1'
    assert body[2]['id'] == 'client-id-2'

    # UTS SPEC ERROR: RSL1k - the spec expects the middle message to receive a
    # library-generated "<base>:<serial>" id. RSL1k1 generates ids only when every message
    # has an empty id, and RSL1k3 in the features spec says that where any message in a
    # batch carries an id, "all message ids (present or absent) are preserved"; so an absent
    # id must stay absent. Asserting what the features spec requires.
    assert 'id' not in body[1]
