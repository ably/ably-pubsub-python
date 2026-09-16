"""Derived from uts/rest/unit/channel/update_delete_message.md in ably/specification.

Spec points: RSL15, RSL15a, RSL15b, RSL15b1, RSL15b7, RSL15c, RSL15d, RSL15e, RSL15f
"""

import json
import uuid
from urllib.parse import urlsplit

import msgpack
import pytest

from ably.types.message import Message
from ably.types.operations import MessageOperation, UpdateDeleteResult
from ably.util.exceptions import AblyException
from test.uts.helpers.client import rest_client
from test.uts.helpers.mock_http import MockHttpClient


def random_id():
    return uuid.uuid4().hex[:8]


def capture_and_respond(captured_requests, body=None):
    def on_request(request):
        captured_requests.append(request)
        request.respond_with(200, body if body is not None else {'versionSerial': 'vs1'})

    return on_request


def request_body(request):
    """The body a PATCH carried, in wire form.

    The specification reads it with `parse_json`; `use_binary_protocol` defaults to True
    in ably-python, so the body is msgpack.
    """
    return msgpack.unpackb(request.body)


def raw_path(request):
    """The request path as it went on the wire, with percent-escapes intact.

    `request.url.path` is percent-decoded by the HTTP layer the mock records, which loses
    the encoding the specification asserts on.
    """
    return urlsplit(str(request.url)).path


# UTS: rest/unit/RSL15b/update-sends-patch-update-0
async def test_rsl15b_update_sends_patch_update():
    channel_name = f'test-RSL15-update-{random_id()}'
    captured_requests = []
    mock_http = MockHttpClient(
        on_connection_attempt=lambda conn: conn.respond_with_success(),
        on_request=capture_and_respond(captured_requests),
    )
    client = rest_client(mock_http)
    channel = client.channels.get(channel_name)

    await channel.update_message(
        Message(serial='msg-serial-1', name='updated', data='new-data'))

    assert len(captured_requests) == 1

    request = captured_requests[0]
    assert request.method == 'PATCH'
    assert request.url.path == f'/channels/{channel_name}/messages/msg-serial-1'

    body = request_body(request)
    assert body['action'] == 1  # MESSAGE_UPDATE numeric value
    assert body['name'] == 'updated'
    assert body['data'] == 'new-data'


# UTS: rest/unit/RSL15b/delete-sends-patch-delete-1
async def test_rsl15b_delete_sends_patch_delete():
    channel_name = f'test-RSL15-delete-{random_id()}'
    captured_requests = []
    mock_http = MockHttpClient(
        on_connection_attempt=lambda conn: conn.respond_with_success(),
        on_request=capture_and_respond(captured_requests),
    )
    client = rest_client(mock_http)
    channel = client.channels.get(channel_name)

    await channel.delete_message(Message(serial='msg-serial-1'))

    request = captured_requests[0]
    assert request.method == 'PATCH'
    assert request.url.path == f'/channels/{channel_name}/messages/msg-serial-1'

    body = request_body(request)
    assert body['action'] == 2  # MESSAGE_DELETE numeric value


# UTS: rest/unit/RSL15b/append-sends-patch-append-2
async def test_rsl15b_append_sends_patch_append():
    channel_name = f'test-RSL15-append-{random_id()}'
    captured_requests = []
    mock_http = MockHttpClient(
        on_connection_attempt=lambda conn: conn.respond_with_success(),
        on_request=capture_and_respond(captured_requests),
    )
    client = rest_client(mock_http)
    channel = client.channels.get(channel_name)

    await channel.append_message(Message(serial='msg-serial-1', data='appended-data'))

    request = captured_requests[0]
    assert request.method == 'PATCH'
    assert request.url.path == f'/channels/{channel_name}/messages/msg-serial-1'

    body = request_body(request)
    assert body['action'] == 5  # MESSAGE_APPEND numeric value
    assert body['data'] == 'appended-data'


# UTS: rest/unit/RSL15b7/version-set-with-operation-0
async def test_rsl15b7_version_set_with_operation():
    channel_name = f'test-RSL15b7-{random_id()}'
    captured_requests = []
    mock_http = MockHttpClient(
        on_connection_attempt=lambda conn: conn.respond_with_success(),
        on_request=capture_and_respond(captured_requests),
    )
    client = rest_client(mock_http)
    channel = client.channels.get(channel_name)

    await channel.update_message(
        Message(serial='s1', data='updated'),
        operation=MessageOperation(
            client_id='user1',
            description='fixed typo',
            metadata={'reason': 'typo'},
        ),
    )

    body = request_body(captured_requests[0])
    assert 'version' in body
    assert body['version']['clientId'] == 'user1'
    assert body['version']['description'] == 'fixed typo'
    assert body['version']['metadata']['reason'] == 'typo'


# UTS: rest/unit/RSL15b7/version-absent-no-operation-1
async def test_rsl15b7_version_absent_no_operation():
    channel_name = f'test-RSL15b7-absent-{random_id()}'
    captured_requests = []
    mock_http = MockHttpClient(
        on_connection_attempt=lambda conn: conn.respond_with_success(),
        on_request=capture_and_respond(captured_requests),
    )
    client = rest_client(mock_http)
    channel = client.channels.get(channel_name)

    await channel.update_message(Message(serial='s1', data='updated'))

    body = request_body(captured_requests[0])
    assert 'version' not in body


