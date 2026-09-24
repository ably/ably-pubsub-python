"""Derived from uts/rest/unit/channel/publish.md in ably/specification.

Spec points: RSL1, RSL1a, RSL1b, RSL1c, RSL1d, RSL1e, RSL1h, RSL1i, RSL1j, RSL1l, RSL1m
"""

import uuid

import msgpack
import pytest

from ably.types.message import Message
from ably.util.exceptions import AblyException
from test.uts.helpers.client import rest_client
from test.uts.helpers.deviations import deviation, spec_error
from test.uts.helpers.mock_http import MockHttpClient


def random_id():
    return uuid.uuid4().hex[:8]


def capture_and_respond(captured_requests, serials):
    def on_request(request):
        captured_requests.append(request)
        request.respond_with(201, {'serials': serials})

    return on_request


def published_messages(request):
    """The messages a publish request carried, in wire form.

    The body is msgpack, as `use_binary_protocol` defaults to True. RSL1b's own
    note allows a single message to travel either as a one-element array or as a
    bare object, and ably-python sends the bare object; both are normalised here
    so the specification's assertions can be made against a list.
    """
    body = msgpack.unpackb(request.body)
    return body if isinstance(body, list) else [body]


# UTS: rest/unit/RSL1a/publish-name-and-data-0
async def test_rsl1a_publish_name_and_data():
    channel_name = f'test-RSL1a-{random_id()}'
    captured_requests = []
    mock_http = MockHttpClient(
        on_connection_attempt=lambda conn: conn.respond_with_success(),
        on_request=capture_and_respond(captured_requests, ['serial1']),
    )
    client = rest_client(mock_http)
    channel = client.channels.get(channel_name)

    await channel.publish(name='greeting', data='hello')

    request = captured_requests[0]

    # RSL1b - single message published
    assert request.method == 'POST'
    assert request.url.path == f'/channels/{channel_name}/messages'

    body = published_messages(request)
    assert isinstance(body, list)
    assert len(body) == 1
    assert body[0]['name'] == 'greeting'
    assert body[0]['data'] == 'hello'


# UTS: rest/unit/RSL1a/publish-message-array-1
# RSL1c asserts that an object payload travels unstringified, which RSL4c3 and RSL4d3
# rule out; see deviations.md.
@spec_error
async def test_rsl1a_publish_message_array():
    channel_name = f'test-RSL1c-{random_id()}'
    captured_requests = []
    request_count = 0

    def on_request(request):
        nonlocal request_count
        captured_requests.append(request)
        request_count += 1
        request.respond_with(201, {'serials': ['s1', 's2', 's3']})

    mock_http = MockHttpClient(
        on_connection_attempt=lambda conn: conn.respond_with_success(),
        on_request=on_request,
    )
    client = rest_client(mock_http)
    channel = client.channels.get(channel_name)

    messages = [
        Message(name='event1', data='data1'),
        Message(name='event2', data={'key': 'value'}),
        Message(name='event3', data=bytes([0x01, 0x02, 0x03])),
    ]
    await channel.publish(messages=messages)

    # RSL1c - single request for array
    assert request_count == 1

    request = captured_requests[0]
    body = published_messages(request)

    assert len(body) == 3
    assert body[0]['name'] == 'event1'
    assert body[0]['data'] == 'data1'
    assert body[1]['name'] == 'event2'
    assert body[1]['data'] == {'key': 'value'}
    # Note: binary data encoding tested separately in encoding tests


# UTS: rest/unit/RSL1e/null-name-and-data-0
async def test_rsl1e_null_name_and_data():
    channel_name = f'test-RSL1e-{random_id()}'
    captured_requests = []
    mock_http = MockHttpClient(
        on_connection_attempt=lambda conn: conn.respond_with_success(),
        on_request=capture_and_respond(captured_requests, ['s1']),
    )
    client = rest_client(mock_http)
    channel = client.channels.get(channel_name)

    test_cases = [
        (None, 'hello', {'data': 'hello'}),
        ('event', None, {'name': 'event'}),
        (None, None, {}),
    ]

    for name, data, expected_body in test_cases:
        captured_requests.clear()

        await channel.publish(name=name, data=data)

        body = published_messages(captured_requests[0])
        # NOTE: the spec asserts body == [expected_body] exactly. RSL1k1 has the library
        # populate an `id` on every message while `idempotentRestPublishing` is enabled,
        # which it is by default, so the transmitted message is a superset of the spec's
        # literal. The spec's own presence assertions below carry the RSL1e requirement.
        assert len(body) == 1
        for key, value in expected_body.items():
            assert body[0][key] == value
        if name is None:
            assert 'name' not in body[0]
        if data is None:
            assert 'data' not in body[0]


