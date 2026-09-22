"""Tests for the `mock_http` helper, driven through the REST client it serves."""

import asyncio
import time

import msgpack
import pytest

from ably import AblyRest
from ably.types.testoptions import TestOptions
from ably.util.exceptions import AblyException
from test.uts.helpers.mock_http import MockHttpClient

KEY = 'a.b:c'
SERVER_TIME = 1234567890000

MSGPACK_CONTENT_TYPE = 'application/x-msgpack'
JSON_CONTENT_TYPE = 'application/json'


def rest_client(mock, **kwargs):
    """A REST client whose HTTP calls are served by `mock`."""
    return AblyRest(key=KEY, test_options=TestOptions(http_transport=mock.as_transport()), **kwargs)


async def raw_get(ably, path='/time'):
    """The response to a GET as it came off the wire, before the client interprets it."""
    return await ably.http.make_request('GET', path, skip_auth=True, raise_on_error=False)


def fail_first_connection(failure):
    """A connection handler which fails the first attempt with `failure` and accepts the rest."""
    attempts = []

    def connect(connection):
        attempts.append(connection)
        if len(attempts) == 1:
            getattr(connection, failure)()
        else:
            connection.respond_with_success()

    return connect, attempts


async def wait_for(predicate, timeout=1.0):
    deadline = time.time() + timeout
    while not predicate():
        assert time.time() < deadline, 'Timed out waiting for the client to reach the mock'
        await asyncio.sleep(0.005)


# Dispatch precedence

async def test_a_queued_response_serves_a_request():
    mock = MockHttpClient()
    mock.queue_response(200, [SERVER_TIME])
    ably = rest_client(mock)

    assert await ably.time() == SERVER_TIME
    await ably.close()


async def test_the_on_request_handler_takes_precedence_over_a_queued_response():
    mock = MockHttpClient(on_request=lambda request: request.respond_with(200, [1]))
    mock.queue_response(200, [2])
    ably = rest_client(mock)

    assert await ably.time() == 1

    # The queued stub was left untouched, so it serves the next request
    mock.on_request = None
    assert await ably.time() == 2
    await ably.close()


async def test_an_awaiting_test_takes_precedence_over_the_on_request_handler():
    handled = []
    mock = MockHttpClient(on_request=handled.append)
    mock.queue_response(200, [2])
    ably = rest_client(mock)

    call = asyncio.ensure_future(ably.time())
    request = await mock.await_request(timeout=0.2)
    request.respond_with(200, [SERVER_TIME])

    assert await call == SERVER_TIME
    assert handled == []
    await ably.close()


async def test_an_unconfigured_request_is_answered_with_a_404():
    mock = MockHttpClient()
    ably = rest_client(mock)

    response = await raw_get(ably)

    assert response.status_code == 404
    assert response.to_native() == {'error': {'message': 'No response configured', 'code': 40400}}
    await ably.close()


async def test_a_connection_succeeds_by_default():
    mock = MockHttpClient()
    mock.queue_response(200, [SERVER_TIME])
    ably = rest_client(mock)

    assert await ably.time() == SERVER_TIME
    assert len(mock.captured_requests) == 1
    await ably.close()


async def test_the_on_connection_attempt_handler_receives_each_attempt():
    attempts = []

    def connect(connection):
        attempts.append(connection)
        connection.respond_with_success()

    mock = MockHttpClient(on_connection_attempt=connect,
                          on_request=lambda request: request.respond_with(200, [SERVER_TIME]))
    ably = rest_client(mock)
    host = ably.http.get_hosts()[0]

    assert await ably.time() == SERVER_TIME
    assert [connection.host for connection in attempts] == [host]
    await ably.close()


async def test_an_awaiting_test_takes_precedence_over_the_on_connection_attempt_handler():
    handled = []
    mock = MockHttpClient(on_connection_attempt=handled.append,
                          on_request=lambda request: request.respond_with(200, [SERVER_TIME]))
    ably = rest_client(mock)

    call = asyncio.ensure_future(ably.time())
    connection = await mock.await_connection_attempt(timeout=0.2)
    connection.respond_with_success()

    assert await call == SERVER_TIME
    assert handled == []
    await ably.close()


