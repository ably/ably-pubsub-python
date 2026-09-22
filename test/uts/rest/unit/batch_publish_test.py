"""Derived from uts/rest/unit/batch_publish.md in ably/specification.

Spec points: RSC22c, RSC22d, BSP2a, BSP2b, BPR2a, BPR2b, BPR2c, BPF2a, BPF2b

NOTE: ably-python has no batch API. `AblyRest` exposes no `batch_publish`, and the package
defines neither `BatchPublishSpec` nor `BatchResult`/`BatchPublishSuccessResult`/
`BatchPublishFailureResult`; the word "batch" appears nowhere under `ably/`. Every test in
this file therefore departs from the specification and is gated behind `RUN_DEVIATIONS`.
Each carries the assertion the spec calls for, written against the name ably-python would
use once RSC22 is implemented, so that dropping the `@deviation` marker is the only change
needed when it is. Today a batch publish has to be hand-rolled by the caller through
`client.request('POST', '/messages', version=..., body=...)`, which does no spec
construction, no RSL4 message encoding and no RSL1k1 idempotent ID generation.

Because `BatchPublishSpec` does not exist to construct, a spec is written as a mapping of
the BSP2 attributes. Results are read by attribute, as the spec writes them, and a success
result is told apart from a failure result by which attributes it carries rather than by
`isinstance`, since neither class exists to name.
"""

import uuid

import msgpack
import pytest

from ably.types.message import Message
from ably.util.exceptions import AblyException
from test.uts.helpers.client import rest_client
from test.uts.helpers.deviations import deviation
from test.uts.helpers.mock_http import MockHttpClient


def random_id():
    return uuid.uuid4().hex[:8]


def capture_and_respond(captured_requests, status=201, body=None):
    def on_request(request):
        captured_requests.append(request)
        request.respond_with(status, body if body is not None else [])

    return on_request


def respond_with(status, body):
    return lambda request: request.respond_with(status, body)


def success_result(channel, message_id='msg', serials=('s1',)):
    return {'channel': channel, 'messageId': message_id, 'serials': list(serials)}


# UTS: rest/unit/RSC22c/single-spec-post-messages-0
@deviation
async def test_rsc22c_batch_publish_single_spec_post_messages():
    channel_name_1 = f'test-RSC22c1-a-{random_id()}'
    channel_name_2 = f'test-RSC22c1-b-{random_id()}'

    captured_requests = []
    mock_http = MockHttpClient(
        on_connection_attempt=lambda conn: conn.respond_with_success(),
        on_request=capture_and_respond(captured_requests),
    )
    client = rest_client(mock_http)

    await client.batch_publish({
        'channels': [channel_name_1, channel_name_2],
        'messages': [Message(name='event', data='hello')],
    })

    assert len(captured_requests) == 1
    request = captured_requests[0]
    assert request.method == 'POST'
    assert request.path == '/messages'

    body = msgpack.unpackb(request.body)
    assert body['channels'] == [channel_name_1, channel_name_2]
    assert len(body['messages']) == 1
    assert body['messages'][0]['name'] == 'event'
    assert body['messages'][0]['data'] == 'hello'


# UTS: rest/unit/RSC22c/array-specs-post-messages-0
@deviation
async def test_rsc22c_batch_publish_array_specs_post_messages():
    channel_name_1 = f'test-RSC22c2-a-{random_id()}'
    channel_name_2 = f'test-RSC22c2-b-{random_id()}'

    captured_requests = []
    mock_http = MockHttpClient(
        on_connection_attempt=lambda conn: conn.respond_with_success(),
        on_request=capture_and_respond(captured_requests),
    )
    client = rest_client(mock_http)

    await client.batch_publish([
        {'channels': [channel_name_1], 'messages': [Message(name='e1', data='d1')]},
        {'channels': [channel_name_2], 'messages': [Message(name='e2', data='d2')]},
    ])

    assert len(captured_requests) == 1
    request = captured_requests[0]
    assert request.method == 'POST'
    assert request.path == '/messages'

    body = msgpack.unpackb(request.body)
    assert isinstance(body, list)
    assert len(body) == 2
    assert body[0]['channels'] == [channel_name_1]
    assert body[0]['messages'][0]['name'] == 'e1'
    assert body[1]['channels'] == [channel_name_2]
    assert body[1]['messages'][0]['name'] == 'e2'


