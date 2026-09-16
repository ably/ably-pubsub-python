"""Derived from uts/rest/unit/auth/client_id.md in ably/specification.

Spec points: RSA7, RSA7a, RSA7b, RSA7c, RSA12, RSA12a, RSA12b, RSA15, RSA15a, RSA15b, RSA15c
"""

import time
from urllib.parse import parse_qsl

import pytest

from ably.types.tokendetails import TokenDetails
from ably.util.exceptions import AblyException, IncompatibleClientIdException
from test.uts.helpers.client import rest_client
from test.uts.helpers.deviations import deviation
from test.uts.helpers.mock_http import MockHttpClient

# `channels.get(name).status()` walks status.occupancy.metrics unguarded, so the
# specification's shorter `{"channelId": ..., "status": {"isActive": true}}` body
# cannot be decoded. The extra nesting carries no meaning for these assertions.
CHANNEL_DETAILS_BODY = {
    'channelId': 'test',
    'status': {
        'isActive': True,
        'occupancy': {
            'metrics': {
                'connections': 0,
                'presenceConnections': 0,
                'presenceMembers': 0,
                'presenceSubscribers': 0,
                'publishers': 0,
                'subscribers': 0,
            },
        },
    },
}


def now():
    return int(time.time() * 1000)


def channel_details_mock():
    return MockHttpClient(
        on_connection_attempt=lambda conn: conn.respond_with_success(),
        on_request=lambda request: request.respond_with(200, CHANNEL_DETAILS_BODY),
    )


# UTS: rest/unit/RSA7a/clientid-from-options-0
async def test_rsa7a_clientid_from_options():
    client = rest_client(channel_details_mock(), key='appId.keyId:keySecret', client_id='my-client-id')

    assert client.auth.client_id == 'my-client-id'


# UTS: rest/unit/RSA7b/clientid-from-token-details-0
async def test_rsa7b_clientid_from_token_details():
    client = rest_client(channel_details_mock(), token_details=TokenDetails(
        token='token-with-clientId',
        expires=now() + 3600000,
        client_id='token-client-id',
    ))

    assert client.auth.client_id == 'token-client-id'


# UTS: rest/unit/RSA7b/clientid-from-callback-token-1
async def test_rsa7b_clientid_from_callback_token():
    async def auth_callback(params):
        return TokenDetails(
            token='callback-token',
            expires=now() + 3600000,
            client_id='callback-client-id',
        )

    client = rest_client(channel_details_mock(), auth_callback=auth_callback)

    await client.channels.get('test').status()

    assert client.auth.client_id == 'callback-client-id'


# UTS: rest/unit/RSA7c/clientid-null-unidentified-0
async def test_rsa7c_clientid_null_unidentified():
    client = rest_client(channel_details_mock(), key='appId.keyId:keySecret')

    assert client.auth.client_id is None


# UTS: rest/unit/RSA7c/clientid-null-unidentified-token-1
async def test_rsa7c_clientid_null_unidentified_token():
    client = rest_client(channel_details_mock(), token_details=TokenDetails(
        token='token-without-clientId',
        expires=now() + 3600000,
    ))

    assert client.auth.client_id is None


# UTS: rest/unit/RSA12a/clientid-passed-to-callback-0
async def test_rsa12a_clientid_passed_to_callback():
    received_params = []

    async def mock_auth_callback(params):
        received_params.append(params)
        return TokenDetails(token='tok', expires=now() + 3600000)

    client = rest_client(channel_details_mock(), auth_callback=mock_auth_callback,
                         client_id='library-client-id')

    # DEVIATION: the spec expects the operation to succeed. The returned token
    # carries no clientId, which RSA15a leaves unconstrained (only a non-wildcard
    # token clientId has to match ClientOptions), but Auth._configure_client_id
    # reads the absent value as an attempt to change the configured clientId and
    # raises 40102.
    with pytest.raises(IncompatibleClientIdException) as excinfo:
        await client.channels.get('test').status()

    assert excinfo.value.code == 40102

    # The spec's own assertions, which hold: the clientId reached the callback.
    # ably-python passes TokenParams as a dict with snake_case keys.
    assert len(received_params) >= 1
    assert received_params[0]['client_id'] == 'library-client-id'


