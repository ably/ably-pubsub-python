"""Derived from uts/rest/integration/revoke_tokens.md in ably/specification.

Spec points: RSA17, RSA17b, RSA17c, RSA17d, RSA17e, RSA17f, RSA17g, TRS2, TRF2

ably-python has no token revocation: there is no `Auth#revokeTokens`, no
`TokenRevocationTargetSpecifier`, no `BatchResult` and no
`TokenRevocationSuccessResult`/`TokenRevocationFailureResult`. Every test here is
therefore an env-gated deviation, each failing with `AttributeError` when run with
`RUN_DEVIATIONS=1`. They are written against the API the specification describes,
spelled the way the unit tier spells it in
[rest/unit/auth/revoke_tokens_test.py](../unit/auth/revoke_tokens_test.py)
(`revoke_tokens`, `issued_before`, `allow_reauth_margin`, `success_count`,
`failure_count`, `applies_at`), with the target specifiers as plain dicts since
the specifier type does not exist either. The two tiers gate on the same names, so
they go green together when the API lands.

Everything either side of the revocation call is real: the app, the revocable key,
the issued token and the realtime connection the revocation drops. The two
connection tests assert FAILED with 40171 where the specification asserts
DISCONNECTED with 40141, which is an adaptation recorded in
[deviations-revoke-tokens-integration.md](../../deviations-revoke-tokens-integration.md)
and explained where it is made.
"""

import asyncio

import pytest

from ably.realtime.connection import ConnectionState
from ably.util.exceptions import AblyException
from test.uts.helpers.client import (
    await_connection_state,
    next_connection_state,
    sandbox_realtime_client,
    sandbox_rest_client,
)
from test.uts.helpers.deviations import deviation
from test.uts.helpers.sandbox import extract_key_name, extract_key_secret, generate_jwt, random_id

# `keys[4]` is the one the canonical app setup marks `revocableTokens: true`. The
# revocation endpoint is only served for such a key, so the index is part of what
# these tests assert rather than an arbitrary choice of credential.
REVOCABLE_KEY_INDEX = 4

# How long a revoked token's connection is given to be dropped. The revocation
# applies about a quarter of a second after the request and the server pushes the
# disconnect at once, so this is generous; it is bounded well inside the package's
# 120 seconds so a stalled wait names itself.
DROP_TIMEOUT = 20.0


async def start_drop_watch(client):
    """Begins waiting for `client`'s connection to be dropped, before the caller revokes.

    This is the specification's `disconnected_promise = connection.once("disconnected")`,
    set up before the revocation so the state change cannot be missed. The client
    auto-connects, so a listener registered afterwards can wait for a change that has
    already gone past. The wait runs as a task, and the event loop is yielded to once,
    so the listener is in place by the time this returns.

    FAILED stands in for the specification's DISCONNECTED; see the note in each caller.
    """
    watch = asyncio.ensure_future(
        next_connection_state(client, ConnectionState.FAILED, timeout=DROP_TIMEOUT))
    await asyncio.sleep(0)
    return watch


async def connected_token_client(key_client, client_id):
    """A realtime client connected with a native token issued for `client_id`.

    The specification's setup: `requestToken(clientId: client_id)` followed by a
    `Realtime` carrying that token, awaited to CONNECTED. Token params go to
    `request_token` as a positional dict, since its keyword arguments are all
    auth options; the `TokenDetails` goes to the client as `token_details`, since
    `token` wants a string.
    """
    token_details = await key_client.auth.request_token({'client_id': client_id})
    realtime_client = sandbox_realtime_client(token_details=token_details)
    await await_connection_state(realtime_client, ConnectionState.CONNECTED)
    return realtime_client