# UTS: rest/unit/RSL15c/no-mutate-user-message-0
async def test_rsl15c_no_mutate_user_message():
    channel_name = f'test-RSL15c-{random_id()}'
    captured_requests = []
    mock_http = MockHttpClient(
        on_connection_attempt=lambda conn: conn.respond_with_success(),
        on_request=capture_and_respond(captured_requests),
    )
    client = rest_client(mock_http)
    channel = client.channels.get(channel_name)

    original_msg = Message(serial='s1', name='orig', data='original-data')

    await channel.update_message(original_msg)

    # Original message must not have been mutated
    assert original_msg.action is None  # No action was set on original
    assert original_msg.name == 'orig'
    assert original_msg.data == 'original-data'

    # But the request body should contain the action
    body = request_body(captured_requests[0])
    assert body['action'] == 1  # MESSAGE_UPDATE


# UTS: rest/unit/RSL15e/returns-update-delete-result-0
async def test_rsl15e_returns_update_delete_result():
    channel_name = f'test-RSL15e-{random_id()}'
    mock_http = MockHttpClient(
        on_connection_attempt=lambda conn: conn.respond_with_success(),
        on_request=lambda request: request.respond_with(
            200, {'versionSerial': 'version-serial-abc'}),
    )
    client = rest_client(mock_http)
    channel = client.channels.get(channel_name)

    result = await channel.update_message(Message(serial='s1', data='updated'))

    assert isinstance(result, UpdateDeleteResult)
    assert result.version_serial == 'version-serial-abc'


# UTS: rest/unit/RSL15e/null-version-serial-1
async def test_rsl15e_null_version_serial():
    channel_name = f'test-RSL15e-null-{random_id()}'
    mock_http = MockHttpClient(
        on_connection_attempt=lambda conn: conn.respond_with_success(),
        on_request=lambda request: request.respond_with(200, {'versionSerial': None}),
    )
    client = rest_client(mock_http)
    channel = client.channels.get(channel_name)

    result = await channel.update_message(Message(serial='s1', data='updated'))

    assert isinstance(result, UpdateDeleteResult)
    assert result.version_serial is None


# UTS: rest/unit/RSL15f/params-sent-as-querystring-0
async def test_rsl15f_params_sent_as_querystring():
    channel_name = f'test-RSL15f-{random_id()}'
    captured_requests = []
    mock_http = MockHttpClient(
        on_connection_attempt=lambda conn: conn.respond_with_success(),
        on_request=capture_and_respond(captured_requests),
    )
    client = rest_client(mock_http)
    channel = client.channels.get(channel_name)

    await channel.update_message(
        Message(serial='s1', data='updated'),
        params={'key': 'value', 'num': '42'},
    )

    request = captured_requests[0]
    assert request.url.query_params['key'] == 'value'
    assert request.url.query_params['num'] == '42'


# UTS: rest/unit/RSL15a/serial-required-throws-error-0
async def test_rsl15a_serial_required_throws_error():
    channel_name = f'test-RSL15a-{random_id()}'
    mock_http = MockHttpClient(
        on_connection_attempt=lambda conn: conn.respond_with_success(),
        on_request=lambda request: request.respond_with(200, {'versionSerial': 'vs1'}),
    )
    client = rest_client(mock_http)
    channel = client.channels.get(channel_name)

    # update_message without serial
    with pytest.raises(AblyException) as excinfo:
        await channel.update_message(Message(name='x', data='y'))
    assert excinfo.value.code == 40003

    # delete_message without serial
    with pytest.raises(AblyException) as excinfo:
        await channel.delete_message(Message(name='x'))
    assert excinfo.value.code == 40003

    # append_message without serial
    with pytest.raises(AblyException) as excinfo:
        await channel.append_message(Message(data='y'))
    assert excinfo.value.code == 40003


# UTS: rest/unit/RSL15d/body-encoded-per-rsl4-0
async def test_rsl15d_body_encoded_per_rsl4():
    channel_name = f'test-RSL15d-{random_id()}'
    captured_requests = []
    mock_http = MockHttpClient(
        on_connection_attempt=lambda conn: conn.respond_with_success(),
        on_request=capture_and_respond(captured_requests),
    )
    client = rest_client(mock_http)
    channel = client.channels.get(channel_name)

    # JSON object data should be encoded per RSL4
    await channel.update_message(Message(serial='s1', data={'key': 'value'}))

    body = request_body(captured_requests[0])

    # JSON data should be JSON-encoded as a string with encoding field
    assert isinstance(body['data'], str)
    assert body['encoding'] == 'json'
    assert json.loads(body['data']) == {'key': 'value'}


# UTS: rest/unit/RSL15b/serial-url-encoded-path-3
async def test_rsl15b_serial_url_encoded_path():
    channel_name = f'test-RSL15b-encode-{random_id()}'
    captured_requests = []
    serial_with_special_chars = 'serial/special:chars'
    mock_http = MockHttpClient(
        on_connection_attempt=lambda conn: conn.respond_with_success(),
        on_request=capture_and_respond(captured_requests),
    )
    client = rest_client(mock_http)
    channel = client.channels.get(channel_name)

    await channel.update_message(
        Message(serial=serial_with_special_chars, data='updated'))

    request = captured_requests[0]

    # DEVIATION: the spec asserts encode_uri_component(serial), which escapes ':' as %3A.
    # Channel._send_update escapes the serial with `parse.quote_plus(serial, safe=':')`, so
    # '/' becomes %2F but ':' is left as-is. ':' is a legal path character and Ably serials
    # carry it, so both forms name the same serial once the server decodes them.
    assert raw_path(request) == f'/channels/{channel_name}/messages/serial%2Fspecial:chars'
