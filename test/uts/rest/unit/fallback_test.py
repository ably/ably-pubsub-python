"""Derived from uts/rest/unit/fallback.md in ably/specification.

Spec points: RSC15, RSC15a, RSC15f, RSC15j, RSC15l, RSC15m, REC1, REC1a, REC1b, REC1b1,
REC1b2, REC1b3, REC1b4, REC1c, REC1c1, REC1c2, REC1d, REC1d1, REC1d2, REC2, REC2a, REC2a1,
REC2a2, REC2b, REC2c, REC2c1, REC2c2, REC2c3, REC2c4, REC2c5, REC2c6, REC3, REC3a, REC3b
"""

import asyncio

import pytest

from ably.util.exceptions import AblyException
from test.uts.helpers.client import rest_client
from test.uts.helpers.mock_http import MockHttpClient

SERVER_TIME_MS = 1234567890000

# The /time endpoint answers with an array. The spec writes `{ "time": ... }` in its mock
# setups, which is not the wire format the endpoint uses, so the array is used here.
TIME_BODY = [SERVER_TIME_MS]

PRIMARY_HOST = 'main.realtime.ably.net'


def fallback_hosts_for(root, suffix='fallback.ably-realtime.com'):
    return [f'{root}.{letter}.{suffix}' for letter in 'abcde']


DEFAULT_FALLBACK_HOSTS = fallback_hosts_for('main')


def error_body(status):
    """An error body of the shape ably-python decodes.

    The spec writes `{ "error": { "code": ... } }`. ably-python reads `message` and
    `statusCode` from the error too, and without them reports 500/50000 regardless of
    the response status, so the full error object is sent.
    """
    return {'error': {'message': f'Error {status}', 'code': status * 100, 'statusCode': status}}


def connect_successfully(conn):
    conn.respond_with_success()


def new_mock():
    return MockHttpClient(on_connection_attempt=connect_successfully)


# UTS: rest/unit/RSC15m/no-fallback-empty-hosts-0
async def test_rsc15m_no_fallback_empty_hosts():
    mock_http = new_mock()
    mock_http.queue_response(500, error_body(500))

    client = rest_client(mock_http, fallback_hosts=[])

    with pytest.raises(AblyException) as excinfo:
        await client.time()

    assert len(mock_http.captured_requests) == 1
    assert excinfo.value.status_code == 500


# UTS: rest/unit/RSC15a/fallback-random-order-0
async def test_rsc15a_fallback_random_order():
    mock_http = new_mock()
    # All requests fail to test full fallback sequence
    mock_http.queue_responses(count=6, status=500, body=error_body(500))

    client = rest_client(mock_http)

    with pytest.raises(AblyException):
        await client.time()

    requests = mock_http.captured_requests

    assert requests[0].url.host == PRIMARY_HOST

    fallback_hosts_used = [r.url.host for r in requests[1:]]

    assert len(fallback_hosts_used) > 0
    assert all(host in DEFAULT_FALLBACK_HOSTS for host in fallback_hosts_used)
    assert len(set(fallback_hosts_used)) == len(fallback_hosts_used)

    # NOTE: the spec queues six responses, for the primary and all five fallbacks.
    # ably-python truncates the host list to http_max_retry_count (3 by default), so
    # the primary and two fallbacks are tried.
    assert len(requests) == 3

    # The spec leaves verifying randomness to the implementation. Ordering is drawn once
    # per client, so several clients are built and their host orders compared.
    orders = set()
    for _ in range(20):
        orders.add(tuple(rest_client(new_mock()).options.get_hosts()))
    assert len(orders) > 1


# UTS: rest/unit/RSC15l/qualifying-errors-trigger-fallback-0
async def test_rsc15l_qualifying_errors_trigger_fallback_http_status_codes():
    for status in (500, 501, 502, 503, 504):
        mock_http = new_mock()
        mock_http.queue_response(status, error_body(status))
        mock_http.queue_response(200, TIME_BODY)

        client = rest_client(mock_http)

        await client.time()

        assert len(mock_http.captured_requests) == 2, status
        assert mock_http.captured_requests[1].url.host != mock_http.captured_requests[0].url.host


