"""Derived from uts/realtime/integration/proxy/rest_faults.md in ably/specification.

Spec points: RSC10, RSC15m, REC2c2, RTL6

These are the HTTP faults a realtime client's REST side meets, so two of the three tests
drive a `Rest` client through the session and the third drives a realtime and a REST
client through the same one. `endpoint='localhost'` disables the fallback hosts by
itself (REC2c2), so a request the proxy faults is not retried anywhere else and the
event log holds exactly the attempts the SDK made.

Authentication is a callback in every test, because `tls=False` makes the session plain
HTTP and RSC18 has the SDK refuse basic auth over it with 40103 before a request is
written. RSC10 and RSC15m take a token from an inner `Rest` client aimed straight at the
sandbox, so the token request is neither consumed by the waiting rule nor counted among
the requests a test asserts on; RTL6 signs an Ably JWT locally and makes no request at
all. `test/uts/rest/integration/proxy/rest_fallback_test.py` carries the same two
patterns for the REST tier.

`http_response` events carry a `status` and no path, so "the injected response fired" is
read off the responses in the order the proxy sent them.

There is no `## Protocol Variants` section, so these run against JSON only, which the
proxy tier requires in any case.
"""

import pytest

from ably import AblyRest
from ably.realtime.connection import ConnectionState
from ably.types.channelstate import ChannelState
from ably.util.exceptions import AblyException
from test.uts.helpers.client import (
    await_channel_state,
    await_connection_state,
    sandbox_realtime_client,
    sandbox_rest_client,
    wall_clock_poll_until,
)
from test.uts.helpers.sandbox import (
    SANDBOX_ENDPOINT,
    extract_key_name,
    extract_key_secret,
    generate_jwt,
    random_id,
)

# The specification's `AWAIT_STATE ... WITH timeout` and `pollUntil` values, as
# wall-clock seconds.
CONNECT_TIMEOUT = 15.0
ATTACH_TIMEOUT = 10.0
HISTORY_TIMEOUT = 10.0
HISTORY_INTERVAL = 0.5


def token_auth_callback(api_key, invocations=None):
    """The specification's `request_token_from_sandbox`, as an `authCallback`.

    Each invocation builds a `Rest` client of its own pointed straight at the sandbox,
    asks it for a token and closes it, so the token arrives over a connection the proxy
    never sees. A token requested through the client under test would be consumed by the
    rule waiting to fault the first matching request, and would show up in the event log
    beside the requests a test counts.

    `invocations` is the specification's `auth_callback_count`, appended to once per
    call where a test counts renewals.
    """
    async def auth_callback(params):
        if invocations is not None:
            invocations.append(params)
        inner_rest = AblyRest(key=api_key, endpoint=SANDBOX_ENDPOINT)
        try:
            return await inner_rest.auth.request_token()
        finally:
            await inner_rest.close()

    return auth_callback


def jwt_auth_callback(api_key):
    """The specification's JWT `authCallback`, which makes no request of its own."""
    async def auth_callback(params):
        return generate_jwt(extract_key_name(api_key), extract_key_secret(api_key))

    return auth_callback


def http_requests(log, path):
    """The `http_request` events the proxy recorded for `path`."""
    return [event for event in log if event['type'] == 'http_request' and path in event['path']]


def http_responses(log):
    """The `http_response` events the proxy recorded, in the order it sent them."""
    return [event for event in log if event['type'] == 'http_response']


# UTS: realtime/proxy/RSC10/token-renewal-on-401-0
async def test_rsc10_token_renewal_on_401(realtime_sandbox, proxy_session):
    # Track authCallback invocations
    auth_callback_invocations = []

    session = await proxy_session(rules=[{
        'match': {'type': 'http_request', 'pathContains': '/channels/'},
        'action': {
            'type': 'http_respond',
            'status': 401,
            'body': {'error': {'code': 40142, 'statusCode': 401, 'message': 'Token expired'}},
        },
        'times': 1,
        'comment': 'RSC10: Return 401 on first channel request, then passthrough',
    }])

    client = sandbox_rest_client(
        auth_callback=token_auth_callback(realtime_sandbox.key_str, auth_callback_invocations),
        endpoint='localhost',
        port=session.proxy_port,
        tls=False,
        use_binary_protocol=False,
    )

    channel_name = f'test-RSC10-token-renewal-{random_id()}'
    channel = client.channels.get(channel_name)

    # Publish a message -- first request gets 401, SDK renews token, retries.
    # The publish completed successfully: no error raised.
    await channel.publish('test-event', 'hello')

    # authCallback was called at least twice (initial token + renewal after 401)
    assert len(auth_callback_invocations) >= 2

    # Proxy event log shows two HTTP requests to the channel endpoint
    log = await session.get_log()
    assert len(http_requests(log, '/channels/')) >= 2

    # First request was intercepted (got 401), second request passed through (got 2xx)
    responses = http_responses(log)
    assert responses[0]['status'] == 401
    assert responses[1]['status'] in (200, 201)


