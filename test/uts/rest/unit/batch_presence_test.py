"""Derived from uts/rest/unit/batch_presence.md in ably/specification.

Spec points: RSC24, BAR2, BGR2, BGF2

NOTE: ably-python has no batch API. `AblyRest` exposes no `batch_presence`, and the package
defines neither `BatchResult`/`BatchPresenceResponse` nor `BatchPresenceSuccessResult`/
`BatchPresenceFailureResult`; the word "batch" appears nowhere under `ably/`. Every test in
this file therefore departs from the specification and is gated behind `RUN_DEVIATIONS`.
Each carries the assertion the spec calls for, written against the name ably-python would
use once RSC24 is implemented, so that dropping the `@deviation` marker is the only change
needed when it is. Today a batch presence query has to be hand-rolled by the caller through
`client.request('GET', '/presence', version=..., params={'channels': ...})`, which returns
an `HttpPaginatedResponse` of raw dicts rather than decoded `PresenceMessage`s, and which
does not raise on an error status.

Counts are read as `success_count` / `failure_count`, the snake_case spelling of BAR2a and
BAR2b, and a success result is told apart from a failure result by which attributes it
carries rather than by `isinstance`, since neither class exists to name.
"""

import pytest

from ably.types.presence import PresenceAction
from ably.util.exceptions import AblyException
from test.uts.helpers.client import rest_client
from test.uts.helpers.deviations import deviation
from test.uts.helpers.mock_http import MockHttpClient


def capture_and_respond(captured_requests, body):
    def on_request(request):
        captured_requests.append(request)
        request.respond_with(200, body)

    return on_request


def respond_with(status, body):
    return lambda request: request.respond_with(status, body)


# UTS: rest/unit/RSC24/get-presence-channels-param-0
@deviation
async def test_rsc24_batch_presence_get_presence_channels_param():
    captured_requests = []
    mock_http = MockHttpClient(
        on_connection_attempt=lambda conn: conn.respond_with_success(),
        on_request=capture_and_respond(captured_requests, {
            'successCount': 2,
            'failureCount': 0,
            'results': [
                {'channel': 'channel-a', 'presence': []},
                {'channel': 'channel-b', 'presence': []},
            ],
        }),
    )
    client = rest_client(mock_http)

    await client.batch_presence(['channel-a', 'channel-b'])

    assert len(captured_requests) == 1
    assert captured_requests[0].method == 'GET'
    assert captured_requests[0].url.path == '/presence'
    assert captured_requests[0].url.query_params['channels'] == 'channel-a,channel-b'


# UTS: rest/unit/RSC24/single-channel-param-0
@deviation
async def test_rsc24_batch_presence_single_channel_param():
    captured_requests = []
    mock_http = MockHttpClient(
        on_connection_attempt=lambda conn: conn.respond_with_success(),
        on_request=capture_and_respond(captured_requests, {
            'successCount': 1,
            'failureCount': 0,
            'results': [
                {'channel': 'my-channel', 'presence': []},
            ],
        }),
    )
    client = rest_client(mock_http)

    await client.batch_presence(['my-channel'])

    assert captured_requests[0].url.query_params['channels'] == 'my-channel'


# UTS: rest/unit/RSC24/special-chars-comma-joined-0
@deviation
async def test_rsc24_batch_presence_special_chars_comma_joined():
    captured_requests = []
    mock_http = MockHttpClient(
        on_connection_attempt=lambda conn: conn.respond_with_success(),
        on_request=capture_and_respond(captured_requests, {
            'successCount': 2,
            'failureCount': 0,
            'results': [
                {'channel': 'foo:bar', 'presence': []},
                {'channel': 'baz/qux', 'presence': []},
            ],
        }),
    )
    client = rest_client(mock_http)

    await client.batch_presence(['foo:bar', 'baz/qux'])

    assert captured_requests[0].url.query_params['channels'] == 'foo:bar,baz/qux'