# UTS: rest/unit/RSC15l/qualifying-errors-trigger-fallback-0
async def test_rsc15l_qualifying_errors_trigger_fallback_non_retryable_statuses():
    for status in (400, 401, 404):
        mock_http = new_mock()
        mock_http.queue_response(status, error_body(status))

        client = rest_client(mock_http)

        with pytest.raises(AblyException):
            await client.time()

        # Should NOT have retried
        assert len(mock_http.captured_requests) == 1, status


# UTS: rest/unit/RSC15l/qualifying-errors-trigger-fallback-0
async def test_rsc15l_qualifying_errors_trigger_fallback_request_timeout():
    mock_http = new_mock()
    mock_http.queue_timeout()
    mock_http.queue_response(200, TIME_BODY)

    # The spec sets httpRequestTimeout to 1000; ably-python takes seconds
    client = rest_client(mock_http, http_request_timeout=1)

    await client.time()

    assert len(mock_http.captured_requests) == 2


# UTS: rest/unit/RSC15l4/cloudfront-error-triggers-fallback-0
async def test_rsc15l4_cloudfront_error_triggers_fallback():
    mock_http = new_mock()
    # NOTE: the spec's body is `{ "error": "Forbidden" }`. ably-python indexes into the
    # error object while decoding, so a string there raises TypeError before the
    # CloudFront check is reached; a full error object is sent instead.
    mock_http.queue_response(403, error_body(403), headers={'Server': 'CloudFront'})
    mock_http.queue_response(200, TIME_BODY)

    client = rest_client(mock_http)

    await client.time()

    assert len(mock_http.captured_requests) == 2
    assert mock_http.captured_requests[0].url.host == PRIMARY_HOST
    assert mock_http.captured_requests[1].url.host != PRIMARY_HOST


# UTS: rest/unit/RSC15l/connection-refused-fallback-0
async def test_rsc15l_connection_refused_fallback():
    request_count = 0

    def on_connection_attempt(conn):
        nonlocal request_count
        request_count += 1
        if request_count == 1:
            # First attempt (primary host) - connection refused
            conn.respond_with_refused()
        else:
            # Fallback succeeds
            conn.respond_with_success()

    mock_http = MockHttpClient(
        on_connection_attempt=on_connection_attempt,
        on_request=lambda req: req.respond_with(200, TIME_BODY),
    )
    client = rest_client(mock_http)

    result = await client.time()

    # Should have succeeded on fallback
    assert result == SERVER_TIME_MS
    assert request_count == 2


# UTS: rest/unit/RSC15l/dns-error-fallback-1
async def test_rsc15l_dns_error_fallback():
    request_count = 0

    def on_connection_attempt(conn):
        nonlocal request_count
        request_count += 1
        if request_count == 1:
            # First attempt - DNS failure
            conn.respond_with_dns_error()
        else:
            # Fallback succeeds
            conn.respond_with_success()

    mock_http = MockHttpClient(
        on_connection_attempt=on_connection_attempt,
        on_request=lambda req: req.respond_with(200, TIME_BODY),
    )
    client = rest_client(mock_http)

    result = await client.time()

    assert result == SERVER_TIME_MS
    assert request_count == 2


# UTS: rest/unit/RSC15l/connection-timeout-fallback-2
async def test_rsc15l_connection_timeout_fallback():
    request_count = 0

    def on_connection_attempt(conn):
        nonlocal request_count
        request_count += 1
        if request_count == 1:
            # First attempt - connection timeout
            conn.respond_with_timeout()
        else:
            # Fallback succeeds
            conn.respond_with_success()

    mock_http = MockHttpClient(
        on_connection_attempt=on_connection_attempt,
        on_request=lambda req: req.respond_with(200, TIME_BODY),
    )
    client = rest_client(mock_http, http_request_timeout=1)

    result = await client.time()

    assert result == SERVER_TIME_MS
    assert request_count == 2