# The two phases of a call

async def test_a_pending_connection_describes_a_tls_target():
    attempts = []

    def connect(connection):
        attempts.append(connection)
        connection.respond_with_success()

    mock = MockHttpClient(on_connection_attempt=connect,
                          on_request=lambda request: request.respond_with(200, [SERVER_TIME]))
    ably = rest_client(mock)
    host = ably.http.get_hosts()[0]
    before = time.time()

    await ably.time()

    connection = attempts[0]
    assert connection.host == host
    assert connection.port == 443
    assert connection.tls is True
    assert before <= connection.timestamp <= time.time()
    await ably.close()


async def test_a_pending_connection_describes_a_non_tls_target():
    attempts = []

    def connect(connection):
        attempts.append(connection)
        connection.respond_with_success()

    mock = MockHttpClient(on_connection_attempt=connect,
                          on_request=lambda request: request.respond_with(200, [SERVER_TIME]))
    ably = AblyRest(token='foo', tls=False, test_options=TestOptions(http_transport=mock.as_transport()))

    await ably.time()

    assert attempts[0].port == 80
    assert attempts[0].tls is False
    assert mock.captured_requests[0].url.scheme == 'http'
    assert mock.captured_requests[0].url.port == 80
    await ably.close()


@pytest.mark.parametrize('failure', ['respond_with_refused', 'respond_with_timeout', 'respond_with_dns_error'])
async def test_a_failed_connection_moves_the_client_to_the_next_host(failure):
    connect, attempts = fail_first_connection(failure)
    mock = MockHttpClient(on_connection_attempt=connect,
                          on_request=lambda request: request.respond_with(200, [SERVER_TIME]))
    ably = rest_client(mock)
    hosts = ably.http.get_hosts()

    assert await ably.time() == SERVER_TIME

    assert [connection.host for connection in attempts] == hosts[:2]
    # A connection that failed never became a request
    assert [request.url.host for request in mock.captured_requests] == [hosts[1]]
    await ably.close()


async def test_a_connection_that_never_succeeds_captures_no_requests():
    attempts = []

    def refuse(connection):
        attempts.append(connection)
        connection.respond_with_refused()

    mock = MockHttpClient(on_connection_attempt=refuse)
    ably = rest_client(mock)
    hosts = ably.http.get_hosts()

    with pytest.raises(AblyException):
        await ably.time()

    assert [connection.host for connection in attempts] == hosts
    assert mock.captured_requests == []
    await ably.close()


# Response body serialisation

async def test_a_native_body_is_msgpack_encoded_for_a_binary_protocol_client():
    mock = MockHttpClient(on_request=lambda request: request.respond_with(200, {'served': 'msgpack'}))
    ably = rest_client(mock)

    response = await raw_get(ably)

    assert response.headers['content-type'] == MSGPACK_CONTENT_TYPE
    assert msgpack.unpackb(response.content) == {'served': 'msgpack'}
    await ably.close()


async def test_a_native_body_is_json_encoded_for_a_text_protocol_client():
    mock = MockHttpClient(on_request=lambda request: request.respond_with(200, {'served': 'json'}))
    ably = rest_client(mock, use_binary_protocol=False)

    response = await raw_get(ably)

    assert response.headers['content-type'] == JSON_CONTENT_TYPE
    assert response.content == b'{"served":"json"}'
    await ably.close()


async def test_an_explicit_json_content_type_overrides_a_binary_protocol_client():
    mock = MockHttpClient(on_request=lambda request: request.respond_with(
        200, [SERVER_TIME], {'Content-Type': JSON_CONTENT_TYPE}))
    ably = rest_client(mock)

    response = await raw_get(ably)

    assert response.headers['content-type'] == JSON_CONTENT_TYPE
    assert response.content == b'[1234567890000]'
    assert response.to_native() == [SERVER_TIME]
    await ably.close()


