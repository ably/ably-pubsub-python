"""Derived from uts/rest/integration/proxy/rest_fallback.md in ably/specification.

Spec points: RSC15l, RSC15l2, RSC15l4, RSL1k4

Every request a test here makes is routed through a `uts-proxy` session, which
answers the first `/time` or first publish with the fault the specification
names and passes everything afterwards through to the sandbox. What each test
is about is therefore what the SDK does next: retry on a fallback host, or
surface the error to the caller.

`endpoint='localhost'` gives both the primary and the fallback host the same
name, so both attempts arrive at the same session port and both appear in the
same event log. A rule carrying `times: 1` fires on the first of them and the
second reaches the sandbox.

There is no `## Protocol Variants` section, so these run against JSON only and
take no `use_binary_protocol`; the proxy reads text frames in any case.
"""

import pytest

from ably import AblyRest
from ably.util.exceptions import AblyException
from test.uts.helpers.client import sandbox_rest_client, wall_clock_poll_until
from test.uts.helpers.deviations import deviation
from test.uts.helpers.sandbox import SANDBOX_ENDPOINT, random_id

# The specification's `non_listening_port`: a port nothing is bound to, so that
# connecting to it is refused rather than answered.
NON_LISTENING_PORT = 19999

# The specification's `httpRequestTimeout: 3000`.
HTTP_REQUEST_TIMEOUT_MS = 3000


def token_auth_callback(api_key):
    """The specification's `token_auth_callback(api_key)`.

    The client under test points at the proxy, where a rule is waiting to fault
    the first request that matches it. A token request made through that client
    would be a request the rule could consume, and would show up in the event
    log beside the requests a test counts. So the callback builds a Rest client
    of its own aimed straight at the sandbox, asks it for a token, and closes
    it: the token arrives over a connection the proxy never sees.
    """
    async def auth_callback(params):
        inner_rest = AblyRest(key=api_key, endpoint=SANDBOX_ENDPOINT)
        try:
            return await inner_rest.auth.request_token()
        finally:
            await inner_rest.close()

    return auth_callback


def http_requests(log, path, method=None):
    """The `http_request` events the proxy recorded for `path`.

    `http_request` events carry the `method` and the `path` the client asked
    for, which is what a specification filters them on.
    """
    return [event for event in log
            if event['type'] == 'http_request'
            and path in event['path']
            and (method is None or event['method'] == method)]


def http_responses(log):
    """The `http_response` events the proxy recorded, in the order it sent them.

    A response event carries `status` and `ruleMatched` and no path, so "the
    first response was the injected one" is read off their order rather than by
    filtering them down to a single endpoint.
    """
    return [event for event in log if event['type'] == 'http_response']


@deviation
# UTS: rest/proxy/RSC15l2/timeout-triggers-fallback-0
async def test_rsc15l2_timeout_triggers_fallback(sandbox, proxy_session):
    session = await proxy_session(rules=[{
        'match': {'type': 'http_request', 'pathContains': '/time'},
        'action': {
            'type': 'http_delay',
            'delayMs': 20000,
        },
        'times': 1,
        'comment': 'RSC15l2: Delay first /time request beyond httpRequestTimeout',
    }])

    client = sandbox_rest_client(
        auth_callback=token_auth_callback(sandbox.key_str),
        endpoint='localhost',
        fallback_hosts=['localhost'],
        port=session.proxy_port,
        tls=False,
        use_binary_protocol=False,
        http_request_timeout=HTTP_REQUEST_TIMEOUT_MS,
    )

    result = await client.time()

    # The request should succeed (retried on fallback after timeout)
    assert isinstance(result, (int, float))
    assert not isinstance(result, bool)

    # Proxy event log shows at least two HTTP requests to /time
    log = await session.get_log()
    assert len(http_requests(log, '/time')) >= 2