# UTS: rest/integration/RSA17g/revoke-token-prevents-use-0
@deviation
async def test_rsa17g_revoke_token_prevents_use(sandbox):
    client_id = f'revoke-client-{random_id()}'
    key_client = sandbox_rest_client(sandbox.key(REVOCABLE_KEY_INDEX).key_str)
    realtime_client = await connected_token_client(key_client, client_id)

    dropped = await start_drop_watch(realtime_client)
    try:
        revoke_result = await key_client.auth.revoke_tokens([{'type': 'clientId', 'value': client_id}])

        assert revoke_result.success_count == 1
        assert revoke_result.failure_count == 0
        assert len(revoke_result.results) == 1

        # NOTE: the spec asserts `success IS TokenRevocationSuccessResult`. No such type
        # exists in ably-python, so the attributes it defines stand in for the type check.
        success = revoke_result.results[0]
        assert success.target == f'clientId:{client_id}'
        assert isinstance(success.issued_before, (int, float))
        assert isinstance(success.applies_at, (int, float))

        # The spec asserts a DISCONNECTED state change whose `reason.code` is 40141. The
        # server does push exactly that — action 6 carrying `{"code": 40141, "message":
        # "token revoked"}` — but a connection holding only a `TokenDetails` has no way to
        # renew, so ably-python fails it under RSA4a with 40171 and the 40141 never reaches
        # the connection's state. See deviations-revoke-tokens-integration.md.
        state_change = await dropped
        assert state_change.reason.code == 40171
        assert state_change.reason.status_code == 403
    finally:
        dropped.cancel()


# UTS: rest/integration/RSA17d/token-auth-revoke-rejected-0
@deviation
async def test_rsa17d_token_auth_revoke_rejected(sandbox):
    revocable_key = sandbox.key(REVOCABLE_KEY_INDEX).key_str
    jwt = generate_jwt(extract_key_name(revocable_key), extract_key_secret(revocable_key), ttl=3600000)
    token_rest = sandbox_rest_client(token=jwt)

    with pytest.raises(AblyException) as excinfo:
        await token_rest.auth.revoke_tokens([{'type': 'clientId', 'value': 'anyone'}])

    assert excinfo.value.code == 40162
    assert excinfo.value.status_code == 401


# UTS: rest/integration/RSA17e/issued-before-reauth-margin-0
@deviation
async def test_rsa17e_issued_before_reauth_margin(sandbox):
    client_id = f'revoke-margin-client-{random_id()}'
    key_client = sandbox_rest_client(sandbox.key(REVOCABLE_KEY_INDEX).key_str)

    # `time()` answers with a number of milliseconds since the epoch, not a date.
    server_time = await key_client.time()

    # An `issuedBefore` in the past, so no token in use anywhere is revoked.
    issued_before = int(server_time) - 20 * 60 * 1000

    revoke_result = await key_client.auth.revoke_tokens(
        [{'type': 'clientId', 'value': client_id}],
        issued_before=issued_before,
        allow_reauth_margin=True,
    )

    assert revoke_result.success_count == 1
    assert len(revoke_result.results) == 1

    # RSA17e: issuedBefore should reflect what was sent.
    assert revoke_result.results[0].issued_before == issued_before

    # RSA17f: allowReauthMargin delays appliesAt by ~30 seconds.
    assert revoke_result.results[0].applies_at > server_time + 30 * 1000


# UTS: rest/integration/RSA17c/mixed-success-failure-0
@deviation
async def test_rsa17c_mixed_success_failure(sandbox):
    client_id = f'revoke-mixed-client-{random_id()}'
    key_client = sandbox_rest_client(sandbox.key(REVOCABLE_KEY_INDEX).key_str)
    realtime_client = await connected_token_client(key_client, client_id)

    dropped = await start_drop_watch(realtime_client)
    try:
        revoke_result = await key_client.auth.revoke_tokens([
            {'type': 'clientId', 'value': client_id},
            {'type': 'invalidType', 'value': 'abc'},
        ])

        assert revoke_result.success_count == 1
        assert revoke_result.failure_count == 1
        assert len(revoke_result.results) == 2

        # NOTE: the spec asserts `success IS TokenRevocationSuccessResult` and
        # `failure IS TokenRevocationFailureResult`; neither type exists in ably-python,
        # so the attributes each defines stand in for the type checks.
        success = revoke_result.results[0]
        assert success.target == f'clientId:{client_id}'
        assert isinstance(success.issued_before, (int, float))
        assert isinstance(success.applies_at, (int, float))

        # The sandbox answers an invalid target type with 40001 rather than the 40000 the
        # spec's example shows, so only the status code the spec asserts is asserted here.
        failure = revoke_result.results[1]
        assert failure.target == 'invalidType:abc'
        assert failure.error.status_code == 400

        # FAILED with 40171 for the spec's DISCONNECTED with 40141, as in RSA17g above.
        state_change = await dropped
        assert state_change.reason.code == 40171
        assert state_change.reason.status_code == 403
    finally:
        dropped.cancel()