async def test_an_explicit_msgpack_content_type_overrides_a_text_protocol_client():
    mock = MockHttpClient(on_request=lambda request: request.respond_with(
        200, [SERVER_TIME], {'Content-Type': MSGPACK_CONTENT_TYPE}))
    ably = rest_client(mock, use_binary_protocol=False)

    response = await raw_get(ably)

    assert response.headers['content-type'] == MSGPACK_CONTENT_TYPE
    assert msgpack.unpackb(response.content) == [SERVER_TIME]
    await ably.close()


async def test_a_bytes_body_is_passed_through_untouched():
    packed = msgpack.packb({'clientId': 'alice'}, use_bin_type=False)
    mock = MockHttpClient(on_request=lambda request: request.respond_with(
        200, packed, {'Content-Type': MSGPACK_CONTENT_TYPE}))
    ably = rest_client(mock)

    response = await raw_get(ably)

    assert response.content == packed
    assert response.to_native() == {'clientId': 'alice'}
    await ably.close()


async def test_a_str_body_is_passed_through_as_utf8_without_a_content_type():
    mock = MockHttpClient(on_request=lambda request: request.respond_with(200, 'grüße'))
    ably = rest_client(mock)

    response = await raw_get(ably)

    assert response.content == 'grüße'.encode()
    assert 'content-type' not in response.headers
    await ably.close()


async def test_a_none_body_yields_empty_content():
    mock = MockHttpClient(on_request=lambda request: request.respond_with(204))
    ably = rest_client(mock)

    response = await raw_get(ably)

    assert response.status_code == 204
    assert response.content == b''
    assert response.to_native() is None
    await ably.close()


async def test_an_error_body_surfaces_with_its_own_code_and_message():
    # RSC8: the code and message come from the body, not from the status
    error = msgpack.packb({'error': {'message': 'Token expired', 'code': 40140, 'statusCode': 401}},
                          use_bin_type=False)
    mock = MockHttpClient(on_request=lambda request: request.respond_with(
        401, error, {'Content-Type': MSGPACK_CONTENT_TYPE}))
    ably = rest_client(mock)

    with pytest.raises(AblyException) as exc_info:
        await ably.time()

    assert exc_info.value.code == 40140
    assert exc_info.value.status_code == 401
    assert exc_info.value.message == 'Token expired'
    assert len(mock.captured_requests) == 1
    await ably.close()


async def test_a_serialised_body_is_decoded_by_the_client():
    mock = MockHttpClient(on_request=lambda request: request.respond_with(200, [SERVER_TIME]))
    ably = rest_client(mock)

    assert await ably.time() == SERVER_TIME
    await ably.close()


# The shape of a recorded request

async def test_a_recorded_request_exposes_the_parts_of_its_url():
    mock = MockHttpClient(on_request=lambda request: request.respond_with(200, [SERVER_TIME]))
    ably = rest_client(mock)
    host = ably.http.get_hosts()[0]
    before = time.time()

    await ably.time()

    request = mock.captured_requests[0]
    assert request.method == 'GET'
    assert request.url.scheme == 'https'
    assert request.url.host == host
    assert request.url.port == 443
    assert request.url.path == '/time'
    assert request.path == '/time'
    assert request.url.query_params == {}
    assert str(request.url) == f'https://{host}/time'
    assert before <= request.timestamp <= time.time()
    await ably.close()


async def test_a_recorded_request_exposes_its_query_params():
    mock = MockHttpClient(on_request=lambda request: request.respond_with(200, []))
    ably = rest_client(mock)
    host = ably.http.get_hosts()[0]

    await ably.stats(limit=5, direction='forwards')

    request = mock.captured_requests[0]
    assert request.url.path == '/stats'
    assert request.url.query_params == {'direction': 'forwards', 'limit': '5'}
    assert str(request.url).startswith(f'https://{host}/stats?')
    await ably.close()


async def test_a_recorded_request_carries_the_headers_and_body_the_client_sent():
    mock = MockHttpClient(on_request=lambda request: request.respond_with(200, {'ok': True}))
    ably = rest_client(mock)

    await ably.request('POST', '/echo', version='3', params={'foo': 'bar'}, body={'x': 1})

    request = mock.captured_requests[0]
    assert request.method == 'POST'
    assert request.url.path == '/echo'
    assert request.url.query_params == {'foo': 'bar'}
    assert request.headers['Content-Type'] == MSGPACK_CONTENT_TYPE
    assert request.headers['content-type'] == MSGPACK_CONTENT_TYPE
    assert request.headers['Accept'] == MSGPACK_CONTENT_TYPE
    assert request.headers['Authorization'].startswith('Basic ')
    assert msgpack.unpackb(request.body) == {'x': 1}
    await ably.close()