# UTS: rest/proxy/RSC15l4/cloudfront-header-fallback-0
async def test_rsc15l4_cloudfront_header_fallback(sandbox, proxy_session):
    session = await proxy_session(rules=[{
        'match': {'type': 'http_request', 'pathContains': '/time'},
        'action': {
            'type': 'http_respond',
            'status': 403,
            'body': {'error': {'message': 'Forbidden', 'code': 40300, 'statusCode': 403}},
            'headers': {'Server': 'CloudFront'},
        },
        'times': 1,
        'comment': 'RSC15l4: CloudFront 403 on first /time request',
    }])

    client = sandbox_rest_client(
        auth_callback=token_auth_callback(sandbox.key_str),
        endpoint='localhost',
        fallback_hosts=['localhost'],
        port=session.proxy_port,
        tls=False,
        use_binary_protocol=False,
    )

    result = await client.time()

    # The request should succeed (retried on fallback after CloudFront error)
    assert isinstance(result, (int, float))
    assert not isinstance(result, bool)

    # Proxy event log shows at least two HTTP requests to /time
    log = await session.get_log()
    assert len(http_requests(log, '/time')) >= 2

    # First response was the injected 403 with CloudFront header
    assert http_responses(log)[0]['status'] == 403


# UTS: rest/proxy/RSC15l/unreachable-endpoint-error-0
async def test_rsc15l_unreachable_endpoint_error(sandbox):
    # No proxy session: the client is pointed at a port nothing is listening
    # on, so the connection is refused before any request is written. The token
    # still comes from the sandbox, so the refusal is the only thing the test
    # provokes.
    client = sandbox_rest_client(
        auth_callback=token_auth_callback(sandbox.key_str),
        endpoint='localhost',
        port=NON_LISTENING_PORT,
        tls=False,
        use_binary_protocol=False,
    )

    with pytest.raises(AblyException) as excinfo:
        await client.time()

    # The error is an ErrorInfo-like object with a statusCode or code
    # (the exact code/statusCode depends on the SDK's HTTP layer, but it must
    # be present and non-null so callers can programmatically handle it).
    # NOTE: the specification leaves the values open. This SDK reports 500 and
    # 50000, the connection error having been wrapped by `catch_all`.
    error = excinfo.value
    assert error is not None
    assert error.status_code is not None or error.code is not None


# UTS: rest/proxy/RSC15l/connection-drop-fallback-1
async def test_rsc15l_connection_drop_fallback(sandbox, proxy_session):
    session = await proxy_session(rules=[{
        'match': {'type': 'http_request', 'pathContains': '/time'},
        'action': {
            'type': 'http_drop',
        },
        'times': 1,
        'comment': 'Drop TCP connection on first /time request (ECONNRESET)',
    }])

    client = sandbox_rest_client(
        auth_callback=token_auth_callback(sandbox.key_str),
        endpoint='localhost',
        fallback_hosts=['localhost'],
        port=session.proxy_port,
        tls=False,
        use_binary_protocol=False,
    )

    result = await client.time()

    # The request should succeed (retried on fallback after connection drop)
    assert isinstance(result, (int, float))
    assert not isinstance(result, bool)

    # Proxy event log shows at least two HTTP requests to /time
    log = await session.get_log()
    assert len(http_requests(log, '/time')) >= 2


# UTS: rest/proxy/RSC15l/http-5xx-json-error-parsed-0
async def test_rsc15l_http_5xx_json_error_parsed(sandbox, proxy_session):
    session = await proxy_session(rules=[{
        'match': {'type': 'http_request', 'pathContains': '/time'},
        'action': {
            'type': 'http_respond',
            'status': 503,
            'body': {'error': {'code': 50300, 'statusCode': 503,
                               'message': 'Service temporarily unavailable'}},
        },
        'times': 1,
        'comment': 'Return 503 with JSON error body on first /time request',
    }])

    # No fallback_hosts -- endpoint='localhost' disables fallback (REC2c2)
    client = sandbox_rest_client(
        auth_callback=token_auth_callback(sandbox.key_str),
        endpoint='localhost',
        port=session.proxy_port,
        tls=False,
        use_binary_protocol=False,
    )

    with pytest.raises(AblyException) as excinfo:
        await client.time()

    # The SDK parsed the error fields from the JSON response body
    error = excinfo.value
    assert error.code == 50300
    assert error.status_code == 503
    assert 'Service temporarily unavailable' in error.message


