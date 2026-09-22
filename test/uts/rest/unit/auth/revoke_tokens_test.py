"""Derived from uts/rest/unit/auth/revoke_tokens.md in ably/specification.

Spec points: RSA17, RSA17b, RSA17c, RSA17d, RSA17e, RSA17f, RSA17g, BAR2, TRS2, TRF2

ably-python has no token revocation at all: there is no `Auth#revokeTokens`, no
`TokenRevocationTargetSpecifier`, no `BatchResult` and no
`TokenRevocationSuccessResult`/`TokenRevocationFailureResult`. Every test here is
therefore an env-gated deviation; each fails with `AttributeError` when run with
`RUN_DEVIATIONS=1`. They are written against the API the specification describes,
spelled the way ably-python spells things (`revoke_tokens`, `issued_before`,
`allow_reauth_margin`, `success_count`, `failure_count`, `applies_at`), with the
target specifiers as plain dicts since the specifier type does not exist either.
"""

import json

import msgpack
import pytest

from ably.util.exceptions import AblyException
from test.uts.helpers.client import rest_client
from test.uts.helpers.deviations import deviation
from test.uts.helpers.mock_http import MockHttpClient

KEY = 'appId.keyName:keySecret'

SUCCESS_ALICE = {
    'target': 'clientId:alice',
    'issuedBefore': 1700000000000,
    'appliesAt': 1700000001000,
}


def request_body(request):
    """The specifications' `JSON_PARSE(request.body)`.

    ably-python encodes request bodies as msgpack unless `use_binary_protocol`
    is off, so the wire encoding is taken from the request's own Content-Type.
    """
    if 'msgpack' in request.headers.get('content-type', ''):
        return msgpack.unpackb(request.body)
    return json.loads(request.body)


def capture_and_respond(captured_requests, status=200, body=None):
    def on_request(request):
        captured_requests.append(request)
        request.respond_with(status, [SUCCESS_ALICE] if body is None else body)

    return on_request


# UTS: rest/unit/RSA17g/sends-post-correct-path-0
@deviation
async def test_rsa17g_sends_post_correct_path():
    captured_requests = []
    mock_http = MockHttpClient(
        on_connection_attempt=lambda conn: conn.respond_with_success(),
        on_request=capture_and_respond(captured_requests),
    )
    client = rest_client(mock_http, key=KEY)

    await client.auth.revoke_tokens([{'type': 'clientId', 'value': 'alice'}])

    assert len(captured_requests) == 1
    assert captured_requests[0].method == 'POST'
    assert captured_requests[0].url.path == '/keys/appId.keyName/revokeTokens'


# UTS: rest/unit/RSA17b/single-specifier-targets-0
@deviation
async def test_rsa17b_single_specifier_targets():
    captured_requests = []
    mock_http = MockHttpClient(
        on_connection_attempt=lambda conn: conn.respond_with_success(),
        on_request=capture_and_respond(captured_requests),
    )
    client = rest_client(mock_http, key=KEY)

    await client.auth.revoke_tokens([{'type': 'clientId', 'value': 'alice'}])

    body = request_body(captured_requests[0])
    assert body['targets'] == ['clientId:alice']


# UTS: rest/unit/RSA17b/multiple-specifier-types-1
@deviation
async def test_rsa17b_multiple_specifier_types():
    captured_requests = []
    mock_http = MockHttpClient(
        on_connection_attempt=lambda conn: conn.respond_with_success(),
        on_request=capture_and_respond(captured_requests, body=[
            SUCCESS_ALICE,
            {'target': 'revocationKey:group-1', 'issuedBefore': 1700000000000, 'appliesAt': 1700000001000},
            {'target': 'channel:secret', 'issuedBefore': 1700000000000, 'appliesAt': 1700000001000},
        ]),
    )
    client = rest_client(mock_http, key=KEY)

    await client.auth.revoke_tokens([
        {'type': 'clientId', 'value': 'alice'},
        {'type': 'revocationKey', 'value': 'group-1'},
        {'type': 'channel', 'value': 'secret'},
    ])

    body = request_body(captured_requests[0])
    assert body['targets'] == ['clientId:alice', 'revocationKey:group-1', 'channel:secret']


# UTS: rest/unit/RSA17c/all-success-result-0
@deviation
async def test_rsa17c_all_success_result():
    # UTS SPEC ERROR RSA17c_1 - the setup stubs the legacy plain array while the assertions read
    # the BatchResult envelope the spec's own "Server Response Format" section says is returned.
    mock_http = MockHttpClient(
        on_connection_attempt=lambda conn: conn.respond_with_success(),
        on_request=lambda request: request.respond_with(201, {
            'successCount': 2,
            'failureCount': 0,
            'results': [
                SUCCESS_ALICE,
                {'target': 'clientId:bob', 'issuedBefore': 1700000000000, 'appliesAt': 1700000002000},
            ],
        }),
    )
    client = rest_client(mock_http, key=KEY)

    result = await client.auth.revoke_tokens([
        {'type': 'clientId', 'value': 'alice'},
        {'type': 'clientId', 'value': 'bob'},
    ])

    assert result.success_count == 2
    assert result.failure_count == 0
    assert len(result.results) == 2


