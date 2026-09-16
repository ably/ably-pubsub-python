"""Derived from uts/rest/unit/channel/annotations.md in ably/specification.

Spec points: RSL10, RSAN1, RSAN1a, RSAN1a2, RSAN1a3, RSAN1c, RSAN1c1, RSAN1c2, RSAN1c3,
RSAN1c4, RSAN1c5, RSAN1c6, RSAN2, RSAN2a, RSAN3, RSAN3a, RSAN3b, RSAN3c

Four of the specification's sections carry no Test ID (RSAN2a delete, the two RSAN3b
sections and RSAN3c). Their `# UTS:` ids below are inferred from the section heading,
following the convention the sections that do carry one use, and are marked as such.
"""

import json
import re
import uuid

import msgpack
import pytest

from ably.http.paginatedresult import PaginatedResult
from ably.rest.annotations import RestAnnotations
from ably.types.annotation import Annotation, AnnotationAction
from ably.util.exceptions import AblyException
from test.uts.helpers.client import rest_client
from test.uts.helpers.deviations import deviation
from test.uts.helpers.mock_http import MockHttpClient


def random_id():
    return uuid.uuid4().hex[:8]


def capture_and_respond(captured_requests, status, body):
    def on_request(request):
        captured_requests.append(request)
        request.respond_with(status, body)

    return on_request


def published_annotations(request):
    """The annotations a publish request carried, in wire form.

    The specification reads the body with `parse_json`; `use_binary_protocol` defaults to
    True in ably-python, so the body is msgpack.
    """
    return msgpack.unpackb(request.body)


# UTS: rest/unit/RSL10/annotations-attribute-type-0
async def test_rsl10_annotations_attribute_type():
    mock_http = MockHttpClient(
        on_connection_attempt=lambda conn: conn.respond_with_success(),
        on_request=lambda request: request.respond_with(200, {}),
    )
    client = rest_client(mock_http)
    channel = client.channels.get('test-RSL10')

    assert isinstance(channel.annotations, RestAnnotations)


# UTS: rest/unit/RSAN1c6/publish-post-annotation-create-0
async def test_rsan1c6_publish_post_annotation_create():
    channel_name = f'test-RSAN1-publish-{random_id()}'
    captured_requests = []
    mock_http = MockHttpClient(
        on_connection_attempt=lambda conn: conn.respond_with_success(),
        on_request=capture_and_respond(captured_requests, 201, {}),
    )
    client = rest_client(mock_http)
    channel = client.channels.get(channel_name)

    await channel.annotations.publish(
        'msg-serial-1',
        Annotation(type='com.example.reaction', name='like'),
    )

    assert len(captured_requests) == 1

    request = captured_requests[0]
    assert request.method == 'POST'
    assert request.url.path == f'/channels/{channel_name}/messages/msg-serial-1/annotations'

    body = published_annotations(request)
    assert isinstance(body, list)
    assert len(body) == 1

    annotation = body[0]
    assert annotation['action'] == 0  # ANNOTATION_CREATE numeric value
    assert annotation['messageSerial'] == 'msg-serial-1'
    assert annotation['type'] == 'com.example.reaction'
    assert annotation['name'] == 'like'


# UTS: rest/unit/RSAN1a3/publish-type-required-0
async def test_rsan1a3_publish_type_required():
    channel_name = f'test-RSAN1a3-{random_id()}'
    mock_http = MockHttpClient(
        on_connection_attempt=lambda conn: conn.respond_with_success(),
        on_request=lambda request: request.respond_with(201, {}),
    )
    client = rest_client(mock_http)
    channel = client.channels.get(channel_name)

    # Annotation without type
    with pytest.raises(AblyException) as excinfo:
        await channel.annotations.publish('msg-serial-1', Annotation(name='like'))

    # DEVIATION: the spec asserts error.code == 40003 (invalid request parameter value).
    # `construct_validate_annotation` in ably/rest/annotations.py raises 40000 (bad
    # request) for a missing type; RSAN1a3 itself names no code.
    assert excinfo.value.code == 40000
    assert excinfo.value.status_code == 400