# UTS: rest/unit/RSC22c/single-spec-single-result-0
@deviation
async def test_rsc22c_batch_publish_single_spec_single_result():
    channel_name = f'test-RSC22c3-{random_id()}'

    # UTS SPEC ERROR: RSC22c3 - the mock body is a bare result object, but RSC22b says the REST
    # response "will still be an array", from which the single-spec overload extracts one element.
    response_body = [{'channel': channel_name, 'messageId': 'msg123', 'serials': ['serial1']}]

    mock_http = MockHttpClient(
        on_connection_attempt=lambda conn: conn.respond_with_success(),
        on_request=respond_with(201, response_body),
    )
    client = rest_client(mock_http)

    result = await client.batch_publish({
        'channels': [channel_name],
        'messages': [Message(name='event', data='hello')],
    })

    assert not isinstance(result, list)
    assert len(result.results) == 1
    assert result.results[0].channel == channel_name
    assert result.results[0].message_id == 'msg123'


# UTS: rest/unit/RSC22c/array-specs-array-results-0
@deviation
async def test_rsc22c_batch_publish_array_specs_array_results():
    channel_name_1 = f'test-RSC22c4-a-{random_id()}'
    channel_name_2 = f'test-RSC22c4-b-{random_id()}'

    response_body = [
        success_result(channel_name_1, 'msg1', ['s1']),
        success_result(channel_name_2, 'msg2', ['s2']),
    ]

    mock_http = MockHttpClient(
        on_connection_attempt=lambda conn: conn.respond_with_success(),
        on_request=respond_with(201, response_body),
    )
    client = rest_client(mock_http)

    results = await client.batch_publish([
        {'channels': [channel_name_1], 'messages': [Message(name='e1', data='d1')]},
        {'channels': [channel_name_2], 'messages': [Message(name='e2', data='d2')]},
    ])

    assert isinstance(results, list)
    assert len(results) == 2
    assert results[0].results[0].channel == channel_name_1
    assert results[1].results[0].channel == channel_name_2


# UTS: rest/unit/RSC22c/multiple-channels-multiple-results-0
@deviation
async def test_rsc22c_batch_publish_multiple_channels_multiple_results():
    channel_name_1 = f'test-RSC22c5-a-{random_id()}'
    channel_name_2 = f'test-RSC22c5-b-{random_id()}'
    channel_name_3 = f'test-RSC22c5-c-{random_id()}'

    response_body = [
        success_result(channel_name_1, 'msg1', ['s1']),
        success_result(channel_name_2, 'msg2', ['s2']),
        success_result(channel_name_3, 'msg3', ['s3']),
    ]

    mock_http = MockHttpClient(
        on_connection_attempt=lambda conn: conn.respond_with_success(),
        on_request=respond_with(201, response_body),
    )
    client = rest_client(mock_http)

    result = await client.batch_publish({
        'channels': [channel_name_1, channel_name_2, channel_name_3],
        'messages': [Message(name='event', data='hello')],
    })

    assert len(result.results) == 3
    assert [entry.channel for entry in result.results] == [channel_name_1, channel_name_2, channel_name_3]


# UTS: rest/unit/RSC22c/messages-encoded-per-rsl4-0
@deviation
async def test_rsc22c_batch_publish_messages_encoded_per_rsl4():
    channel_name = f'test-RSC22c6-{random_id()}'

    captured_requests = []
    mock_http = MockHttpClient(
        on_connection_attempt=lambda conn: conn.respond_with_success(),
        on_request=capture_and_respond(captured_requests),
    )
    client = rest_client(mock_http)

    await client.batch_publish({
        'channels': [channel_name],
        'messages': [
            Message(name='string', data='plain text'),
            Message(name='binary', data=b'\x01\x02\x03'),
            Message(name='json', data={'key': 'value'}),
        ],
    })

    assert len(captured_requests) == 1
    messages = msgpack.unpackb(captured_requests[0].body)['messages']

    assert messages[0]['data'] == 'plain text'
    assert 'encoding' not in messages[0] or messages[0]['encoding'] is None

    # UTS SPEC ERROR: RSC22c6 - base64/"encoding: base64" is the JSON-protocol rule (RSL4d1). The
    # spec never sets useBinaryProtocol=false, and TO3f defaults it true, so RSL4c1 applies: a
    # binary payload goes on the wire as a MessagePack binary with no encoding attribute.
    assert messages[1]['data'] == b'\x01\x02\x03'
    assert 'encoding' not in messages[1] or messages[1]['encoding'] is None

    # RSL4c3: a JSON payload is stringified and the encoding attribute is set to "json"
    assert messages[2]['data'] == '{"key":"value"}'
    assert messages[2]['encoding'] == 'json'


