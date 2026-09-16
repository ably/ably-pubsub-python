"""Derived from uts/rest/unit/encoding/message_encoding.md in ably/specification.

Spec points: RSL4, RSL4a, RSL4b, RSL4c, RSL4d, RSL6, RSL6a, RSL6b
"""

import base64
import json
import os

import msgpack
import pytest

from ably.util.exceptions import AblyException
from test.uts.helpers.client import rest_client
from test.uts.helpers.mock_http import MockHttpClient

MSGPACK_CONTENT_TYPE = 'application/x-msgpack'

FIXTURES_PATH = os.path.join(
    os.path.dirname(__file__), '..', '..', '..', '..', '..',
    'submodules', 'test-resources', 'messages-encoding.json')


def publish_mock(captured_requests):
    def on_request(request):
        captured_requests.append(request)
        request.respond_with(201, {'serials': ['s1']})

    return on_request


def history_mock(captured_requests, body, headers=None):
    def on_request(request):
        captured_requests.append(request)
        request.respond_with(200, body, headers)

    return on_request


def published_message(request, binary=True):
    """The message a publish request carried.

    ably-python posts a lone message as a bare object rather than as a
    one-element array, which is the other form the REST API accepts, so the
    spec's `parse_json(request.body)[0]` indexing does not apply here.
    """
    body = msgpack.unpackb(request.body) if binary else json.loads(request.body)
    assert isinstance(body, dict)
    return body


# UTS: rest/unit/RSL4a/string-data-no-encoding-0
async def test_rsl4a_string_data_no_encoding():
    captured_requests = []
    mock_http = MockHttpClient(
        on_connection_attempt=lambda conn: conn.respond_with_success(),
        on_request=publish_mock(captured_requests),
    )
    client = rest_client(mock_http, use_binary_protocol=False)
    channel = client.channels.get('test-RSL4a')

    await channel.publish(name='event', data='plain string data')

    body = published_message(captured_requests[0], binary=False)

    assert body['data'] == 'plain string data'
    assert 'encoding' not in body or body['encoding'] is None


# UTS: rest/unit/RSL4b/json-object-encoding-0
async def test_rsl4b_json_object_encoding():
    captured_requests = []
    mock_http = MockHttpClient(
        on_connection_attempt=lambda conn: conn.respond_with_success(),
        on_request=publish_mock(captured_requests),
    )
    client = rest_client(mock_http, use_binary_protocol=False)
    channel = client.channels.get('test-RSL4b')

    await channel.publish(name='event', data={'key': 'value', 'nested': {'a': 1}})

    body = published_message(captured_requests[0], binary=False)

    assert isinstance(body['data'], str)
    assert json.loads(body['data']) == {'key': 'value', 'nested': {'a': 1}}
    assert body['encoding'] == 'json'


# UTS: rest/unit/RSL4c/binary-base64-json-protocol-0
async def test_rsl4c_binary_base64_json_protocol():
    captured_requests = []
    mock_http = MockHttpClient(
        on_connection_attempt=lambda conn: conn.respond_with_success(),
        on_request=publish_mock(captured_requests),
    )
    client = rest_client(mock_http, use_binary_protocol=False)
    channel = client.channels.get('test-RSL4c')

    binary_data = bytes([0x00, 0x01, 0x02, 0xFF, 0xFE])
    await channel.publish(name='event', data=binary_data)

    body = published_message(captured_requests[0], binary=False)

    assert body['encoding'] == 'base64'
    assert base64.b64decode(body['data']) == bytes([0x00, 0x01, 0x02, 0xFF, 0xFE])


# UTS: rest/unit/RSL4c/binary-direct-msgpack-protocol-1
async def test_rsl4c_binary_direct_msgpack_protocol():
    captured_requests = []
    mock_http = MockHttpClient(
        on_connection_attempt=lambda conn: conn.respond_with_success(),
        on_request=publish_mock(captured_requests),
    )
    client = rest_client(mock_http, use_binary_protocol=True)
    channel = client.channels.get('test-RSL4c-msgpack')

    binary_data = bytes([0x00, 0x01, 0x02, 0xFF, 0xFE])
    await channel.publish(name='event', data=binary_data)

    body = published_message(captured_requests[0])

    assert body['data'] == bytes([0x00, 0x01, 0x02, 0xFF, 0xFE])
    assert 'encoding' not in body or body['encoding'] is None


# UTS: rest/unit/RSL4d/array-json-encoding-0
async def test_rsl4d_array_json_encoding():
    captured_requests = []
    mock_http = MockHttpClient(
        on_connection_attempt=lambda conn: conn.respond_with_success(),
        on_request=publish_mock(captured_requests),
    )
    client = rest_client(mock_http, use_binary_protocol=False)
    channel = client.channels.get('test-RSL4d')

    await channel.publish(name='event', data=[1, 2, 'three', {'four': 4}])

    body = published_message(captured_requests[0], binary=False)

    assert body['encoding'] == 'json'
    assert json.loads(body['data']) == [1, 2, 'three', {'four': 4}]