# UTS: rest/unit/BAR2/mixed-success-failure-counts-0
@deviation
async def test_bar2_batch_presence_mixed_success_failure_counts():
    mock_http = MockHttpClient(
        on_connection_attempt=lambda conn: conn.respond_with_success(),
        on_request=respond_with(200, {
            'successCount': 3,
            'failureCount': 1,
            'results': [
                {'channel': 'ch-1', 'presence': []},
                {'channel': 'ch-2', 'presence': []},
                {'channel': 'ch-3', 'presence': []},
                {
                    'channel': 'ch-4',
                    'error': {'code': 40160, 'statusCode': 401, 'message': 'Not permitted'},
                },
            ],
        }),
    )
    client = rest_client(mock_http)

    result = await client.batch_presence(['ch-1', 'ch-2', 'ch-3', 'ch-4'])

    assert result.success_count == 3
    assert result.failure_count == 1
    assert len(result.results) == 4


# UTS: rest/unit/BAR2/all-success-counts-0
@deviation
async def test_bar2_batch_presence_all_success_counts():
    mock_http = MockHttpClient(
        on_connection_attempt=lambda conn: conn.respond_with_success(),
        on_request=respond_with(200, {
            'successCount': 2,
            'failureCount': 0,
            'results': [
                {'channel': 'ch-a', 'presence': []},
                {'channel': 'ch-b', 'presence': []},
            ],
        }),
    )
    client = rest_client(mock_http)

    result = await client.batch_presence(['ch-a', 'ch-b'])

    assert result.success_count == 2
    assert result.failure_count == 0
    assert len(result.results) == 2


# UTS: rest/unit/BAR2/all-failure-counts-0
@deviation
async def test_bar2_batch_presence_all_failure_counts():
    error = {'code': 40160, 'statusCode': 401, 'message': 'Not permitted'}
    mock_http = MockHttpClient(
        on_connection_attempt=lambda conn: conn.respond_with_success(),
        on_request=respond_with(200, {
            'successCount': 0,
            'failureCount': 2,
            'results': [
                {'channel': 'ch-a', 'error': error},
                {'channel': 'ch-b', 'error': error},
            ],
        }),
    )
    client = rest_client(mock_http)

    result = await client.batch_presence(['ch-a', 'ch-b'])

    assert result.success_count == 0
    assert result.failure_count == 2
    assert len(result.results) == 2


# UTS: rest/unit/BGR2/success-with-members-0
@deviation
async def test_bgr2_batch_presence_success_with_members():
    mock_http = MockHttpClient(
        on_connection_attempt=lambda conn: conn.respond_with_success(),
        on_request=respond_with(200, {
            'successCount': 1,
            'failureCount': 0,
            'results': [
                {
                    'channel': 'my-channel',
                    'presence': [
                        {
                            'clientId': 'client-1',
                            'action': 1,
                            'connectionId': 'conn-abc',
                            'id': 'conn-abc:0:0',
                            'timestamp': 1700000000000,
                            'data': 'hello',
                        },
                        {
                            'clientId': 'client-2',
                            'action': 1,
                            'connectionId': 'conn-def',
                            'id': 'conn-def:0:0',
                            'timestamp': 1700000000000,
                            'data': {'key': 'value'},
                        },
                    ],
                },
            ],
        }),
    )
    client = rest_client(mock_http)

    result = await client.batch_presence(['my-channel'])

    assert len(result.results) == 1

    success = result.results[0]
    assert getattr(success, 'presence', None) is not None
    assert success.channel == 'my-channel'
    assert len(success.presence) == 2

    assert success.presence[0].client_id == 'client-1'
    assert success.presence[0].action == PresenceAction.PRESENT
    assert success.presence[0].connection_id == 'conn-abc'
    assert success.presence[0].data == 'hello'

    assert success.presence[1].client_id == 'client-2'
    assert isinstance(success.presence[1].data, dict)
    assert success.presence[1].data['key'] == 'value'


# UTS: rest/unit/BGR2/success-empty-presence-0
@deviation
async def test_bgr2_batch_presence_success_empty_presence():
    mock_http = MockHttpClient(
        on_connection_attempt=lambda conn: conn.respond_with_success(),
        on_request=respond_with(200, {
            'successCount': 1,
            'failureCount': 0,
            'results': [
                {'channel': 'empty-channel', 'presence': []},
            ],
        }),
    )
    client = rest_client(mock_http)

    result = await client.batch_presence(['empty-channel'])

    success = result.results[0]
    assert getattr(success, 'presence', None) is not None
    assert success.channel == 'empty-channel'
    assert len(success.presence) == 0


