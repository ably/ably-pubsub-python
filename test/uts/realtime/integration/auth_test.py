"""Derived from uts/realtime/integration/auth.md in ably/specification.

Spec points: RTC8, RTC8a, RTC8c, RSA8, RSA7

Every client here authenticates through an `auth_callback` returning an Ably JWT, which is
what the specification's third-party JWT library produces; `generate_jwt` signs it HS256
over the key secret.

`Connection#id` is not a member of ably-python's `Connection`, so `connection_id` below
reads the value off the connection manager. See
[deviations.md](../../deviations.md) for the house ruling on a missing accessor.

`authorize()` on a CONNECTED connection sends AUTH and then awaits the next state change
before it returns, so the UPDATE it provokes has already been delivered to a listener
registered beforehand by the time the call completes. The reauth test needs no settle.
"""

from ably.realtime.connection import ConnectionState
from test.uts.helpers.client import await_connection_state, sandbox_realtime_client
from test.uts.helpers.deviations import deviation
from test.uts.helpers.sandbox import extract_key_name, extract_key_secret, generate_jwt, random_id

# The lifetime every JWT here is issued with, as the specification's `ttl: 3600000`.
TOKEN_TTL = 3600000

# The wait for the mismatched-clientId connection to be failed by the server. The SDK spends
# its `disconnected_retry_timeout` — 15 seconds by default — between the first attempt and
# the one the server rejects, so the specification's unstated wait has to clear that.
FAIL_TIMEOUT = 20.0


def connection_id(client):
    """The specification's `connection.id`, held on the connection manager."""
    return client.connection.connection_manager.connection_id


def jwt_callback(api_key, client_id=None):
    """The specification's `auth_callback`, answering with a freshly signed Ably JWT."""
    key_name = extract_key_name(api_key)
    key_secret = extract_key_secret(api_key)

    async def auth_callback(params):
        return generate_jwt(key_name=key_name, key_secret=key_secret, ttl=TOKEN_TTL, client_id=client_id)

    return auth_callback


# UTS: realtime/integration/RTC8a/in-band-reauth-connected-0
async def test_rtc8a_in_band_reauth_connected(realtime_sandbox):
    client = sandbox_realtime_client(
        auth_callback=jwt_callback(realtime_sandbox.key_str), auto_connect=False)

    client.connect()
    await await_connection_state(client, ConnectionState.CONNECTED)

    connection_id_before = connection_id(client)

    state_changes = []

    def record(change):
        state_changes.append(change)

    client.connection.on(record)

    token = await client.auth.authorize()

    connection_id_after = connection_id(client)

    assert token is not None
    assert isinstance(token.token, str)

    assert connection_id_after == connection_id_before

    state_transitions = [change for change in state_changes if change.current != change.previous]
    assert state_transitions == []


# UTS: realtime/integration/RTC8c/authorize-initiates-connection-0
async def test_rtc8c_authorize_initiates_connection(realtime_sandbox):
    client = sandbox_realtime_client(
        auth_callback=jwt_callback(realtime_sandbox.key_str), auto_connect=False)

    assert client.connection.state is ConnectionState.INITIALIZED

    token = await client.auth.authorize()

    await await_connection_state(client, ConnectionState.CONNECTED)

    assert token is not None
    assert client.connection.state is ConnectionState.CONNECTED
    assert connection_id(client) is not None


# UTS: realtime/integration/RSA8/token-auth-connect-0
async def test_rsa8_token_auth_connect(realtime_sandbox):
    client = sandbox_realtime_client(
        auth_callback=jwt_callback(realtime_sandbox.key_str), auto_connect=False)

    client.connect()
    await await_connection_state(client, ConnectionState.CONNECTED)

    assert client.connection.state is ConnectionState.CONNECTED
    assert connection_id(client) is not None
    assert client.connection.error_reason is None


# UTS: realtime/integration/RSA7/matching-clientid-succeeds-0
@deviation
async def test_rsa7_matching_clientid_succeeds(realtime_sandbox):
    test_client_id = 'test-client-' + random_id()

    client = sandbox_realtime_client(
        auth_callback=jwt_callback(realtime_sandbox.key_str, client_id=test_client_id),
        client_id=test_client_id, auto_connect=False)

    client.connect()
    await await_connection_state(client, ConnectionState.CONNECTED)

    assert client.connection.state is ConnectionState.CONNECTED
    assert client.auth.client_id == test_client_id


# UTS: realtime/integration/RSA7/mismatched-clientid-fails-1
async def test_rsa7_mismatched_clientid_fails(realtime_sandbox):
    # UTS SPEC ERROR: the test step expects the `Realtime` constructor to throw, while the
    # assertions below it say the key assertion is that the connection enters FAILED with
    # 40102. Both cannot hold — a constructor has no token to compare a clientId against,
    # and the specification's own note concedes the point — so the client is constructed
    # and the FAILED assertion the specification names is the one made.
    client = sandbox_realtime_client(
        auth_callback=jwt_callback(realtime_sandbox.key_str, client_id='token-client-id'),
        client_id='wrong-client-id', auto_connect=False)

    client.connect()
    await await_connection_state(client, ConnectionState.FAILED, FAIL_TIMEOUT)

    assert client.connection.state is ConnectionState.FAILED
    assert client.connection.error_reason.code == 40102