# UTS: realtime/proxy/RSC15m/http-503-no-fallback-0
async def test_rsc15m_http_503_no_fallback(realtime_sandbox, proxy_session):
    session = await proxy_session(rules=[{
        'match': {'type': 'http_request', 'pathContains': '/channels/'},
        'action': {
            'type': 'http_respond',
            'status': 503,
            'body': {'error': {'code': 50300, 'statusCode': 503,
                               'message': 'Service temporarily unavailable'}},
        },
        'times': 1,
        'comment': 'RSC15m: Return 503 on first channel request',
    }])

    # No fallback_hosts -- endpoint='localhost' disables fallback (REC2c2)
    client = sandbox_rest_client(
        auth_callback=token_auth_callback(realtime_sandbox.key_str),
        endpoint='localhost',
        port=session.proxy_port,
        tls=False,
        use_binary_protocol=False,
    )

    channel_name = f'test-RSC15m-503-error-{random_id()}'
    channel = client.channels.get(channel_name)

    # Try to publish a message -- should fail with 503 error
    with pytest.raises(AblyException) as excinfo:
        await channel.publish('test-event', 'hello')

    # The error propagates to the caller with the correct error code
    assert excinfo.value.code == 50300
    assert excinfo.value.status_code == 503

    # Proxy event log shows only one HTTP request to the channel endpoint
    # (no fallback attempts since endpoint='localhost' disables fallback hosts)
    log = await session.get_log()
    assert len(http_requests(log, '/channels/')) == 1


# UTS: realtime/proxy/RTL6/publish-history-through-proxy-0
async def test_rtl6_publish_history_through_proxy(realtime_sandbox, proxy_session):
    # A session with no rules: pure passthrough, so what this test shows is that the
    # proxy forwards WebSocket and HTTP traffic without interfering with either.
    session = await proxy_session(rules=[])

    realtime_client = sandbox_realtime_client(
        auth_callback=jwt_auth_callback(realtime_sandbox.key_str),
        endpoint='localhost',
        port=session.proxy_port,
        tls=False,
        use_binary_protocol=False,
        auto_connect=False,
    )

    rest_client = sandbox_rest_client(
        auth_callback=jwt_auth_callback(realtime_sandbox.key_str),
        endpoint='localhost',
        port=session.proxy_port,
        tls=False,
        use_binary_protocol=False,
    )

    channel_name = f'test-RTL6-publish-history-{random_id()}'
    realtime_channel = realtime_client.channels.get(channel_name)
    rest_channel = rest_client.channels.get(channel_name)

    # Connect Realtime client through proxy and wait until connected
    realtime_client.connect()
    await await_connection_state(realtime_client, ConnectionState.CONNECTED, CONNECT_TIMEOUT)

    await realtime_channel.attach()
    await await_channel_state(realtime_channel, ChannelState.ATTACHED, ATTACH_TIMEOUT)

    await realtime_channel.publish('test-msg', 'hello world')

    # Poll history via REST until the published message appears. History is eventually
    # consistent so a single immediate read may return nothing, and a `PaginatedResult`
    # is truthy whether or not it holds anything, so the condition answers None until
    # the page has an item.
    async def published_history():
        page = await rest_channel.history()
        return page if len(page.items) > 0 else None

    history = await wall_clock_poll_until(
        published_history, HISTORY_TIMEOUT, 'the published message to reach history',
        HISTORY_INTERVAL)

    # History contains the published message
    assert len(history.items) >= 1

    published_msg = next((m for m in history.items if m.name == 'test-msg'), None)
    assert published_msg is not None
    assert published_msg.data == 'hello world'

    # Proxy event log shows both WebSocket and HTTP traffic
    log = await session.get_log()

    # At least one WebSocket connection was made (Realtime client)
    assert len([event for event in log if event['type'] == 'ws_connect']) >= 1

    # At least one HTTP request was made (REST history call)
    assert len([event for event in log if event['type'] == 'http_request']) >= 1