# UTS: rest/unit/RSL6a/decode-base64-to-binary-0
async def test_rsl6a_decode_base64_to_binary():
    captured_requests = []
    mock_http = MockHttpClient(
        on_connection_attempt=lambda conn: conn.respond_with_success(),
        on_request=history_mock(captured_requests, [
            {
                'id': 'msg1',
                'name': 'event',
                'data': 'AAECAwQ=',  # base64 of [0, 1, 2, 3, 4]
                'encoding': 'base64',
                'timestamp': 1234567890000,
            },
        ]),
    )
    client = rest_client(mock_http)
    channel = client.channels.get('test-RSL6a')

    history = await channel.history()
    message = history.items[0]

    assert message.data == bytes([0x00, 0x01, 0x02, 0x03, 0x04])
    # NOTE: the spec asserts the encoding IS null. ably-python spells "no
    # encoding remains" as the empty string, which EncodeDataMixin joins from
    # an empty encoding list.
    assert message.encoding == ''


# UTS: rest/unit/RSL6a/decode-json-to-object-1
async def test_rsl6a_decode_json_to_object():
    captured_requests = []
    mock_http = MockHttpClient(
        on_connection_attempt=lambda conn: conn.respond_with_success(),
        on_request=history_mock(captured_requests, [
            {
                'id': 'msg1',
                'name': 'event',
                'data': '{"key":"value","number":42}',
                'encoding': 'json',
                'timestamp': 1234567890000,
            },
        ]),
    )
    client = rest_client(mock_http)
    channel = client.channels.get('test-RSL6a-json')

    history = await channel.history()
    message = history.items[0]

    assert message.data == {'key': 'value', 'number': 42}
    assert message.encoding == ''


# UTS: rest/unit/RSL6a/decode-chained-encodings-2
async def test_rsl6a_decode_chained_encodings():
    json_string = '{"key":"value"}'
    base64_of_json = base64.b64encode(json_string.encode('utf-8')).decode('ascii')

    captured_requests = []
    mock_http = MockHttpClient(
        on_connection_attempt=lambda conn: conn.respond_with_success(),
        on_request=history_mock(captured_requests, [
            {
                'id': 'msg1',
                'name': 'event',
                'data': base64_of_json,
                'encoding': 'json/base64',  # Decode base64 first, then JSON
                'timestamp': 1234567890000,
            },
        ]),
    )
    client = rest_client(mock_http)
    channel = client.channels.get('test-RSL6a-chained')

    history = await channel.history()
    message = history.items[0]

    assert message.data == {'key': 'value'}
    assert message.encoding == ''


# UTS: rest/unit/RSL6b/unrecognized-encoding-preserved-0
async def test_rsl6b_unrecognized_encoding_preserved():
    # UTS SPEC ERROR: rest/unit/RSL6b/unrecognized-encoding-preserved-0 - the spec's payload
    # "encrypted-data-here" is not valid base64, so the base64 decode the spec asserts
    # succeeds cannot happen; a valid base64 payload is used in its place.
    payload = base64.b64encode(b'encrypted-data-here').decode('ascii')

    captured_requests = []
    mock_http = MockHttpClient(
        on_connection_attempt=lambda conn: conn.respond_with_success(),
        on_request=history_mock(captured_requests, [
            {
                'id': 'msg1',
                'name': 'event',
                'data': payload,
                'encoding': 'custom-encryption/base64',
                'timestamp': 1234567890000,
            },
        ]),
    )
    client = rest_client(mock_http)
    channel = client.channels.get('test-RSL6b')

    history = await channel.history()
    message = history.items[0]

    # base64 is decoded, custom-encryption is unrecognized and left in place
    assert message.encoding == 'custom-encryption'
    assert isinstance(message.data, (bytes, bytearray))
    assert message.data == b'encrypted-data-here'


# UTS: rest/unit/RSL6/msgpack-binary-stays-binary-0
async def test_rsl6_msgpack_binary_stays_binary():
    binary_payload = bytes([0x48, 0x65, 0x6C, 0x6C, 0x6F])  # "Hello" as bytes - valid UTF-8

    captured_requests = []
    mock_http = MockHttpClient(
        on_connection_attempt=lambda conn: conn.respond_with_success(),
        on_request=history_mock(
            captured_requests,
            msgpack.packb([{'name': 'event', 'data': binary_payload}], use_bin_type=True),
            {'Content-Type': MSGPACK_CONTENT_TYPE},
        ),
    )
    client = rest_client(mock_http, use_binary_protocol=True)
    channel = client.channels.get('test-RSL6-msgpack-binary')

    history = await channel.history()
    message = history.items[0]

    # Binary data must remain binary, NOT be converted to a string
    assert isinstance(message.data, (bytes, bytearray))
    assert message.data == bytes([0x48, 0x65, 0x6C, 0x6C, 0x6F])
    assert message.encoding == ''