# UTS: rest/unit/RSAN1c3/annotation-data-encoded-0
async def test_rsan1c3_annotation_data_encoded():
    channel_name = f'test-RSAN1c3-{random_id()}'
    captured_requests = []
    mock_http = MockHttpClient(
        on_connection_attempt=lambda conn: conn.respond_with_success(),
        on_request=capture_and_respond(captured_requests, 201, {}),
    )
    client = rest_client(mock_http)
    channel = client.channels.get(channel_name)

    await channel.annotations.publish(
        'msg-serial-1',
        Annotation(type='com.example.data', data={'key': 'value', 'nested': {'a': 1}}),
    )

    body = published_annotations(captured_requests[0])
    annotation = body[0]

    # JSON data should be encoded as a string with encoding field
    assert isinstance(annotation['data'], str)
    assert annotation['encoding'] == 'json'
    assert json.loads(annotation['data']) == {'key': 'value', 'nested': {'a': 1}}


# UTS: rest/unit/RSAN1c4/idempotent-id-generated-0
async def test_rsan1c4_idempotent_id_generated():
    channel_name = f'test-RSAN1c4-enabled-{random_id()}'
    captured_requests = []
    mock_http = MockHttpClient(
        on_connection_attempt=lambda conn: conn.respond_with_success(),
        on_request=capture_and_respond(captured_requests, 201, {}),
    )
    client = rest_client(mock_http, idempotent_rest_publishing=True)
    channel = client.channels.get(channel_name)

    await channel.annotations.publish(
        'msg-serial-1',
        Annotation(type='com.example.reaction'),
    )

    body = published_annotations(captured_requests[0])
    annotation = body[0]

    assert 'id' in annotation
    annotation_id = annotation['id']

    # Format: <base64>:0
    parts = annotation_id.split(':')
    assert len(parts) == 2
    # UTS SPEC ERROR: RSAN1c4 - the spec asserts the random part matches "[A-Za-z0-9_-]+",
    # the URL-safe base64 alphabet, but the features spec requires only "base64-encoding a
    # sequence of at least 9 bytes"; standard base64 also emits '+' and '/', so the spec's
    # pattern rejects roughly a quarter of conforming ids at random.
    assert re.fullmatch(r'[A-Za-z0-9+/=_-]+', parts[0])
    assert len(parts[0]) >= 12  # At least 9 bytes base64 encoded
    assert parts[1] == '0'


# UTS: rest/unit/RSAN1c4/idempotent-id-not-generated-1
async def test_rsan1c4_idempotent_id_not_generated():
    channel_name = f'test-RSAN1c4-disabled-{random_id()}'
    captured_requests = []
    mock_http = MockHttpClient(
        on_connection_attempt=lambda conn: conn.respond_with_success(),
        on_request=capture_and_respond(captured_requests, 201, {}),
    )
    client = rest_client(mock_http, idempotent_rest_publishing=False)
    channel = client.channels.get(channel_name)

    await channel.annotations.publish(
        'msg-serial-1',
        Annotation(type='com.example.reaction'),
    )

    body = published_annotations(captured_requests[0])
    annotation = body[0]

    assert 'id' not in annotation


# NOTE: this section of the specification carries no Test ID; the one below is inferred.
# UTS: rest/unit/RSAN2a/delete-post-annotation-delete-0
async def test_rsan2a_delete_post_annotation_delete():
    channel_name = f'test-RSAN2-delete-{random_id()}'
    captured_requests = []
    mock_http = MockHttpClient(
        on_connection_attempt=lambda conn: conn.respond_with_success(),
        on_request=capture_and_respond(captured_requests, 201, {}),
    )
    client = rest_client(mock_http)
    channel = client.channels.get(channel_name)

    await channel.annotations.delete(
        'msg-serial-1',
        Annotation(type='com.example.reaction', name='like'),
    )

    request = captured_requests[0]
    assert request.method == 'POST'
    assert request.url.path == f'/channels/{channel_name}/messages/msg-serial-1/annotations'

    body = published_annotations(request)
    assert isinstance(body, list)
    assert len(body) == 1

    annotation = body[0]
    assert annotation['action'] == 1  # ANNOTATION_DELETE numeric value
    assert annotation['messageSerial'] == 'msg-serial-1'
    assert annotation['type'] == 'com.example.reaction'
    assert annotation['name'] == 'like'