# UTS: rest/unit/RSC15l/request-timeout-fallback-3
async def test_rsc15l_request_timeout_fallback():
    request_count = 0
    captured_hosts = []

    def on_connection_attempt(conn):
        captured_hosts.append(conn.host)
        conn.respond_with_success()

    def on_request(req):
        nonlocal request_count
        request_count += 1
        if request_count == 1:
            # First request times out
            req.respond_with_timeout()
        else:
            # Fallback succeeds
            req.respond_with(200, TIME_BODY)

    mock_http = MockHttpClient(on_connection_attempt=on_connection_attempt, on_request=on_request)
    client = rest_client(mock_http, http_request_timeout=1)

    result = await client.time()

    assert result == SERVER_TIME_MS
    assert request_count == 2
    # Should have tried different hosts
    assert captured_hosts[0] != captured_hosts[1]


# UTS: rest/unit/RSC15l/http-5xx-triggers-fallback-4
async def test_rsc15l_http_5xx_triggers_fallback():
    for status_code in (500, 501, 502, 503, 504):
        request_count = 0

        def on_request(req, status_code=status_code):
            nonlocal request_count
            request_count += 1
            if request_count == 1:
                req.respond_with(status_code, error_body(status_code))
            else:
                req.respond_with(200, TIME_BODY)

        mock_http = MockHttpClient(on_connection_attempt=connect_successfully, on_request=on_request)
        client = rest_client(mock_http)

        result = await client.time()

        assert result == SERVER_TIME_MS, status_code
        assert request_count == 2, status_code


# UTS: rest/unit/RSC15l/http-4xx-no-fallback-5
async def test_rsc15l_http_4xx_no_fallback():
    for status_code in (400, 401, 404):
        request_count = 0

        def on_request(req, status_code=status_code):
            nonlocal request_count
            request_count += 1
            req.respond_with(status_code, error_body(status_code))

        mock_http = MockHttpClient(on_connection_attempt=connect_successfully, on_request=on_request)
        client = rest_client(mock_http)

        with pytest.raises(AblyException) as excinfo:
            await client.time()

        assert excinfo.value.status_code == status_code

        # Should NOT have retried
        assert request_count == 1, status_code


# UTS: rest/unit/RSC15j/host-header-matches-request-0
async def test_rsc15j_host_header_matches_request():
    mock_http = new_mock()
    mock_http.queue_response(500, error_body(500))
    mock_http.queue_response(200, TIME_BODY)

    client = rest_client(mock_http)

    await client.time()

    request_1 = mock_http.captured_requests[0]
    request_2 = mock_http.captured_requests[1]

    # Host header should match the actual host being requested
    assert request_1.headers['Host'] == request_1.url.host
    assert request_2.headers['Host'] == request_2.url.host
    assert request_1.headers['Host'] != request_2.headers['Host']


# UTS: rest/unit/RSC15f/successful-fallback-cached-0
async def test_rsc15f_successful_fallback_cached():
    mock_http = new_mock()
    # First request to primary fails
    mock_http.queue_response_for_host(PRIMARY_HOST, 500, error_body(500))
    # NOTE: the spec queues only for `main.a.fallback.ably-realtime.com`, but RSC15a
    # requires the fallbacks to be tried in random order, so whichever is tried first
    # has to answer. Every fallback is queued twice: once for the fallback request and
    # once for the request that should reuse the cached host.
    for host in DEFAULT_FALLBACK_HOSTS:
        mock_http.queue_response_for_host(host, 200, TIME_BODY)
        mock_http.queue_response_for_host(host, 200, TIME_BODY)

    client = rest_client(mock_http, fallback_retry_timeout=60000)

    # First request - triggers fallback
    await client.time()

    # Second request - should use cached fallback
    await client.time()

    assert len(mock_http.captured_requests) == 3

    # Request 1: primary (failed)
    assert mock_http.captured_requests[0].url.host == PRIMARY_HOST

    # Request 2: fallback (succeeded)
    assert mock_http.captured_requests[1].url.host in DEFAULT_FALLBACK_HOSTS

    # Request 3: cached fallback (no retry to primary)
    assert mock_http.captured_requests[2].url.host == mock_http.captured_requests[1].url.host


