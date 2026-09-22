"""Derived from uts/rest/unit/channel/publish_result.md in ably/specification.

Spec points: RSL1n, RSL1n1, PBR1, PBR2a
"""

import uuid

from ably.types.message import Message
from ably.types.operations import PublishResult
from test.uts.helpers.client import rest_client
from test.uts.helpers.mock_http import MockHttpClient


def random_id():
    return uuid.uuid4().hex[:8]


def capture_and_respond(captured_requests, serials):
    def on_request(request):
        captured_requests.append(request)
        request.respond_with(201, {'serials': serials})

    return on_request


# UTS: rest/unit/RSL1n/publish-result-single-message-0
async def test_rsl1n_publish_result_single_message():
    channel_name = f'test-RSL1n-single-{random_id()}'
    captured_requests = []
    mock_http = MockHttpClient(
        on_connection_attempt=lambda conn: conn.respond_with_success(),
        on_request=capture_and_respond(captured_requests, ['serial-abc']),
    )
    client = rest_client(mock_http)
    channel = client.channels.get(channel_name)

    result = await channel.publish(name='event', data='hello')

    assert isinstance(result, PublishResult)
    assert isinstance(result.serials, list)
    assert len(result.serials) == 1
    assert result.serials[0] == 'serial-abc'


# UTS: rest/unit/RSL1n/publish-result-batch-serials-1
async def test_rsl1n_publish_result_batch_serials():
    channel_name = f'test-RSL1n-batch-{random_id()}'
    captured_requests = []
    mock_http = MockHttpClient(
        on_connection_attempt=lambda conn: conn.respond_with_success(),
        on_request=capture_and_respond(captured_requests, ['s1', 's2', 's3']),
    )
    client = rest_client(mock_http)
    channel = client.channels.get(channel_name)

    messages = [
        Message(name='event1', data='data1'),
        Message(name='event2', data='data2'),
        Message(name='event3', data='data3'),
    ]
    result = await channel.publish(messages=messages)

    assert isinstance(result, PublishResult)
    assert len(result.serials) == 3
    assert result.serials[0] == 's1'
    assert result.serials[1] == 's2'
    assert result.serials[2] == 's3'


# UTS: rest/unit/RSL1n/publish-result-null-serial-2
async def test_rsl1n_publish_result_null_serial():
    channel_name = f'test-RSL1n-null-{random_id()}'
    mock_http = MockHttpClient(
        on_connection_attempt=lambda conn: conn.respond_with_success(),
        on_request=lambda request: request.respond_with(201, {'serials': [None, 's2']}),
    )
    client = rest_client(mock_http)
    channel = client.channels.get(channel_name)

    messages = [
        Message(name='event1', data='data1'),
        Message(name='event2', data='data2'),
    ]
    result = await channel.publish(messages=messages)

    assert len(result.serials) == 2
    assert result.serials[0] is None
    assert result.serials[1] == 's2'