# UTS: rest/unit/RSL1h/publish-signature-0
async def test_rsl1h_publish_signature():
    channel_name = f'test-RSL1h-{random_id()}'
    captured_requests = []
    request_count = 0

    def on_request(request):
        nonlocal request_count
        captured_requests.append(request)
        request_count += 1
        request.respond_with(201, {'serials': ['s1']})

    mock_http = MockHttpClient(
        on_connection_attempt=lambda conn: conn.respond_with_success(),
        on_request=on_request,
    )
    client = rest_client(mock_http)
    channel = client.channels.get(channel_name)

    # The API should accept exactly (name, data) with no extras
    await channel.publish('event', 'payload')

    assert request_count == 1
    body = published_messages(captured_requests[0])
    assert body[0]['name'] == 'event'
    assert body[0]['data'] == 'payload'


# UTS: rest/unit/RSL1i/message-size-limit-0
@deviation
async def test_rsl1i_message_size_limit():
    channel_name = f'test-RSL1i-{random_id()}'
    captured_requests = []
    request_count = 0

    def on_request(request):
        nonlocal request_count
        captured_requests.append(request)
        request_count += 1
        request.respond_with(201, {'serials': ['s1']})

    mock_http = MockHttpClient(
        on_connection_attempt=lambda conn: conn.respond_with_success(),
        on_request=on_request,
    )
    client = rest_client(mock_http, max_message_size=1024)
    channel = client.channels.get(channel_name)

    test_cases = [
        (1000, True),
        (1024, True),
        (1025, False),
        (10000, False),
    ]

    for size, expect_success in test_cases:
        captured_requests.clear()
        request_count = 0

        large_data = 'x' * size

        if expect_success:
            await channel.publish(name='event', data=large_data)
            assert request_count == 1
        else:
            with pytest.raises(AblyException) as excinfo:
                await channel.publish(name='event', data=large_data)
            assert excinfo.value.code == 40009
            assert request_count == 0  # Request never sent


# UTS: rest/unit/RSL1j/all-attributes-transmitted-0
async def test_rsl1j_all_attributes_transmitted():
    channel_name = f'test-RSL1j-{random_id()}'
    captured_requests = []
    mock_http = MockHttpClient(
        on_connection_attempt=lambda conn: conn.respond_with_success(),
        on_request=capture_and_respond(captured_requests, ['s1']),
    )
    client = rest_client(mock_http)
    channel = client.channels.get(channel_name)

    message = Message(
        name='test-event',
        data='test-data',
        client_id='explicit-client-id',  # RSL1m tests cover whether this should be sent
        id='custom-message-id',
        extras={'push': {'notification': {'title': 'Test'}}},
    )

    await channel.publish(message)

    body = published_messages(captured_requests[0])[0]

    assert body['name'] == 'test-event'
    assert body['data'] == 'test-data'
    assert body['id'] == 'custom-message-id'
    assert body['extras']['push']['notification']['title'] == 'Test'
    # clientId handling is tested separately in RSL1m tests


# UTS: rest/unit/RSL1l/params-as-querystring-0
async def test_rsl1l_params_as_querystring():
    channel_name = f'test-RSL1l-{random_id()}'
    captured_requests = []
    mock_http = MockHttpClient(
        on_connection_attempt=lambda conn: conn.respond_with_success(),
        on_request=capture_and_respond(captured_requests, ['s1']),
    )
    client = rest_client(mock_http)
    channel = client.channels.get(channel_name)

    params = {
        'customParam': 'customValue',
        'anotherParam': '123',
    }

    # The message is positional, as publish() binds its first argument positionally
    await channel.publish(Message(name='event', data='data'), params=params)

    request = captured_requests[0]

    assert request.url.path == f'/channels/{channel_name}/messages'
    assert request.url.query_params['customParam'] == 'customValue'
    assert request.url.query_params['anotherParam'] == '123'


# UTS: rest/unit/RSL1m/clientid-not-injected-0
async def test_rsl1m_clientid_not_injected():
    channel_name_m1 = f'test-RSL1m1-{random_id()}'
    channel_name_m2 = f'test-RSL1m2-{random_id()}'
    channel_name_m3 = f'test-RSL1m3-{random_id()}'

    captured_requests = []
    mock_http = MockHttpClient(
        on_connection_attempt=lambda conn: conn.respond_with_success(),
        on_request=capture_and_respond(captured_requests, ['s1']),
    )

    # RSL1m1 - Message with no clientId
    client_with_id = rest_client(mock_http, client_id='lib-client')
    await client_with_id.channels.get(channel_name_m1).publish(name='e', data='d')

    body = published_messages(captured_requests[0])[0]
    assert 'clientId' not in body  # Library should not inject its clientId

    # RSL1m2 - Message clientId matches library
    captured_requests.clear()

    await client_with_id.channels.get(channel_name_m2).publish(
        Message(name='e', data='d', client_id='lib-client'))

    body = published_messages(captured_requests[0])[0]
    assert body['clientId'] == 'lib-client'  # Explicit clientId preserved

    # RSL1m3 - Unidentified client with message clientId
    captured_requests.clear()

    client_no_id = rest_client(mock_http)
    await client_no_id.channels.get(channel_name_m3).publish(
        Message(name='e', data='d', client_id='msg-client'))

    body = published_messages(captured_requests[0])[0]
    assert body['clientId'] == 'msg-client'