# UTS: rest/unit/RSA17c/mixed-success-failure-1
@deviation
async def test_rsa17c_mixed_success_failure():
    mock_http = MockHttpClient(
        on_connection_attempt=lambda conn: conn.respond_with_success(),
        on_request=lambda request: request.respond_with(200, {
            'successCount': 1,
            'failureCount': 1,
            'results': [
                SUCCESS_ALICE,
                {
                    'target': 'invalidType:abc',
                    'error': {'code': 40000, 'statusCode': 400, 'message': 'Invalid target type'},
                },
            ],
        }),
    )
    client = rest_client(mock_http, key=KEY)

    result = await client.auth.revoke_tokens([
        {'type': 'clientId', 'value': 'alice'},
        {'type': 'invalidType', 'value': 'abc'},
    ])

    assert result.success_count == 1
    assert result.failure_count == 1
    assert len(result.results) == 2


# UTS: rest/unit/RSA17c/all-failure-result-2
@deviation
async def test_rsa17c_all_failure_result():
    mock_http = MockHttpClient(
        on_connection_attempt=lambda conn: conn.respond_with_success(),
        on_request=lambda request: request.respond_with(200, {
            'successCount': 0,
            'failureCount': 2,
            'results': [
                {
                    'target': 'invalidType:foo',
                    'error': {'code': 40000, 'statusCode': 400, 'message': 'Invalid target type'},
                },
                {
                    'target': 'invalidType:bar',
                    'error': {'code': 40000, 'statusCode': 400, 'message': 'Invalid target type'},
                },
            ],
        }),
    )
    client = rest_client(mock_http, key=KEY)

    result = await client.auth.revoke_tokens([
        {'type': 'invalidType', 'value': 'foo'},
        {'type': 'invalidType', 'value': 'bar'},
    ])

    assert result.success_count == 0
    assert result.failure_count == 2
    assert len(result.results) == 2


# UTS: rest/unit/TRS2/success-result-attributes-0
@deviation
async def test_trs2_success_result_attributes():
    # UTS SPEC ERROR TRS2_1 - the setup stubs the legacy plain array while the assertions read
    # `result.results`, which only exists on the BatchResult envelope the spec says is returned.
    mock_http = MockHttpClient(
        on_connection_attempt=lambda conn: conn.respond_with_success(),
        on_request=lambda request: request.respond_with(201, {
            'successCount': 1,
            'failureCount': 0,
            'results': [SUCCESS_ALICE],
        }),
    )
    client = rest_client(mock_http, key=KEY)

    result = await client.auth.revoke_tokens([{'type': 'clientId', 'value': 'alice'}])

    # NOTE: the spec asserts `success IS TokenRevocationSuccessResult`. No such type exists in
    # ably-python, so the attributes it defines stand in for the type check.
    success = result.results[0]
    assert success.target == 'clientId:alice'
    assert success.issued_before == 1700000000000
    assert success.applies_at == 1700000001000


# UTS: rest/unit/TRF2/failure-result-attributes-0
@deviation
async def test_trf2_failure_result_attributes():
    mock_http = MockHttpClient(
        on_connection_attempt=lambda conn: conn.respond_with_success(),
        on_request=lambda request: request.respond_with(200, {
            'successCount': 0,
            'failureCount': 1,
            'results': [
                {
                    'target': 'invalidType:abc',
                    'error': {'code': 40000, 'statusCode': 400, 'message': 'Invalid target type'},
                },
            ],
        }),
    )
    client = rest_client(mock_http, key=KEY)

    result = await client.auth.revoke_tokens([{'type': 'invalidType', 'value': 'abc'}])

    # NOTE: the spec asserts `failure IS TokenRevocationFailureResult`; no such type exists in
    # ably-python, so its attributes stand in for the type check.
    failure = result.results[0]
    assert failure.target == 'invalidType:abc'
    assert failure.error.code == 40000
    assert failure.error.status_code == 400
    assert 'Invalid target type' in failure.error.message


# UTS: rest/unit/RSA17d/token-auth-revoke-rejected-0
@deviation
async def test_rsa17d_token_auth_revoke_rejected():
    captured_requests = []
    mock_http = MockHttpClient(
        on_connection_attempt=lambda conn: conn.respond_with_success(),
        on_request=capture_and_respond(captured_requests, body=[]),
    )
    client = rest_client(mock_http, token='a.token.string')

    with pytest.raises(AblyException) as excinfo:
        await client.auth.revoke_tokens([{'type': 'clientId', 'value': 'alice'}])

    assert excinfo.value.code == 40162
    assert excinfo.value.status_code == 401

    assert len(captured_requests) == 0