# UTS: rest/unit/RSC15f/cached-fallback-expires-1
async def test_rsc15f_cached_fallback_expires():
    mock_http = new_mock()
    mock_http.queue_response_for_host(PRIMARY_HOST, 500, error_body(500))
    for host in DEFAULT_FALLBACK_HOSTS:
        mock_http.queue_response_for_host(host, 200, TIME_BODY)
    # After timeout, primary should be tried again
    mock_http.queue_response_for_host(PRIMARY_HOST, 200, TIME_BODY)

    client = rest_client(mock_http, fallback_retry_timeout=100)

    # First request triggers fallback
    await client.time()

    # The spec advances fake time by 150ms; ably-python reads time.time() directly, so
    # the wait is real and the timeout is kept short.
    await asyncio.sleep(0.15)

    # Next request should try primary again
    await client.time()

    assert len(mock_http.captured_requests) == 3

    # The setup's premise: the first request fell back and pinned that host
    assert mock_http.captured_requests[1].url.host in DEFAULT_FALLBACK_HOSTS

    # After timeout, primary is tried again
    assert mock_http.captured_requests[2].url.host == PRIMARY_HOST


# UTS: rest/unit/RSC15f/expired-not-resurrected-2
async def test_rsc15f_expired_not_resurrected():
    held_request = None
    request_index = 0

    def on_request(req):
        nonlocal held_request, request_index
        request_index += 1
        if request_index == 1:
            # First request to primary - fail to trigger fallback
            req.respond_with(500, error_body(500))
        elif request_index == 2:
            # First fallback - succeed, caches this host
            req.respond_with(200, TIME_BODY)
        elif request_index == 3:
            # Second request goes to cached fallback - hold it (don't respond yet)
            held_request = req
        else:
            # All subsequent requests - succeed
            req.respond_with(200, TIME_BODY)

    mock_http = MockHttpClient(on_connection_attempt=connect_successfully, on_request=on_request)
    client = rest_client(mock_http, fallback_retry_timeout=100)

    # Request 1+2: primary fails -> fallback succeeds -> fallback cached
    await client.time()

    # Request 3: goes to cached fallback, but we hold the response
    request_future = asyncio.ensure_future(client.time())
    while len(mock_http.captured_requests) < 3:
        await asyncio.sleep(0)

    # Advance past fallbackRetryTimeout so the cache expires
    await asyncio.sleep(0.15)

    # Request 4: cache expired -> should try primary again
    await client.time()

    # Now let the held request (3) complete successfully
    held_request.respond_with(200, TIME_BODY)
    await request_future

    # Request 5: the late success from request 3 must NOT have re-pinned the fallback
    await client.time()

    assert len(mock_http.captured_requests) == 5

    # Requests 1+2: primary fail -> fallback success
    assert mock_http.captured_requests[0].url.host == PRIMARY_HOST
    assert mock_http.captured_requests[1].url.host != PRIMARY_HOST

    fallback_host = mock_http.captured_requests[1].url.host

    # Request 3: went to cached fallback (held, not yet responded)
    assert mock_http.captured_requests[2].url.host == fallback_host

    # Request 4: after timeout expiry, primary is tried again
    assert mock_http.captured_requests[3].url.host == PRIMARY_HOST

    # Request 5: late success from request 3 did NOT re-pin fallback
    assert mock_http.captured_requests[4].url.host == PRIMARY_HOST


# UTS: rest/unit/REC1a/default-primary-domain-0
async def test_rec1a_default_primary_domain():
    mock_http = new_mock()
    mock_http.queue_response(200, TIME_BODY)

    client = rest_client(mock_http)

    await client.time()

    assert mock_http.captured_requests[0].url.host == PRIMARY_HOST


# UTS: rest/unit/REC1b2/explicit-hostname-with-period-0
async def test_rec1b2_explicit_hostname_with_period():
    mock_http = new_mock()
    mock_http.queue_response(200, TIME_BODY)

    client = rest_client(mock_http, endpoint='custom.ably.example.com')

    await client.time()

    assert mock_http.captured_requests[0].url.host == 'custom.ably.example.com'


# UTS: rest/unit/REC1b2/endpoint-localhost-1
async def test_rec1b2_endpoint_localhost():
    mock_http = new_mock()
    mock_http.queue_response(200, TIME_BODY)

    client = rest_client(mock_http, endpoint='localhost')

    await client.time()

    assert mock_http.captured_requests[0].url.host == 'localhost'