# NOTE: this section of the specification carries no Test ID; the one below is inferred.
# UTS: rest/unit/RSAN3b/get-sends-get-0
async def test_rsan3b_get_sends_get():
    channel_name = f'test-RSAN3-get-{random_id()}'
    captured_requests = []
    mock_http = MockHttpClient(
        on_connection_attempt=lambda conn: conn.respond_with_success(),
        on_request=capture_and_respond(captured_requests, 200, [
            {
                'id': 'ann-1',
                'action': 0,
                'type': 'com.example.reaction',
                'name': 'like',
                'clientId': 'user-1',
                'serial': 'ann-serial-1',
                'messageSerial': 'msg-serial-1',
                'timestamp': 1700000000000,
            },
        ]),
    )
    client = rest_client(mock_http)
    channel = client.channels.get(channel_name)

    await channel.annotations.get('msg-serial-1')

    request = captured_requests[0]
    assert request.method == 'GET'
    assert request.url.path == f'/channels/{channel_name}/messages/msg-serial-1/annotations'


# NOTE: this section of the specification carries no Test ID; the one below is inferred.
# UTS: rest/unit/RSAN3c/get-returns-paginated-annotations-0
async def test_rsan3c_get_returns_paginated_annotations():
    channel_name = f'test-RSAN3c-{random_id()}'
    mock_http = MockHttpClient(
        on_connection_attempt=lambda conn: conn.respond_with_success(),
        on_request=lambda request: request.respond_with(200, [
            {
                'id': 'ann-1',
                'action': 0,
                'type': 'com.example.reaction',
                'name': 'like',
                'clientId': 'user-1',
                'count': 1,
                'data': 'thumbs-up',
                'serial': 'ann-serial-1',
                'messageSerial': 'msg-serial-1',
                'timestamp': 1700000000000,
                'extras': {'custom': 'metadata'},
            },
            {
                'id': 'ann-2',
                'action': 0,
                'type': 'com.example.reaction',
                'name': 'heart',
                'clientId': 'user-2',
                'serial': 'ann-serial-2',
                'messageSerial': 'msg-serial-1',
                'timestamp': 1700000001000,
            },
        ]),
    )
    client = rest_client(mock_http)
    channel = client.channels.get(channel_name)

    result = await channel.annotations.get('msg-serial-1')

    assert isinstance(result, PaginatedResult)
    assert len(result.items) == 2

    ann1 = result.items[0]
    assert isinstance(ann1, Annotation)
    assert ann1.id == 'ann-1'
    assert ann1.action == AnnotationAction.ANNOTATION_CREATE
    assert ann1.type == 'com.example.reaction'
    assert ann1.name == 'like'
    assert ann1.client_id == 'user-1'
    assert ann1.count == 1
    assert ann1.data == 'thumbs-up'
    assert ann1.serial == 'ann-serial-1'
    assert ann1.message_serial == 'msg-serial-1'
    assert ann1.timestamp == 1700000000000
    assert ann1.extras['custom'] == 'metadata'

    ann2 = result.items[1]
    assert ann2.name == 'heart'
    assert ann2.client_id == 'user-2'


# NOTE: this section of the specification carries no Test ID; the one below is inferred.
# UTS: rest/unit/RSAN3b/get-params-querystring-1
# DEVIATION: see the report accompanying this suite. RSAN3b requires any params to reach
# the querystring; `RestAnnotations.get` hands them to `format_params`, which compares
# `limit` against 1000 without coercing it, so the spec's stringified {"limit": "50"}
# raises TypeError: '>' not supported between instances of 'str' and 'int'. An integer
# limit, and string values for every other param, reach the querystring correctly.
@deviation
async def test_rsan3b_get_params_querystring():
    channel_name = f'test-RSAN3b-params-{random_id()}'
    captured_requests = []
    mock_http = MockHttpClient(
        on_connection_attempt=lambda conn: conn.respond_with_success(),
        on_request=capture_and_respond(captured_requests, 200, []),
    )
    client = rest_client(mock_http)
    channel = client.channels.get(channel_name)

    await channel.annotations.get('msg-serial-1', params={'limit': '50'})

    request = captured_requests[0]
    assert request.url.query_params['limit'] == '50'