# UTS: rest/unit/RSC22c/uses-configured-auth-0
@deviation
async def test_rsc22c_batch_publish_uses_configured_auth():
    channel_name = f'test-RSC22c7-{random_id()}'

    captured_requests = []
    mock_http = MockHttpClient(
        on_connection_attempt=lambda conn: conn.respond_with_success(),
        on_request=capture_and_respond(captured_requests),
    )
    token_client = rest_client(mock_http, token='fake-token')

    await token_client.batch_publish({
        'channels': [channel_name],
        'messages': [Message(name='event', data='hello')],
    })

    assert len(captured_requests) == 1
    assert captured_requests[0].headers['Authorization'].startswith('Bearer ')

    basic_channel_name = f'test-RSC22c7-basic-{random_id()}'

    basic_requests = []
    mock_http.on_request = capture_and_respond(basic_requests)
    basic_client = rest_client(mock_http)

    await basic_client.batch_publish({
        'channels': [basic_channel_name],
        'messages': [Message(name='event', data='hello')],
    })

    assert len(basic_requests) == 1
    assert basic_requests[0].headers['Authorization'].startswith('Basic ')


# UTS: rest/unit/RSC22d/idempotent-ids-generated-0
@deviation
async def test_rsc22d_batch_publish_idempotent_ids_generated():
    captured_requests = []
    mock_http = MockHttpClient(
        on_connection_attempt=lambda conn: conn.respond_with_success(),
        on_request=capture_and_respond(captured_requests),
    )
    client = rest_client(mock_http, idempotent_rest_publishing=True)

    await client.batch_publish([
        {
            'channels': [f'test-RSC22d-a-{random_id()}'],
            'messages': [Message(name='e1', data='d1'), Message(name='e2', data='d2')],
        },
        {
            'channels': [f'test-RSC22d-b-{random_id()}'],
            'messages': [Message(name='e3', data='d3'), Message(name='e4', data='d4')],
        },
    ])

    assert len(captured_requests) == 1
    specs = msgpack.unpackb(captured_requests[0].body)

    base_ids = []
    for spec in specs:
        ids = [message['id'] for message in spec['messages']]
        assert len(set(ids)) == len(ids)
        # RSL1k1: the id is a base id followed by a colon and the message's serial in the spec
        for serial, message_id in enumerate(ids):
            base_id, _, suffix = message_id.rpartition(':')
            assert base_id != ''
            assert suffix == str(serial)
        base_ids.append(ids[0].rpartition(':')[0])

    # RSC22d: RSL1k1 is applied to each BatchPublishSpec separately
    assert base_ids[0] != base_ids[1]


# UTS: rest/unit/RSC22d/explicit-ids-preserved-0
@deviation
async def test_rsc22d_batch_publish_explicit_ids_preserved():
    channel_name = f'test-RSC22d-explicit-{random_id()}'

    captured_requests = []
    mock_http = MockHttpClient(
        on_connection_attempt=lambda conn: conn.respond_with_success(),
        on_request=capture_and_respond(captured_requests),
    )
    client = rest_client(mock_http, idempotent_rest_publishing=True)

    await client.batch_publish({
        'channels': [channel_name],
        'messages': [
            Message(name='e1', data='d1', id='explicit-id-1'),
            Message(name='e2', data='d2', id='explicit-id-2'),
        ],
    })

    assert len(captured_requests) == 1
    messages = msgpack.unpackb(captured_requests[0].body)['messages']

    # RSL1k3: ids supplied by the caller are sent unaltered
    assert [message['id'] for message in messages] == ['explicit-id-1', 'explicit-id-2']