# UTS: rest/unit/RSA17d/use-token-auth-revoke-rejected-1
@deviation
async def test_rsa17d_use_token_auth_revoke_rejected():
    captured_requests = []
    mock_http = MockHttpClient(
        on_connection_attempt=lambda conn: conn.respond_with_success(),
        on_request=capture_and_respond(captured_requests, body=[]),
    )
    client = rest_client(mock_http, key=KEY, use_token_auth=True)

    with pytest.raises(AblyException) as excinfo:
        await client.auth.revoke_tokens([{'type': 'clientId', 'value': 'alice'}])

    assert excinfo.value.code == 40162
    assert excinfo.value.status_code == 401

    assert len(captured_requests) == 0


# UTS: rest/unit/RSA17e/issued-before-included-0
@deviation
async def test_rsa17e_issued_before_included():
    captured_requests = []
    mock_http = MockHttpClient(
        on_connection_attempt=lambda conn: conn.respond_with_success(),
        on_request=capture_and_respond(captured_requests, body=[
            {'target': 'clientId:alice', 'issuedBefore': 1699999000000, 'appliesAt': 1700000001000},
        ]),
    )
    client = rest_client(mock_http, key=KEY)

    await client.auth.revoke_tokens(
        [{'type': 'clientId', 'value': 'alice'}],
        issued_before=1699999000000,
    )

    body = request_body(captured_requests[0])
    assert body['issuedBefore'] == 1699999000000


# UTS: rest/unit/RSA17e/issued-before-omitted-1
@deviation
async def test_rsa17e_issued_before_omitted():
    captured_requests = []
    mock_http = MockHttpClient(
        on_connection_attempt=lambda conn: conn.respond_with_success(),
        on_request=capture_and_respond(captured_requests),
    )
    client = rest_client(mock_http, key=KEY)

    await client.auth.revoke_tokens([{'type': 'clientId', 'value': 'alice'}])

    body = request_body(captured_requests[0])
    assert 'issuedBefore' not in body


# UTS: rest/unit/RSA17f/reauth-margin-included-0
@deviation
async def test_rsa17f_reauth_margin_included():
    captured_requests = []
    mock_http = MockHttpClient(
        on_connection_attempt=lambda conn: conn.respond_with_success(),
        on_request=capture_and_respond(captured_requests, body=[
            {'target': 'clientId:alice', 'issuedBefore': 1700000000000, 'appliesAt': 1700000030000},
        ]),
    )
    client = rest_client(mock_http, key=KEY)

    await client.auth.revoke_tokens(
        [{'type': 'clientId', 'value': 'alice'}],
        allow_reauth_margin=True,
    )

    body = request_body(captured_requests[0])
    assert body['allowReauthMargin'] is True


# UTS: rest/unit/RSA17f/reauth-margin-omitted-1
@deviation
async def test_rsa17f_reauth_margin_omitted():
    captured_requests = []
    mock_http = MockHttpClient(
        on_connection_attempt=lambda conn: conn.respond_with_success(),
        on_request=capture_and_respond(captured_requests),
    )
    client = rest_client(mock_http, key=KEY)

    await client.auth.revoke_tokens([{'type': 'clientId', 'value': 'alice'}])

    body = request_body(captured_requests[0])
    assert 'allowReauthMargin' not in body


# UTS: rest/unit/RSA17f/both-options-together-2
@deviation
async def test_rsa17f_both_options_together():
    captured_requests = []
    mock_http = MockHttpClient(
        on_connection_attempt=lambda conn: conn.respond_with_success(),
        on_request=capture_and_respond(captured_requests, body=[
            {'target': 'clientId:alice', 'issuedBefore': 1699999000000, 'appliesAt': 1700000030000},
        ]),
    )
    client = rest_client(mock_http, key=KEY)

    await client.auth.revoke_tokens(
        [{'type': 'clientId', 'value': 'alice'}],
        issued_before=1699999000000,
        allow_reauth_margin=True,
    )

    body = request_body(captured_requests[0])
    assert body['targets'] == ['clientId:alice']
    assert body['issuedBefore'] == 1699999000000
    assert body['allowReauthMargin'] is True


# UTS: rest/unit/RSA17/server-error-propagated-0
@deviation
async def test_rsa17_server_error_propagated():
    mock_http = MockHttpClient(
        on_connection_attempt=lambda conn: conn.respond_with_success(),
        on_request=lambda request: request.respond_with(500, {
            'error': {'code': 50000, 'statusCode': 500, 'message': 'Internal error'},
        }),
    )
    client = rest_client(mock_http, key=KEY)

    with pytest.raises(AblyException) as excinfo:
        await client.auth.revoke_tokens([{'type': 'clientId', 'value': 'alice'}])

    assert excinfo.value.code == 50000
    assert excinfo.value.status_code == 500


# UTS: rest/unit/RSA17/request-uses-basic-auth-0
@deviation
async def test_rsa17_request_uses_basic_auth():
    captured_requests = []
    mock_http = MockHttpClient(
        on_connection_attempt=lambda conn: conn.respond_with_success(),
        on_request=capture_and_respond(captured_requests),
    )
    client = rest_client(mock_http, key=KEY)

    await client.auth.revoke_tokens([{'type': 'clientId', 'value': 'alice'}])

    assert captured_requests[0].headers['Authorization'].startswith('Basic ')