# UTS: rest/unit/REC1b2/endpoint-ipv6-address-2
async def test_rec1b2_endpoint_ipv6_address():
    mock_http = new_mock()
    mock_http.queue_response(200, TIME_BODY)

    client = rest_client(mock_http, endpoint='::1')

    await client.time()

    # IPv6 addresses may be bracketed in URLs
    assert mock_http.captured_requests[0].url.host in ('::1', '[::1]')


# UTS: rest/unit/REC1b3/nonprod-routing-policy-0
async def test_rec1b3_nonprod_routing_policy():
    mock_http = new_mock()
    mock_http.queue_response(200, TIME_BODY)

    client = rest_client(mock_http, endpoint='nonprod:staging')

    await client.time()

    assert mock_http.captured_requests[0].url.host == 'staging.realtime.ably-nonprod.net'


# UTS: rest/unit/REC1b4/production-routing-policy-0
async def test_rec1b4_production_routing_policy():
    mock_http = new_mock()
    mock_http.queue_response(200, TIME_BODY)

    client = rest_client(mock_http, endpoint='test')

    await client.time()

    assert mock_http.captured_requests[0].url.host == 'test.realtime.ably.net'


# UTS: rest/unit/REC1b1/endpoint-conflicts-environment-0
async def test_rec1b1_endpoint_conflicts_environment():
    with pytest.raises(AblyException) as excinfo:
        rest_client(new_mock(), endpoint='test', environment='production')

    # NOTE: the spec asserts code 40000, or a message containing "invalid" or "conflict".
    # ably-python raises 40106 with "endpoint is incompatible with ...".
    assert excinfo.value.status_code == 400
    assert excinfo.value.code == 40106
    assert 'incompatible' in excinfo.value.message


# UTS: rest/unit/REC1b1/endpoint-conflicts-resthost-1
async def test_rec1b1_endpoint_conflicts_resthost():
    with pytest.raises(AblyException) as excinfo:
        rest_client(new_mock(), endpoint='test', rest_host='custom.host.com')

    # NOTE: the spec asserts code 40000, or a message containing "invalid" or "conflict".
    assert excinfo.value.status_code == 400
    assert excinfo.value.code == 40106
    assert 'incompatible' in excinfo.value.message


# UTS: rest/unit/REC1b1/endpoint-conflicts-realtimehost-2
async def test_rec1b1_endpoint_conflicts_realtimehost():
    with pytest.raises(AblyException) as excinfo:
        rest_client(new_mock(), endpoint='test', realtime_host='custom.realtime.com')

    # NOTE: the spec asserts code 40000, or a message containing "invalid" or "conflict".
    assert excinfo.value.status_code == 400
    assert excinfo.value.code == 40106
    assert 'incompatible' in excinfo.value.message


# UTS: rest/unit/REC1b1/endpoint-conflicts-fallback-default-3
@pytest.mark.skip(
    reason='fallbackHostsUseDefault is optional (features.md TO3k7) and ably-python does not '
           'support it, so REC1b1 does not apply to this option here.')
async def test_rec1b1_endpoint_conflicts_fallback_default():
    with pytest.raises(AblyException):
        rest_client(new_mock(), endpoint='test', fallback_hosts_use_default=True)


# UTS: rest/unit/REC1c2/environment-sets-primary-domain-0
async def test_rec1c2_environment_sets_primary_domain():
    mock_http = new_mock()
    mock_http.queue_response(200, TIME_BODY)

    client = rest_client(mock_http, environment='sandbox')

    await client.time()

    assert mock_http.captured_requests[0].url.host == 'sandbox.realtime.ably.net'


# UTS: rest/unit/REC1c1/environment-conflicts-resthost-0
async def test_rec1c1_environment_conflicts_resthost():
    with pytest.raises(AblyException) as excinfo:
        rest_client(new_mock(), environment='sandbox', rest_host='custom.host.com')

    # NOTE: the spec asserts code 40000, or a message containing "invalid" or "conflict".
    assert excinfo.value.status_code == 400
    assert excinfo.value.code == 40106
    assert 'not both' in excinfo.value.message


# UTS: rest/unit/REC1c1/environment-conflicts-realtimehost-1
async def test_rec1c1_environment_conflicts_realtimehost():
    with pytest.raises(AblyException) as excinfo:
        rest_client(new_mock(), environment='sandbox', realtime_host='custom.realtime.com')

    # NOTE: the spec asserts code 40000, or a message containing "invalid" or "conflict".
    assert excinfo.value.status_code == 400
    assert excinfo.value.code == 40106
    assert 'not both' in excinfo.value.message