# UTS: rest/proxy/RSC15l/http-5xx-no-json-synthesized-1
async def test_rsc15l_http_5xx_no_json_synthesized(sandbox, proxy_session):
    session = await proxy_session(rules=[{
        'match': {'type': 'http_request', 'pathContains': '/time'},
        'action': {
            'type': 'http_respond',
            'status': 503,
            'body': {},
        },
        'times': 1,
        'comment': 'Return 503 with empty JSON body (no error field) on first /time request',
    }])

    # No fallback_hosts -- endpoint='localhost' disables fallback (REC2c2)
    client = sandbox_rest_client(
        auth_callback=token_auth_callback(sandbox.key_str),
        endpoint='localhost',
        port=session.proxy_port,
        tls=False,
        use_binary_protocol=False,
    )

    with pytest.raises(AblyException) as excinfo:
        await client.time()

    # The SDK synthesized an error from the HTTP status code
    assert excinfo.value.status_code == 503


# UTS: rest/proxy/RSC15l/http-4xx-not-retried-0
async def test_rsc15l_http_4xx_not_retried(sandbox, proxy_session):
    session = await proxy_session(rules=[{
        'match': {'type': 'http_request', 'pathContains': '/time'},
        'action': {
            'type': 'http_respond',
            'status': 403,
            'body': {'error': {'code': 40300, 'statusCode': 403, 'message': 'Forbidden'}},
        },
        'times': 1,
        'comment': 'Return 403 with JSON error body on first /time request',
    }])

    # Fallback hosts ARE configured -- but 403 should NOT trigger fallback
    client = sandbox_rest_client(
        auth_callback=token_auth_callback(sandbox.key_str),
        endpoint='localhost',
        fallback_hosts=['localhost'],
        port=session.proxy_port,
        tls=False,
        use_binary_protocol=False,
    )

    with pytest.raises(AblyException) as excinfo:
        await client.time()

    # The SDK parsed the error fields from the JSON response body
    error = excinfo.value
    assert error.code == 40300
    assert error.status_code == 403

    # Proxy event log shows exactly 1 HTTP request to /time (no fallback retry)
    log = await session.get_log()
    assert len(http_requests(log, '/time')) == 1


# UTS: rest/proxy/RSL1k4/idempotent-retry-dedup-0
async def test_rsl1k4_idempotent_retry_dedup(sandbox, proxy_session):
    # `http_replace_response` forwards the publish to the sandbox and then
    # discards the sandbox's answer in favour of a 503, so the message is
    # persisted while the client is told it failed. What the test is about is
    # what the server does with the retry that follows: the message carries the
    # id the library generated for it, so the second copy is recognised as the
    # first and dropped.
    session = await proxy_session(rules=[{
        'match': {'type': 'http_request', 'method': 'POST', 'pathContains': '/channels/'},
        'action': {
            'type': 'http_replace_response',
            'status': 503,
            'body': {'error': {'code': 50300, 'statusCode': 503,
                               'message': 'Service temporarily unavailable'}},
        },
        'times': 1,
        'comment': 'RSL1k4: Forward first publish to server, then return fake 503 to client',
    }])

    client = sandbox_rest_client(
        auth_callback=token_auth_callback(sandbox.key_str),
        endpoint='localhost',
        fallback_hosts=['localhost'],
        port=session.proxy_port,
        tls=False,
        use_binary_protocol=False,
        idempotent_rest_publishing=True,
    )

    channel_name = f'test-RSL1k4-idempotent-{random_id()}'
    channel = client.channels.get(channel_name)

    # Publish a message -- first attempt succeeds server-side but client sees
    # 503, SDK retries, server deduplicates the retry.
    # The publish completed successfully: no error thrown.
    await channel.publish(name='test', data='data')

    # Proxy event log shows at least two POST requests to /channels/.
    # Read before history, which is a GET through the same session and so
    # lands in the same log.
    log = await session.get_log()
    assert len(http_requests(log, '/channels/', method='POST')) >= 2

    # Verify via history that only one copy of the message exists
    # (server deduplicated the retry based on the library-generated message id)
    async def published_message():
        page = await channel.history()
        matching = [message for message in page.items
                    if message.name == 'test' and message.data == 'data']
        return matching or None

    matching = await wall_clock_poll_until(
        published_message, description='the published message to reach history')
    assert len(matching) == 1