# UTS: rest/unit/RSC22d/ids-not-generated-disabled-0
@deviation
async def test_rsc22d_batch_publish_ids_not_generated_disabled():
    channel_name = f'test-RSC22d-disabled-{random_id()}'

    captured_requests = []
    mock_http = MockHttpClient(
        on_connection_attempt=lambda conn: conn.respond_with_success(),
        on_request=capture_and_respond(captured_requests),
    )
    client = rest_client(mock_http, idempotent_rest_publishing=False)

    await client.batch_publish({
        'channels': [channel_name],
        'messages': [Message(name='e1', data='d1'), Message(name='e2', data='d2')],
    })

    assert len(captured_requests) == 1
    messages = msgpack.unpackb(captured_requests[0].body)['messages']

    for message in messages:
        assert 'id' not in message or message['id'] is None


# UTS: rest/unit/BSP2a/channels-array-strings-0
@deviation
async def test_bsp2a_batch_publish_spec_channels_array_strings():
    channel_name_1 = f'test-BSP2a-a-{random_id()}'
    channel_name_2 = f'test-BSP2a-b-{random_id()}'
    channel_name_3 = f'test-BSP2a-c-{random_id()}'

    captured_requests = []
    mock_http = MockHttpClient(
        on_connection_attempt=lambda conn: conn.respond_with_success(),
        on_request=capture_and_respond(captured_requests),
    )
    client = rest_client(mock_http)

    await client.batch_publish({
        'channels': [channel_name_1, channel_name_2, channel_name_3],
        'messages': [Message(name='event', data='hello')],
    })

    assert len(captured_requests) == 1
    channels = msgpack.unpackb(captured_requests[0].body)['channels']

    assert isinstance(channels, list)
    assert all(isinstance(channel, str) for channel in channels)
    assert channels == [channel_name_1, channel_name_2, channel_name_3]


# UTS: rest/unit/BSP2b/messages-array-objects-0
@deviation
async def test_bsp2b_batch_publish_spec_messages_array_objects():
    channel_name = f'test-BSP2b-{random_id()}'

    captured_requests = []
    mock_http = MockHttpClient(
        on_connection_attempt=lambda conn: conn.respond_with_success(),
        on_request=capture_and_respond(captured_requests),
    )
    client = rest_client(mock_http)

    await client.batch_publish({
        'channels': [channel_name],
        'messages': [
            Message(name='event1', data='data1'),
            Message(name='event2', data={'key': 'value'}),
        ],
    })

    assert len(captured_requests) == 1
    messages = msgpack.unpackb(captured_requests[0].body)['messages']

    assert isinstance(messages, list)
    assert len(messages) == 2
    assert all(isinstance(message, dict) for message in messages)

    # TM2: each message carries its name, and its data encoded per RSL4
    assert messages[0]['name'] == 'event1'
    assert messages[0]['data'] == 'data1'
    assert messages[1]['name'] == 'event2'
    assert messages[1]['data'] == '{"key":"value"}'
    assert messages[1]['encoding'] == 'json'


# UTS: rest/unit/BPR2a/success-channel-name-0
@deviation
async def test_bpr2a_batch_publish_success_channel_name():
    channel_name = f'test-BPR2a-{random_id()}'

    mock_http = MockHttpClient(
        on_connection_attempt=lambda conn: conn.respond_with_success(),
        on_request=respond_with(201, [success_result(channel_name, 'msg123', ['s1'])]),
    )
    client = rest_client(mock_http)

    result = await client.batch_publish({
        'channels': [channel_name],
        'messages': [Message(name='event', data='hello')],
    })

    assert result.results[0].channel == channel_name


# UTS: rest/unit/BPR2b/success-message-id-prefix-0
@deviation
async def test_bpr2b_batch_publish_success_message_id_prefix():
    channel_name = f'test-BPR2b-{random_id()}'

    mock_http = MockHttpClient(
        on_connection_attempt=lambda conn: conn.respond_with_success(),
        on_request=respond_with(201, [success_result(channel_name, 'unique-id-prefix', ['s1', 's2'])]),
    )
    client = rest_client(mock_http)

    result = await client.batch_publish({
        'channels': [channel_name],
        'messages': [Message(name='e1', data='d1'), Message(name='e2', data='d2')],
    })

    assert result.results[0].message_id == 'unique-id-prefix'