# UTS: rest/unit/RSA12b/clientid-sent-to-authurl-0
# DEVIATION: two departures, either of which alone fails this test.
#  - RSA8c takes a JSON auth_url response to be "a TokenRequest or TokenDetails
#    object". ably-python recognises TokenDetails only when the payload carries
#    `issued` (ably/rest/auth.py, Auth.request_token), so `{"token": ..., "expires": ...}`
#    is read as a TokenRequest and rejected as 40170 before `status()` returns.
#  - RSA8c1a sends the TokenParams as query params under their wire names.
#    ably-python passes its internal snake_case dict straight through
#    (`token_params['client_id']` in Auth._ensure_valid_auth_credentials), so the
#    auth_url receives `client_id`, not `clientId`.
@deviation
async def test_rsa12b_clientid_sent_to_authurl():
    captured_requests = []

    def on_request(request):
        captured_requests.append(request)
        if request.url.host == 'auth.example.com':
            request.respond_with(200, {'token': 'url-token', 'expires': now() + 3600000},
                                 {'Content-Type': 'application/json'})
        else:
            request.respond_with(200, CHANNEL_DETAILS_BODY)

    mock_http = MockHttpClient(
        on_connection_attempt=lambda conn: conn.respond_with_success(),
        on_request=on_request,
    )
    client = rest_client(mock_http, auth_url='https://auth.example.com/token',
                         client_id='url-client-id')

    await client.channels.get('test').status()

    auth_request = captured_requests[0]
    assert auth_request.url.host == 'auth.example.com'

    if auth_request.method == 'GET':
        assert auth_request.url.query_params['clientId'] == 'url-client-id'
    else:
        body_params = dict(parse_qsl(auth_request.body.decode('utf-8')))
        assert body_params['clientId'] == 'url-client-id'


# UTS: rest/unit/RSA7/clientid-updated-after-authorize-0
async def test_rsa7_clientid_updated_after_authorize():
    token_count = [0]

    async def mock_auth_callback(params):
        token_count[0] += 1
        return TokenDetails(
            token=f'token-{token_count[0]}',
            expires=now() + 3600000,
            client_id=f'client-{token_count[0]}',
        )

    client = rest_client(channel_details_mock(), auth_callback=mock_auth_callback)

    await client.channels.get('test').status()

    assert client.auth.client_id == 'client-1'

    # DEVIATION: the spec expects auth.client_id to become 'client-2'. ably-python
    # treats the clientId as immutable once a token has established one, so a
    # second token naming a different clientId is rejected with 40102, even though
    # ClientOptions named no clientId to conflict with.
    with pytest.raises(IncompatibleClientIdException) as excinfo:
        await client.auth.authorize()

    assert excinfo.value.code == 40102
    assert client.auth.client_id == 'client-1'


# UTS: rest/unit/RSA12/wildcard-clientid-0
async def test_rsa12_wildcard_clientid():
    client = rest_client(channel_details_mock(), token_details=TokenDetails(
        token='wildcard-token',
        expires=now() + 3600000,
        client_id='*',
    ))

    assert client.auth.client_id == '*'


# UTS: rest/unit/RSA7/clientid-mismatch-error-1
@deviation
async def test_rsa7_clientid_mismatch_error():
    # Case 2 of the spec's table: ClientOptions 'client-a' against a token
    # naming 'client-b'. ably-python never compares the two for a statically
    # supplied TokenDetails, so no error is reported at construction or at use.
    client = rest_client(channel_details_mock(), client_id='client-a',
                         token_details=TokenDetails(
                             token='mismatched-token',
                             expires=now() + 3600000,
                             client_id='client-b',
                         ))

    with pytest.raises(AblyException) as excinfo:
        await client.channels.get('test').status()

    message = excinfo.value.message or ''
    assert 'clientId' in message or 'mismatch' in message


# UTS: rest/unit/RSA15a/token-clientid-must-match-0
@deviation
async def test_rsa15a_token_clientid_must_match():
    client_match = rest_client(channel_details_mock(), client_id='my-client',
                               token_details=TokenDetails(
                                   token='matching-token',
                                   expires=now() + 3600000,
                                   client_id='my-client',
                               ))

    assert client_match.auth.client_id == 'my-client'

    # ably-python constructs this client without complaint.
    with pytest.raises(AblyException) as excinfo:
        rest_client(channel_details_mock(), client_id='my-client',
                    token_details=TokenDetails(
                        token='mismatched-token',
                        expires=now() + 3600000,
                        client_id='other-client',
                    ))

    assert excinfo.value.code == 40102


# UTS: rest/unit/RSA15b/wildcard-token-permits-any-0
async def test_rsa15b_wildcard_token_permits_any():
    client = rest_client(channel_details_mock(), client_id='any-client',
                         token_details=TokenDetails(
                             token='wildcard-token',
                             expires=now() + 3600000,
                             client_id='*',
                         ))

    assert client.auth.client_id == 'any-client'


# UTS: rest/unit/RSA15c/incompatible-clientid-error-0
@deviation
async def test_rsa15c_incompatible_clientid_error():
    # The spec defers to the RSA15a mismatch case: a REST operation under a
    # TokenDetails whose clientId is incompatible must fail with code 40102.
    # ably-python performs the operation instead.
    client = rest_client(channel_details_mock(), client_id='client-a',
                         token_details=TokenDetails(
                             token='incompatible-token',
                             expires=now() + 3600000,
                             client_id='client-b',
                         ))

    with pytest.raises(AblyException) as excinfo:
        await client.channels.get('test').status()

    assert excinfo.value.code == 40102