# UTS: rest/unit/REC1d1/resthost-sets-primary-domain-0
async def test_rec1d1_resthost_sets_primary_domain():
    mock_http = new_mock()
    mock_http.queue_response(200, TIME_BODY)

    client = rest_client(mock_http, rest_host='custom.rest.example.com')

    await client.time()

    assert mock_http.captured_requests[0].url.host == 'custom.rest.example.com'


# UTS: rest/unit/REC1d2/realtimehost-sets-primary-domain-0
async def test_rec1d2_realtimehost_sets_primary_domain():
    mock_http = new_mock()
    mock_http.queue_response(200, TIME_BODY)

    client = rest_client(mock_http, realtime_host='custom.realtime.example.com')

    await client.time()

    assert mock_http.captured_requests[0].url.host == 'custom.realtime.example.com'


# UTS: rest/unit/REC1d/resthost-precedence-over-realtimehost-0
async def test_rec1d_resthost_precedence_over_realtimehost():
    mock_http = new_mock()
    mock_http.queue_response(200, TIME_BODY)

    client = rest_client(mock_http, rest_host='rest.example.com', realtime_host='realtime.example.com')

    await client.time()

    # REST client uses restHost, not realtimeHost
    assert mock_http.captured_requests[0].url.host == 'rest.example.com'


# UTS: rest/unit/REC2c1/default-fallback-domains-0
async def test_rec2c1_default_fallback_domains():
    mock_http = new_mock()
    # Primary fails
    mock_http.queue_response(500, error_body(500))
    # Fallback succeeds
    mock_http.queue_response(200, TIME_BODY)

    client = rest_client(mock_http)

    await client.time()

    assert len(mock_http.captured_requests) == 2
    assert mock_http.captured_requests[0].url.host == PRIMARY_HOST
    assert mock_http.captured_requests[1].url.host in DEFAULT_FALLBACK_HOSTS


# UTS: rest/unit/REC2a2/custom-fallback-hosts-0
async def test_rec2a2_custom_fallback_hosts():
    mock_http = new_mock()
    mock_http.queue_response(500, error_body(500))
    mock_http.queue_response(200, TIME_BODY)

    custom_fallbacks = ['fb1.example.com', 'fb2.example.com', 'fb3.example.com']
    client = rest_client(mock_http, fallback_hosts=custom_fallbacks)

    await client.time()

    assert len(mock_http.captured_requests) == 2
    assert mock_http.captured_requests[0].url.host == PRIMARY_HOST
    assert mock_http.captured_requests[1].url.host in custom_fallbacks


# UTS: rest/unit/REC2a1/fallback-hosts-conflicts-use-default-0
@pytest.mark.skip(
    reason='fallbackHostsUseDefault is optional (features.md TO3k7) and ably-python does not '
           'support it, so REC2a1 does not apply.')
async def test_rec2a1_fallback_hosts_conflicts_use_default():
    with pytest.raises(AblyException):
        rest_client(new_mock(), fallback_hosts=['fb1.example.com'], fallback_hosts_use_default=True)


# UTS: rest/unit/REC2b/fallback-hosts-use-default-0
@pytest.mark.skip(
    reason='fallbackHostsUseDefault is optional (features.md TO3k7) and ably-python does not '
           'support it, so REC2b does not apply.')
async def test_rec2b_fallback_hosts_use_default():
    mock_http = new_mock()
    mock_http.queue_response(500, error_body(500))
    mock_http.queue_response(200, TIME_BODY)

    client = rest_client(mock_http, rest_host='custom.host.com', fallback_hosts_use_default=True)

    await client.time()

    assert len(mock_http.captured_requests) == 2
    assert mock_http.captured_requests[0].url.host == 'custom.host.com'
    assert mock_http.captured_requests[1].url.host in DEFAULT_FALLBACK_HOSTS