# UTS: rest/unit/BPR2c/serials-array-0
@deviation
async def test_bpr2c_batch_publish_serials_array():
    channel_name = f'test-BPR2c-{random_id()}'

    mock_http = MockHttpClient(
        on_connection_attempt=lambda conn: conn.respond_with_success(),
        on_request=respond_with(201, [success_result(channel_name, 'msg', ['serial1', 'serial2', 'serial3'])]),
    )
    client = rest_client(mock_http)

    messages = [Message(name=f'e{index}', data=f'd{index}') for index in range(3)]
    result = await client.batch_publish({'channels': [channel_name], 'messages': messages})

    assert result.results[0].serials == ['serial1', 'serial2', 'serial3']
    assert len(result.results[0].serials) == len(messages)


# UTS: rest/unit/BPR2c/serials-null-conflated-0
@deviation
async def test_bpr2c_batch_publish_serials_null_conflated():
    channel_name = f'test-BPR2c1-{random_id()}'

    mock_http = MockHttpClient(
        on_connection_attempt=lambda conn: conn.respond_with_success(),
        on_request=respond_with(201, [{
            'channel': channel_name,
            'messageId': 'msg',
            'serials': ['serial1', None, 'serial3'],
        }]),
    )
    client = rest_client(mock_http)

    messages = [Message(name=f'e{index}', data=f'd{index}') for index in range(3)]
    result = await client.batch_publish({'channels': [channel_name], 'messages': messages})

    # BPR2c: a null serial marks a message discarded by a conflation rule
    assert result.results[0].serials == ['serial1', None, 'serial3']


# UTS: rest/unit/BPF2a/failure-channel-name-0
@deviation
async def test_bpf2a_batch_publish_failure_channel_name():
    channel_name = f'test-BPF2a-{random_id()}'

    mock_http = MockHttpClient(
        on_connection_attempt=lambda conn: conn.respond_with_success(),
        on_request=respond_with(201, [{
            'channel': channel_name,
            'error': {'code': 40160, 'statusCode': 401, 'message': 'Not permitted'},
        }]),
    )
    client = rest_client(mock_http)

    result = await client.batch_publish({
        'channels': [channel_name],
        'messages': [Message(name='event', data='hello')],
    })

    assert result.results[0].channel == channel_name


# UTS: rest/unit/BPF2b/failure-error-info-0
@deviation
async def test_bpf2b_batch_publish_failure_error_info():
    channel_name = f'test-BPF2b-{random_id()}'

    mock_http = MockHttpClient(
        on_connection_attempt=lambda conn: conn.respond_with_success(),
        on_request=respond_with(201, [{
            'channel': channel_name,
            'error': {
                'code': 40160,
                'statusCode': 401,
                'message': 'Channel operation not permitted',
                'href': 'https://help.ably.io/error/40160',
            },
        }]),
    )
    client = rest_client(mock_http)

    result = await client.batch_publish({
        'channels': [channel_name],
        'messages': [Message(name='event', data='hello')],
    })

    error = result.results[0].error
    assert error.code == 40160
    assert error.status_code == 401
    assert 'not permitted' in error.message


# UTS: rest/unit/RSC22c/partial-success-mixed-results-0
@deviation
async def test_rsc22c_batch_publish_partial_success_mixed_results():
    channel_name_allowed = f'test-BatchResult1-allowed-{random_id()}'
    channel_name_restricted = f'test-BatchResult1-restricted-{random_id()}'

    mock_http = MockHttpClient(
        on_connection_attempt=lambda conn: conn.respond_with_success(),
        on_request=respond_with(201, [
            success_result(channel_name_allowed, 'msg1', ['s1']),
            {
                'channel': channel_name_restricted,
                'error': {'code': 40160, 'statusCode': 401, 'message': 'Not permitted'},
            },
        ]),
    )
    client = rest_client(mock_http)

    result = await client.batch_publish({
        'channels': [channel_name_allowed, channel_name_restricted],
        'messages': [Message(name='event', data='hello')],
    })

    # NOTE: the spec writes result[0] / result[1]; BAR2c puts the per-channel results in
    # BatchResult.results, so they are read from there.
    assert len(result.results) == 2

    assert result.results[0].channel == channel_name_allowed
    assert result.results[0].message_id == 'msg1'
    assert getattr(result.results[0], 'error', None) is None

    assert result.results[1].channel == channel_name_restricted
    assert result.results[1].error.code == 40160