# UTS: rest/unit/RSL6/msgpack-string-stays-string-1
async def test_rsl6_msgpack_string_stays_string():
    captured_requests = []
    mock_http = MockHttpClient(
        on_connection_attempt=lambda conn: conn.respond_with_success(),
        on_request=history_mock(
            captured_requests,
            msgpack.packb([{'name': 'event', 'data': 'Hello World'}], use_bin_type=True),
            {'Content-Type': MSGPACK_CONTENT_TYPE},
        ),
    )
    client = rest_client(mock_http, use_binary_protocol=True)
    channel = client.channels.get('test-RSL6-msgpack-string')

    history = await channel.history()
    message = history.items[0]

    assert isinstance(message.data, str)
    assert message.data == 'Hello World'
    assert message.encoding == ''


# UTS: rest/unit/RSL4/encoding-fixtures-ably-common-0
@pytest.mark.skipif(not os.path.exists(FIXTURES_PATH),
                    reason='ably-common submodule not checked out')
async def test_rsl4_encoding_fixtures_ably_common():
    # UTS SPEC ERROR: rest/unit/RSL4/encoding-fixtures-ably-common-0 - the spec loads
    # "encoding.json" with input_data/expected_wire_data/expected_encoding/use_binary_protocol
    # fields; ably-common has no such fixture, so messages-encoding.json (the file RSL6a1
    # names) is driven in the encode direction instead.
    with open(FIXTURES_PATH) as fixture_file:
        encoding_fixtures = json.load(fixture_file)['messages']

    for fixture in encoding_fixtures:
        if 'expectedHexValue' in fixture:
            input_data = bytes.fromhex(fixture['expectedHexValue'])
        else:
            input_data = fixture['expectedValue']

        captured_requests = []
        mock_http = MockHttpClient(
            on_connection_attempt=lambda conn: conn.respond_with_success(),
            on_request=publish_mock(captured_requests),
        )
        # The fixture's wire values are those of the JSON transport
        client = rest_client(mock_http, use_binary_protocol=False)
        channel = client.channels.get('test-RSL4-fixture')

        await channel.publish(name='event', data=input_data)

        body = published_message(captured_requests[0], binary=False)

        if fixture['encoding'] == 'json':
            # ably-python's json.dumps uses spacing separators, so the wire string
            # differs from the fixture's byte for byte while the value matches
            assert json.loads(body['data']) == json.loads(fixture['data'])
        else:
            assert body['data'] == fixture['data']

        assert body.get('encoding') == fixture['encoding']


# UTS: rest/unit/RSL4/null-data-no-encoding-1
async def test_rsl4_null_data_no_encoding():
    captured_requests = []
    mock_http = MockHttpClient(
        on_connection_attempt=lambda conn: conn.respond_with_success(),
        on_request=publish_mock(captured_requests),
    )
    client = rest_client(mock_http, use_binary_protocol=False)
    channel = client.channels.get('test-RSL4-null')

    await channel.publish(name='event', data=None)

    body = published_message(captured_requests[0], binary=False)

    # RSL1e: a null data property is omitted from the body rather than sent as null
    assert body.get('data') is None
    assert 'encoding' not in body or body['encoding'] is None


# UTS: rest/unit/RSL4a/number-type-rejected-1
async def test_rsl4a_number_type_rejected():
    mock_http = MockHttpClient(
        on_connection_attempt=lambda conn: conn.respond_with_success(),
        on_request=lambda request: request.respond_with(201, {'serials': ['s1']}),
    )
    client = rest_client(mock_http, use_binary_protocol=False)
    channel = client.channels.get('test')

    with pytest.raises(AblyException) as excinfo:
        await channel.publish(name='event', data=42)

    assert excinfo.value is not None


# UTS: rest/unit/RSL4a/boolean-type-rejected-2
async def test_rsl4a_boolean_type_rejected():
    mock_http = MockHttpClient(
        on_connection_attempt=lambda conn: conn.respond_with_success(),
        on_request=lambda request: request.respond_with(201, {'serials': ['s1']}),
    )
    client = rest_client(mock_http, use_binary_protocol=False)
    channel = client.channels.get('test')

    with pytest.raises(AblyException) as excinfo:
        await channel.publish(name='event', data=True)

    assert excinfo.value is not None