# Queued responses

async def test_queued_responses_are_consumed_in_order():
    mock = MockHttpClient()
    mock.queue_response(200, [1])
    mock.queue_response(200, [2])
    ably = rest_client(mock)

    assert await ably.time() == 1
    assert await ably.time() == 2
    # The queue is empty again, so the fallback applies
    assert (await raw_get(ably)).status_code == 404
    await ably.close()


async def test_queue_responses_queues_the_same_stub_several_times():
    mock = MockHttpClient()
    mock.queue_responses(count=3, status=200, body=[SERVER_TIME])
    ably = rest_client(mock)

    assert [await ably.time() for _ in range(3)] == [SERVER_TIME] * 3
    assert (await raw_get(ably)).status_code == 404
    await ably.close()


async def test_a_queued_timeout_moves_the_client_to_the_next_host():
    mock = MockHttpClient()
    mock.queue_timeout()
    mock.queue_response(200, [SERVER_TIME])
    ably = rest_client(mock)
    hosts = ably.http.get_hosts()

    assert await ably.time() == SERVER_TIME
    # A timed out request was still made, unlike a failed connection
    assert [request.url.host for request in mock.captured_requests] == hosts[:2]
    await ably.close()


async def test_a_queued_delayed_response_arrives_after_the_given_milliseconds():
    mock = MockHttpClient()
    mock.queue_delayed_response(100, 200, [SERVER_TIME])
    ably = rest_client(mock)

    started = time.time()
    assert await ably.time() == SERVER_TIME
    elapsed = time.time() - started

    assert 0.09 <= elapsed < 1
    await ably.close()


async def test_a_stub_queued_for_a_host_takes_precedence_over_the_queue():
    mock = MockHttpClient()
    ably = rest_client(mock)
    mock.queue_response(200, [2])
    mock.queue_response_for_host(ably.http.get_hosts()[0], 200, [1])

    assert await ably.time() == 1
    assert await ably.time() == 2
    await ably.close()


async def test_stubs_queued_for_one_host_are_consumed_in_order():
    mock = MockHttpClient()
    ably = rest_client(mock)
    host = ably.http.get_hosts()[0]
    mock.queue_response_for_host(host, 200, [1])
    mock.queue_response_for_host(host, 200, [2])

    assert await ably.time() == 1
    assert await ably.time() == 2
    await ably.close()


async def test_a_stub_queued_for_a_url_takes_precedence_over_the_queue():
    mock = MockHttpClient()
    ably = rest_client(mock)
    mock.queue_response(200, [2])
    mock.queue_response_for_url(f'https://{ably.http.get_hosts()[0]}/time', 200, [1])

    assert await ably.time() == 1
    assert await ably.time() == 2
    await ably.close()


# Awaiting an event

async def test_await_request_hands_the_pending_request_to_the_test():
    mock = MockHttpClient()
    ably = rest_client(mock)

    call = asyncio.ensure_future(ably.time())
    request = await mock.await_request(timeout=0.2)

    assert request.url.path == '/time'
    request.respond_with(200, [SERVER_TIME])
    assert await call == SERVER_TIME
    await ably.close()


async def test_await_request_raises_when_no_request_arrives():
    mock = MockHttpClient()

    with pytest.raises(AssertionError, match='^Timeout waiting for request$'):
        await mock.await_request(timeout=0.2)


async def test_await_connection_attempt_hands_the_pending_connection_to_the_test():
    mock = MockHttpClient(on_request=lambda request: request.respond_with(200, [SERVER_TIME]))
    ably = rest_client(mock)
    host = ably.http.get_hosts()[0]

    call = asyncio.ensure_future(ably.time())
    connection = await mock.await_connection_attempt(timeout=0.2)

    assert connection.host == host
    # Nothing is recorded until the connection succeeds
    assert mock.captured_requests == []

    connection.respond_with_success()
    assert await call == SERVER_TIME
    assert len(mock.captured_requests) == 1
    await ably.close()