# UTS: rest/unit/RSC22c/distinguish-success-failure-0
@deviation
async def test_rsc22c_batch_publish_distinguish_success_failure():
    channel_name = f'test-BatchResult2-{random_id()}'
    failed_channel_name = f'test-BatchResult2-failed-{random_id()}'

    mock_http = MockHttpClient(
        on_connection_attempt=lambda conn: conn.respond_with_success(),
        on_request=respond_with(201, [
            success_result(channel_name, 'msg1', ['s1']),
            {
                'channel': failed_channel_name,
                'error': {'code': 40160, 'statusCode': 401, 'message': 'Not permitted'},
            },
        ]),
    )
    client = rest_client(mock_http)

    result = await client.batch_publish({
        'channels': [channel_name, failed_channel_name],
        'messages': [Message(name='event', data='hello')],
    })

    for entry in result.results:
        has_success_fields = getattr(entry, 'message_id', None) is not None and \
            getattr(entry, 'serials', None) is not None
        has_error_field = getattr(entry, 'error', None) is not None
        assert has_success_fields != has_error_field


# UTS: rest/unit/RSC22/empty-channels-rejected-0
@deviation
async def test_rsc22_batch_publish_empty_channels_rejected():
    mock_http = MockHttpClient(
        on_connection_attempt=lambda conn: conn.respond_with_success(),
        on_request=capture_and_respond([]),
    )
    client = rest_client(mock_http)

    with pytest.raises(AblyException) as excinfo:
        await client.batch_publish({'channels': [], 'messages': [Message(name='event', data='hello')]})

    # NOTE: the spec says only "the error indicates invalid request"; read as a 400.
    assert excinfo.value.status_code == 400


# UTS: rest/unit/RSC22/empty-messages-rejected-0
@deviation
async def test_rsc22_batch_publish_empty_messages_rejected():
    channel_name = f'test-RSC22-Error2-{random_id()}'

    mock_http = MockHttpClient(
        on_connection_attempt=lambda conn: conn.respond_with_success(),
        on_request=capture_and_respond([]),
    )
    client = rest_client(mock_http)

    with pytest.raises(AblyException) as excinfo:
        await client.batch_publish({'channels': [channel_name], 'messages': []})

    # NOTE: the spec says only "the error indicates invalid request"; read as a 400.
    assert excinfo.value.status_code == 400


# UTS: rest/unit/RSC22/server-error-propagated-0
@deviation
async def test_rsc22_batch_publish_server_error_propagated():
    channel_name = f'test-RSC22-Error3-{random_id()}'

    mock_http = MockHttpClient(
        on_connection_attempt=lambda conn: conn.respond_with_success(),
        on_request=respond_with(500, {
            'error': {'code': 50000, 'statusCode': 500, 'message': 'Internal error'},
        }),
    )
    client = rest_client(mock_http)

    with pytest.raises(AblyException) as excinfo:
        await client.batch_publish({
            'channels': [channel_name],
            'messages': [Message(name='event', data='hello')],
        })

    assert excinfo.value.code == 50000
    assert excinfo.value.status_code == 500


# UTS: rest/unit/RSC22/auth-error-propagated-0
@deviation
async def test_rsc22_batch_publish_auth_error_propagated():
    channel_name = f'test-RSC22-Error4-{random_id()}'

    mock_http = MockHttpClient(
        on_connection_attempt=lambda conn: conn.respond_with_success(),
        on_request=respond_with(401, {
            'error': {'code': 40101, 'statusCode': 401, 'message': 'Invalid credentials'},
        }),
    )
    client = rest_client(mock_http)

    with pytest.raises(AblyException) as excinfo:
        await client.batch_publish({
            'channels': [channel_name],
            'messages': [Message(name='event', data='hello')],
        })

    assert excinfo.value.code == 40101
    assert excinfo.value.status_code == 401