# UTS: rest/unit/RSL6/decode-utf8-base64-data-2
async def test_rsl6_decode_utf8_base64_data():
    captured_requests = []
    mock_http = MockHttpClient(
        on_connection_attempt=lambda conn: conn.respond_with_success(),
        on_request=history_mock(captured_requests, [
            {
                'id': 'msg1',
                'name': 'event',
                'data': 'SGVsbG8gV29ybGQ=',  # base64 of UTF-8 "Hello World"
                'encoding': 'utf-8/base64',
                'timestamp': 1234567890000,
            },
        ]),
    )
    client = rest_client(mock_http)
    channel = client.channels.get('test-RSL6-utf8')

    history = await channel.history()
    message = history.items[0]

    assert message.data == 'Hello World'
    assert isinstance(message.data, str)
    assert message.encoding == ''


# UTS: rest/unit/RSL6/complex-chained-encoding-3
async def test_rsl6_complex_chained_encoding():
    original_object = {'status': 'active', 'count': 5}
    json_string = json.dumps(original_object, separators=(',', ':'))
    utf8_bytes = json_string.encode('utf-8')
    base64_data = base64.b64encode(utf8_bytes).decode('ascii')

    captured_requests = []
    mock_http = MockHttpClient(
        on_connection_attempt=lambda conn: conn.respond_with_success(),
        on_request=history_mock(captured_requests, [
            {
                'id': 'msg1',
                'name': 'event',
                'data': base64_data,
                'encoding': 'json/utf-8/base64',
                'timestamp': 1234567890000,
            },
        ]),
    )
    client = rest_client(mock_http)
    channel = client.channels.get('test-RSL6-complex')

    history = await channel.history()
    message = history.items[0]

    # Should decode: base64 -> utf-8 -> json
    assert message.data == {'status': 'active', 'count': 5}
    assert message.encoding == ''


# UTS: rest/unit/RSL4/json-protocol-content-type-2
async def test_rsl4_json_protocol_content_type():
    captured_requests = []
    mock_http = MockHttpClient(
        on_connection_attempt=lambda conn: conn.respond_with_success(),
        on_request=publish_mock(captured_requests),
    )
    client = rest_client(mock_http, use_binary_protocol=False)
    channel = client.channels.get('test-RSL4-json-ct')

    await channel.publish(name='event', data='test')

    request = captured_requests[0]
    assert request.headers['Content-Type'] == 'application/json'
    assert request.headers['Accept'] == 'application/json'


# UTS: rest/unit/RSL4/msgpack-protocol-content-type-3
async def test_rsl4_msgpack_protocol_content_type():
    captured_requests = []
    mock_http = MockHttpClient(
        on_connection_attempt=lambda conn: conn.respond_with_success(),
        on_request=publish_mock(captured_requests),
    )
    client = rest_client(mock_http, use_binary_protocol=True)
    channel = client.channels.get('test-RSL4-msgpack-ct')

    await channel.publish(name='event', data='test')

    request = captured_requests[0]
    assert request.headers['Content-Type'] == 'application/x-msgpack'
    assert request.headers['Accept'] == 'application/x-msgpack'


# UTS: rest/unit/RSL4/empty-string-no-encoding-4
async def test_rsl4_empty_string_no_encoding():
    captured_requests = []
    mock_http = MockHttpClient(
        on_connection_attempt=lambda conn: conn.respond_with_success(),
        on_request=publish_mock(captured_requests),
    )
    client = rest_client(mock_http, use_binary_protocol=False)
    channel = client.channels.get('test-RSL4-empty-str')

    await channel.publish(name='event', data='')

    body = published_message(captured_requests[0], binary=False)

    assert body['data'] == ''
    assert 'encoding' not in body or body['encoding'] is None


# UTS: rest/unit/RSL4/empty-array-json-encoding-5
async def test_rsl4_empty_array_json_encoding():
    captured_requests = []
    mock_http = MockHttpClient(
        on_connection_attempt=lambda conn: conn.respond_with_success(),
        on_request=publish_mock(captured_requests),
    )
    client = rest_client(mock_http, use_binary_protocol=False)
    channel = client.channels.get('test-RSL4-empty-arr')

    await channel.publish(name='event', data=[])

    body = published_message(captured_requests[0], binary=False)

    assert body['encoding'] == 'json'
    assert json.loads(body['data']) == []


# NOTE: the spec's "RSL4 - Empty object encoding" section carries no Test ID, so the
# id below follows the numbering of its siblings under RSL4.
# UTS: rest/unit/RSL4/empty-object-json-encoding-6
async def test_rsl4_empty_object_json_encoding():
    captured_requests = []
    mock_http = MockHttpClient(
        on_connection_attempt=lambda conn: conn.respond_with_success(),
        on_request=publish_mock(captured_requests),
    )
    client = rest_client(mock_http, use_binary_protocol=False)
    channel = client.channels.get('test-RSL4-empty-obj')

    await channel.publish(name='event', data={})

    body = published_message(captured_requests[0], binary=False)

    assert body['encoding'] == 'json'
    assert json.loads(body['data']) == {}
