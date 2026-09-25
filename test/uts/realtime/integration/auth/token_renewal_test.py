"""Derived from uts/realtime/integration/auth/token_renewal_test.md in ably/specification.

Spec points: RSA4b, RTN14b

The client is given a JWT that lives five seconds and then long-lived ones. Measured against
the sandbox, the server answers the expiry with DISCONNECTED carrying `40142`, and the
client is back in CONNECTED about a tenth of a second later, having called the auth callback
a second time — so the specification's thirty-second poll has a wide margin.

The specification records `initial_connection_id` before the expiry and never asserts on
it, so nothing here reads it: ably-python has no `Connection#id` to read it from, and
adding the adaptation described in [deviations.md](../../../deviations.md) would only
introduce a value no assertion consumes.
"""

from ably.realtime.connection import ConnectionState
from test.uts.helpers.client import await_connection_state, sandbox_realtime_client, wall_clock_poll_until
from test.uts.helpers.sandbox import extract_key_name, extract_key_secret, generate_jwt

# The two lifetimes the specification issues: one short enough for the server to expire
# during the test, and one that outlives it.
SHORT_TTL = 5000
LONG_TTL = 3600000

# The specification's `poll_until(interval: 1000ms, timeout: 30s)` and the fifteen seconds
# it then gives the reconnection.
RENEWAL_TIMEOUT = 30.0
RENEWAL_INTERVAL = 1.0
RECONNECT_TIMEOUT = 15.0


# UTS: realtime/integration/RSA4b/token-renewal-on-expiry-0
async def test_rsa4b_token_renewal_on_expiry(realtime_sandbox):
    api_key = realtime_sandbox.key_str
    key_name = extract_key_name(api_key)
    key_secret = extract_key_secret(api_key)
    callback_count = []

    async def auth_callback(params):
        callback_count.append(params)
        ttl = SHORT_TTL if len(callback_count) == 1 else LONG_TTL
        return generate_jwt(key_name=key_name, key_secret=key_secret, ttl=ttl)

    client = sandbox_realtime_client(auth_callback=auth_callback, auto_connect=False)

    client.connect()
    await await_connection_state(client, ConnectionState.CONNECTED, RECONNECT_TIMEOUT)

    assert len(callback_count) == 1

    await wall_clock_poll_until(
        lambda: len(callback_count) >= 2, timeout=RENEWAL_TIMEOUT, interval=RENEWAL_INTERVAL,
        description='the auth callback to be invoked for a renewed token')

    await await_connection_state(client, ConnectionState.CONNECTED, RECONNECT_TIMEOUT)

    assert len(callback_count) >= 2
    assert client.connection.state is ConnectionState.CONNECTED