async def test_await_connection_attempt_raises_when_no_connection_is_attempted():
    mock = MockHttpClient()

    with pytest.raises(AssertionError, match='^Timeout waiting for connection attempt$'):
        await mock.await_connection_attempt(timeout=0.2)


async def test_a_handler_may_hold_a_request_and_respond_to_it_later():
    held = []
    mock = MockHttpClient(on_request=held.append)
    ably = rest_client(mock)

    call = asyncio.ensure_future(ably.time())
    await wait_for(lambda: len(held) == 1)

    # The client waits while the test gets on with something else
    await asyncio.sleep(0.05)
    assert not call.done()

    held[0].respond_with(200, [SERVER_TIME])
    assert await call == SERVER_TIME
    await ably.close()


# Resetting and reassigning

async def test_reset_clears_captured_requests_and_queued_responses():
    mock = MockHttpClient()
    mock.queue_response(200, [SERVER_TIME])
    ably = rest_client(mock)
    await ably.time()
    assert len(mock.captured_requests) == 1

    mock.queue_response(200, [1])
    mock.reset()

    assert mock.captured_requests == []
    assert (await raw_get(ably)).status_code == 404
    await ably.close()


async def test_reset_keeps_the_handlers_in_place():
    attempts = []

    def connect(connection):
        attempts.append(connection)
        connection.respond_with_success()

    mock = MockHttpClient(on_connection_attempt=connect,
                          on_request=lambda request: request.respond_with(200, [SERVER_TIME]))
    ably = rest_client(mock)
    await ably.time()

    mock.reset()

    assert await ably.time() == SERVER_TIME
    assert len(attempts) == 2
    assert len(mock.captured_requests) == 1
    await ably.close()


async def test_reset_drops_a_waiting_test():
    mock = MockHttpClient()
    ably = rest_client(mock)
    waiting = asyncio.ensure_future(mock.await_request(timeout=0.2))
    await asyncio.sleep(0)

    mock.reset()

    assert (await raw_get(ably)).status_code == 404
    with pytest.raises(AssertionError, match='^Timeout waiting for request$'):
        await waiting
    await ably.close()


async def test_the_handlers_can_be_assigned_after_construction():
    mock = MockHttpClient()
    ably = rest_client(mock)

    mock.on_request = lambda request: request.respond_with(200, [SERVER_TIME])
    assert await ably.time() == SERVER_TIME

    mock.on_connection_attempt = lambda connection: connection.respond_with_refused()
    with pytest.raises(AblyException):
        await ably.time()
    await ably.close()


async def test_queue_response_for_url_matches_a_key_written_with_a_default_port():
    mock = MockHttpClient()
    mock.queue_response_for_url('https://main.realtime.ably.net:443/time', 200, [99])
    ably = rest_client(mock)

    assert await ably.time() == 99

    await ably.close()


async def test_a_delayed_response_beyond_the_read_budget_times_out():
    mock = MockHttpClient()
    mock.queue_delayed_response(5000, 200, [1])
    ably = rest_client(mock, http_request_timeout=0.05)

    started = time.monotonic()
    with pytest.raises(AblyException):
        await ably.time()
    elapsed = time.monotonic() - started

    # The client's budget decides when it gives up, not the queued delay
    assert elapsed < 1
    await ably.close()


async def test_a_delayed_response_within_the_read_budget_arrives():
    mock = MockHttpClient()
    mock.queue_delayed_response(20, 200, [7])
    ably = rest_client(mock, http_request_timeout=5)

    assert await ably.time() == 7

    await ably.close()


async def test_a_recorded_url_keeps_the_encoded_path_alongside_the_decoded_one():
    mock = MockHttpClient(on_request=lambda request: request.respond_with(200, []))
    ably = rest_client(mock)

    await ably.channels.get('a/b:c').history()

    url = mock.captured_requests[0].url
    assert url.raw_path == '/channels/a%2Fb:c/messages'
    assert url.path == '/channels/a/b:c/messages'
    await ably.close()