# UTS: rest/unit/REC2c2/explicit-hostname-no-fallbacks-0
async def test_rec2c2_explicit_hostname_no_fallbacks():
    mock_http = new_mock()
    mock_http.queue_response(500, error_body(500))

    client = rest_client(mock_http, endpoint='custom.ably.example.com')

    with pytest.raises(AblyException):
        await client.time()

    # No fallback attempted - only one request
    assert len(mock_http.captured_requests) == 1
    assert mock_http.captured_requests[0].url.host == 'custom.ably.example.com'


# UTS: rest/unit/REC2c3/nonprod-fallback-domains-0
async def test_rec2c3_nonprod_fallback_domains():
    mock_http = new_mock()
    mock_http.queue_response(500, error_body(500))
    mock_http.queue_response(200, TIME_BODY)

    client = rest_client(mock_http, endpoint='nonprod:staging')

    await client.time()

    assert len(mock_http.captured_requests) == 2
    assert mock_http.captured_requests[0].url.host == 'staging.realtime.ably-nonprod.net'

    expected_fallbacks = fallback_hosts_for('staging', 'fallback.ably-realtime-nonprod.com')
    assert mock_http.captured_requests[1].url.host in expected_fallbacks


# UTS: rest/unit/REC2c4/production-endpoint-fallback-domains-0
async def test_rec2c4_production_endpoint_fallback_domains():
    mock_http = new_mock()
    mock_http.queue_response(500, error_body(500))
    mock_http.queue_response(200, TIME_BODY)

    client = rest_client(mock_http, endpoint='test')

    await client.time()

    assert len(mock_http.captured_requests) == 2
    assert mock_http.captured_requests[0].url.host == 'test.realtime.ably.net'
    assert mock_http.captured_requests[1].url.host in fallback_hosts_for('test')


# UTS: rest/unit/REC2c5/production-environment-fallback-domains-0
async def test_rec2c5_production_environment_fallback_domains():
    mock_http = new_mock()
    mock_http.queue_response(500, error_body(500))
    mock_http.queue_response(200, TIME_BODY)

    client = rest_client(mock_http, environment='sandbox')

    await client.time()

    assert len(mock_http.captured_requests) == 2
    assert mock_http.captured_requests[0].url.host == 'sandbox.realtime.ably.net'
    assert mock_http.captured_requests[1].url.host in fallback_hosts_for('sandbox')


# UTS: rest/unit/REC2c6/custom-resthost-no-fallbacks-0
async def test_rec2c6_custom_resthost_no_fallbacks():
    mock_http = new_mock()
    mock_http.queue_response(500, error_body(500))

    client = rest_client(mock_http, rest_host='custom.rest.example.com')

    with pytest.raises(AblyException):
        await client.time()

    # No fallback attempted
    assert len(mock_http.captured_requests) == 1
    assert mock_http.captured_requests[0].url.host == 'custom.rest.example.com'


# UTS: rest/unit/REC2c6/custom-realtimehost-no-fallbacks-1
async def test_rec2c6_custom_realtimehost_no_fallbacks():
    mock_http = new_mock()
    mock_http.queue_response(500, error_body(500))

    client = rest_client(mock_http, realtime_host='custom.realtime.example.com')

    with pytest.raises(AblyException):
        await client.time()

    # No fallback attempted
    assert len(mock_http.captured_requests) == 1
    assert mock_http.captured_requests[0].url.host == 'custom.realtime.example.com'


CONNECTIVITY_CHECK_SKIP = (
    'ably-python has no public connectivity check: ConnectionManager.check_connection is '
    'internal, synchronous, and calls httpx.get directly rather than through the injected '
    'HTTP transport, so the mock cannot serve it.')


# UTS: rest/unit/REC3a/default-connectivity-check-url-0
@pytest.mark.skip(reason=CONNECTIVITY_CHECK_SKIP)
async def test_rec3a_default_connectivity_check_url():
    pass


# UTS: rest/unit/REC3b/custom-connectivity-check-url-0
@pytest.mark.skip(reason=CONNECTIVITY_CHECK_SKIP)
async def test_rec3b_custom_connectivity_check_url():
    pass


# UTS: rest/unit/REC3/connectivity-check-validation-0
@pytest.mark.skip(reason=CONNECTIVITY_CHECK_SKIP)
async def test_rec3_connectivity_check_validation():
    pass