# UTS: rest/unit/BGF2/failure-error-details-0
@deviation
async def test_bgf2_batch_presence_failure_error_details():
    mock_http = MockHttpClient(
        on_connection_attempt=lambda conn: conn.respond_with_success(),
        on_request=respond_with(200, {
            'successCount': 0,
            'failureCount': 1,
            'results': [
                {
                    'channel': 'restricted-channel',
                    'error': {
                        'code': 40160,
                        'statusCode': 401,
                        'message': 'Channel operation not permitted',
                    },
                },
            ],
        }),
    )
    client = rest_client(mock_http)

    result = await client.batch_presence(['restricted-channel'])

    assert len(result.results) == 1

    failure = result.results[0]
    assert getattr(failure, 'error', None) is not None
    assert failure.channel == 'restricted-channel'
    assert failure.error.code == 40160
    assert failure.error.status_code == 401
    assert 'not permitted' in failure.error.message


# UTS: rest/unit/RSC24/mixed-success-failure-results-0
@deviation
async def test_rsc24_batch_presence_mixed_success_failure_results():
    mock_http = MockHttpClient(
        on_connection_attempt=lambda conn: conn.respond_with_success(),
        on_request=respond_with(200, {
            'successCount': 1,
            'failureCount': 1,
            'results': [
                {
                    'channel': 'allowed-channel',
                    'presence': [
                        {
                            'clientId': 'user-1',
                            'action': 1,
                            'connectionId': 'conn-1',
                            'id': 'conn-1:0:0',
                            'timestamp': 1700000000000,
                        },
                    ],
                },
                {
                    'channel': 'restricted-channel',
                    'error': {'code': 40160, 'statusCode': 401, 'message': 'Not permitted'},
                },
            ],
        }),
    )
    client = rest_client(mock_http)

    result = await client.batch_presence(['allowed-channel', 'restricted-channel'])

    assert result.success_count == 1
    assert result.failure_count == 1
    assert len(result.results) == 2

    assert getattr(result.results[0], 'presence', None) is not None
    assert result.results[0].channel == 'allowed-channel'
    assert len(result.results[0].presence) == 1
    assert result.results[0].presence[0].client_id == 'user-1'

    assert getattr(result.results[1], 'error', None) is not None
    assert result.results[1].channel == 'restricted-channel'
    assert result.results[1].error.code == 40160


# UTS: rest/unit/RSC24/server-error-propagated-0
@deviation
async def test_rsc24_batch_presence_server_error_propagated():
    mock_http = MockHttpClient(
        on_connection_attempt=lambda conn: conn.respond_with_success(),
        on_request=respond_with(500, {
            'error': {'code': 50000, 'statusCode': 500, 'message': 'Internal error'},
        }),
    )
    client = rest_client(mock_http)

    with pytest.raises(AblyException) as excinfo:
        await client.batch_presence(['any-channel'])

    assert excinfo.value.code == 50000
    assert excinfo.value.status_code == 500


# UTS: rest/unit/RSC24/auth-error-propagated-0
@deviation
async def test_rsc24_batch_presence_auth_error_propagated():
    mock_http = MockHttpClient(
        on_connection_attempt=lambda conn: conn.respond_with_success(),
        on_request=respond_with(401, {
            'error': {'code': 40101, 'statusCode': 401, 'message': 'Invalid credentials'},
        }),
    )
    client = rest_client(mock_http)

    with pytest.raises(AblyException) as excinfo:
        await client.batch_presence(['any-channel'])

    assert excinfo.value.code == 40101
    assert excinfo.value.status_code == 401


# UTS: rest/unit/RSC24/uses-configured-auth-0
@deviation
async def test_rsc24_batch_presence_uses_configured_auth():
    captured_requests = []
    mock_http = MockHttpClient(
        on_connection_attempt=lambda conn: conn.respond_with_success(),
        on_request=capture_and_respond(captured_requests, {
            'successCount': 1,
            'failureCount': 0,
            'results': [
                {'channel': 'ch', 'presence': []},
            ],
        }),
    )
    client = rest_client(mock_http)

    await client.batch_presence(['ch'])

    assert captured_requests[0].headers['Authorization'].startswith('Basic ')