# UTS: rest/unit/RSC22/standard-headers-included-0
@deviation
async def test_rsc22_batch_publish_standard_headers_included():
    channel_name = f'test-RSC22-Headers1-{random_id()}'

    captured_requests = []
    mock_http = MockHttpClient(
        on_connection_attempt=lambda conn: conn.respond_with_success(),
        on_request=capture_and_respond(captured_requests),
    )
    client = rest_client(mock_http)

    await client.batch_publish({
        'channels': [channel_name],
        'messages': [Message(name='event', data='hello')],
    })

    assert len(captured_requests) == 1
    request = captured_requests[0]

    # UTS SPEC ERROR: RSC22_Headers1 - X-Ably-Version is the protocol version of CSV2b, which
    # batch_presence.md itself puts at >= 3 for current SDKs, not the hardcoded "2".
    assert int(request.headers['X-Ably-Version']) >= 3

    assert 'Ably-Agent' in request.headers

    # UTS SPEC ERROR: RSC22_Headers1 - Content-Type follows useBinaryProtocol (TO3f, default
    # true), so it is msgpack unless the test opts into the JSON protocol, which this one does not.
    assert request.headers['Content-Type'] == 'application/x-msgpack'


# UTS: rest/unit/RSC22/request-id-included-0
@deviation
async def test_rsc22_batch_publish_request_id_included():
    channel_name = f'test-RSC22-Headers2-{random_id()}'

    captured_requests = []
    mock_http = MockHttpClient(
        on_connection_attempt=lambda conn: conn.respond_with_success(),
        on_request=capture_and_respond(captured_requests),
    )
    client = rest_client(mock_http, add_request_ids=True)

    await client.batch_publish({
        'channels': [channel_name],
        'messages': [Message(name='event', data='hello')],
    })

    assert len(captured_requests) == 1
    request_id = captured_requests[0].url.query_params['request_id']

    # RSC7c: at least 9 bytes of randomness, url-safe base64 encoded
    assert request_id
    assert len(request_id) >= 12


# UTS: rest/unit/RSC22/multiple-messages-per-channel-0
@deviation
async def test_rsc22_batch_publish_multiple_messages_per_channel():
    channel_name = f'test-RSC22-Batch1-{random_id()}'

    captured_requests = []
    mock_http = MockHttpClient(
        on_connection_attempt=lambda conn: conn.respond_with_success(),
        on_request=capture_and_respond(captured_requests, body=[
            success_result(channel_name, 'msg', [f's{index}' for index in range(100)]),
        ]),
    )
    client = rest_client(mock_http)

    messages = [Message(name=f'event-{index}', data=f'data-{index}') for index in range(100)]
    result = await client.batch_publish({'channels': [channel_name], 'messages': messages})

    assert len(captured_requests) == 1
    sent_messages = msgpack.unpackb(captured_requests[0].body)['messages']
    assert len(sent_messages) == 100
    assert sent_messages[0]['name'] == 'event-0'
    assert sent_messages[99]['name'] == 'event-99'

    assert len(result.results[0].serials) == 100


# UTS: rest/unit/RSC22/multiple-channels-multiple-messages-0
@deviation
async def test_rsc22_batch_publish_multiple_channels_multiple_messages():
    channel_name_1 = f'test-RSC22-Batch2-a-{random_id()}'
    channel_name_2 = f'test-RSC22-Batch2-b-{random_id()}'
    channel_name_3 = f'test-RSC22-Batch2-c-{random_id()}'

    captured_requests = []
    mock_http = MockHttpClient(
        on_connection_attempt=lambda conn: conn.respond_with_success(),
        on_request=capture_and_respond(captured_requests, body=[
            success_result(channel_name_1, 'msg1', ['s1', 's2', 's3']),
            success_result(channel_name_2, 'msg2', ['s4', 's5', 's6']),
            success_result(channel_name_3, 'msg3', ['s7', 's8', 's9']),
        ]),
    )
    client = rest_client(mock_http)

    result = await client.batch_publish({
        'channels': [channel_name_1, channel_name_2, channel_name_3],
        'messages': [
            Message(name='msg1', data='d1'),
            Message(name='msg2', data='d2'),
            Message(name='msg3', data='d3'),
        ],
    })

    assert len(captured_requests) == 1
    body = msgpack.unpackb(captured_requests[0].body)
    assert len(body['channels']) == 3
    assert len(body['messages']) == 3

    # 3 messages to each of 3 channels is 9 publications, reported as one result per channel
    assert len(result.results) == 3
    assert sum(len(entry.serials) for entry in result.results) == 9
