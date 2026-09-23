"""Derived from uts/realtime/unit/connection/backoff_jitter_test.md in ably/specification.

Spec points: RTB1, RTB1a, RTB1b

The specification reads the retry delay from `ConnectionStateChange.retryIn` and
`ChannelStateChange.retryIn`, and tests the backoff and jitter coefficients through
functions of their own. ably-python has neither the attribute nor the functions, so
each delay is measured here as the notional time between the state change that
schedules a retry and the state change the retry produces. A `FakeClock` is what
makes that measurable: the retry runs on the timer seam, and a timer's callback runs
with the clock reading exactly the time the timer was due, so the measurement is
exact rather than sampled.
"""

from ably.realtime.channel import ChannelState
from ably.realtime.connection import ConnectionState
from ably.transport.websockettransport import ProtocolMessageAction
from test.uts.helpers.client import await_connection_state, realtime_client
from test.uts.helpers.clock import FakeClock, settle
from test.uts.helpers.deviations import deviation
from test.uts.helpers.mock_websocket import MockWebSocket, connected_message

CONNECTED_MESSAGE = connected_message('connection-id', connectionKey='connection-key')

# Short enough that a refused attempt, which reaches no failure path of its own and
# so ends on the transition timer, does not crowd out the retry delays being measured
REQUEST_TIMEOUT = 50

# The connection is suspended once it has been disconnected for
# `Defaults.connection_state_ttl`, after which retries move to
# `suspended_retry_timeout`; every sample has to be taken before that
CONNECTION_STATE_TTL = 120000


def expected_backoff(n):
    """RTB1a: the backoff coefficient for the nth retry, 1-indexed."""
    return min((n + 2) / 3, 2)


def retry_delays(transitions, scheduling_state, retrying_state):
    """The notional milliseconds each `scheduling_state` waited before the
    `retrying_state` that followed it.

    A retry made with no delay at all is left out: RTN15a reconnects immediately
    from the DISCONNECTED that follows a dropped connection, so that one carries no
    retry delay to measure.
    """
    delays = []
    scheduled_at = None
    for at, state in transitions:
        if state == scheduling_state:
            scheduled_at = at
        elif state == retrying_state and scheduled_at is not None:
            if at > scheduled_at:
                delays.append(at - scheduled_at)
            scheduled_at = None
    return delays


async def measure_disconnected_retry_delays(count, disconnected_retry_timeout):
    """Drives a connection through repeated failed reconnections, returning the
    delay before each retry."""
    connection_attempts = []

    def on_connection_attempt(conn):
        connection_attempts.append(conn)
        if len(connection_attempts) == 1:
            conn.respond_with_success(CONNECTED_MESSAGE)
        else:
            conn.respond_with_refused()

    mock_ws = MockWebSocket(on_connection_attempt=on_connection_attempt)
    clock = FakeClock()
    client = realtime_client(
        mock_ws, clock=clock, key='appId.keyId:keySecret', use_binary_protocol=False,
        disconnected_retry_timeout=disconnected_retry_timeout,
        realtime_request_timeout=REQUEST_TIMEOUT,
    )

    transitions = []
    client.connection.on(lambda change: transitions.append((clock.now, change.current)))

    client.connect()
    await await_connection_state(client, ConnectionState.CONNECTED)

    mock_ws.simulate_disconnect()
    await settle()

    while clock.now < CONNECTION_STATE_TTL:
        await clock.advance(disconnected_retry_timeout * 2 + REQUEST_TIMEOUT)
        delays = retry_delays(transitions, ConnectionState.DISCONNECTED, ConnectionState.CONNECTING)
        if len(delays) >= count:
            return delays
    raise AssertionError(f'Only {len(delays)} retry delays were observed before the connection '
                         'state ttl expired')


# UTS: realtime/unit/RTB1a/backoff-coefficient-sequence-0
@deviation
async def test_rtb1a_backoff_coefficient_sequence():
    # The specification calls a backoff coefficient function for retries 1 to 10.
    # ably-python has no such function, so the coefficient of each retry is read
    # back from the delay it was scheduled with
    retry_timeout = 2000
    delays = await measure_disconnected_retry_delays(10, retry_timeout)

    coefficients = [delay / retry_timeout for delay in delays[:10]]

    # Each coefficient carries RTB1b's jitter, so it lands in [0.8, 1.0] of the
    # backoff the specification gives as an exact value
    assert expected_backoff(1) * 0.8 <= coefficients[0] <= expected_backoff(1)
    assert expected_backoff(2) * 0.8 <= coefficients[1] <= expected_backoff(2)
    assert expected_backoff(3) * 0.8 <= coefficients[2] <= expected_backoff(3)
    assert expected_backoff(4) * 0.8 <= coefficients[3] <= expected_backoff(4)

    for coefficient in coefficients[3:]:
        assert 2.0 * 0.8 <= coefficient <= 2.0


# UTS: realtime/unit/RTB1b/jitter-coefficient-range-0
@deviation
async def test_rtb1b_jitter_coefficient_range():
    # The specification samples a jitter generator 1000 times. ably-python has no
    # such generator, so the jitter is read back from the delay of each retry, which
    # costs a reconnection cycle apiece; 40 samples still separate a uniform
    # distribution from a degenerate one, and fit inside the connection state ttl
    sample_count = 40
    retry_timeout = 2000
    delays = await measure_disconnected_retry_delays(sample_count, retry_timeout)

    # Every retry from the fourth on has a backoff coefficient of 2, so the delay
    # divided by twice the retry timeout is the jitter coefficient alone
    jitter_values = [delay / (retry_timeout * 2.0) for delay in delays[3:sample_count]]
    assert len(jitter_values) > 0

    for jitter in jitter_values:
        assert jitter >= 0.8
        assert jitter <= 1.0

    mean = sum(jitter_values) / len(jitter_values)
    assert mean >= 0.85
    assert mean <= 0.95

    assert max(jitter_values) - min(jitter_values) > 0.05


# UTS: realtime/unit/RTB1/disconnected-retry-delay-0
@deviation
async def test_rtb1_disconnected_retry_delay():
    disconnected_retry_timeout = 2000
    retry_delays_observed = await measure_disconnected_retry_delays(5, disconnected_retry_timeout)

    assert len(retry_delays_observed) >= 5

    assert retry_delays_observed[0] >= disconnected_retry_timeout * 1.0 * 0.8
    assert retry_delays_observed[0] <= disconnected_retry_timeout * 1.0

    assert retry_delays_observed[1] >= disconnected_retry_timeout * (4.0 / 3.0) * 0.8
    assert retry_delays_observed[1] <= disconnected_retry_timeout * (4.0 / 3.0)

    assert retry_delays_observed[2] >= disconnected_retry_timeout * (5.0 / 3.0) * 0.8
    assert retry_delays_observed[2] <= disconnected_retry_timeout * (5.0 / 3.0)

    assert retry_delays_observed[3] >= disconnected_retry_timeout * 2.0 * 0.8
    assert retry_delays_observed[3] <= disconnected_retry_timeout * 2.0

    assert retry_delays_observed[4] >= disconnected_retry_timeout * 2.0 * 0.8
    assert retry_delays_observed[4] <= disconnected_retry_timeout * 2.0


# UTS: realtime/unit/RTB1/suspended-channel-retry-delay-1
@deviation
async def test_rtb1_suspended_channel_retry_delay():
    channel_name = 'test-RTB1-channel'
    channel_retry_timeout = 3000

    mock_ws = MockWebSocket(
        on_connection_attempt=lambda conn: conn.respond_with_success(CONNECTED_MESSAGE),
    )
    clock = FakeClock()
    client = realtime_client(
        mock_ws, clock=clock, key='appId.keyId:keySecret', use_binary_protocol=False,
        channel_retry_timeout=channel_retry_timeout,
    )

    attach_count = []

    def on_message_from_client(message):
        if message.get('action') == int(ProtocolMessageAction.ATTACH):
            attach_count.append(message)
            if len(attach_count) == 1:
                mock_ws.send_to_client({
                    'action': int(ProtocolMessageAction.ATTACHED),
                    'channel': message.get('channel'),
                    'flags': 0,
                })
            else:
                # RTL13b: a re-attach that is refused suspends the channel
                mock_ws.send_to_client({
                    'action': int(ProtocolMessageAction.DETACHED),
                    'channel': message.get('channel'),
                    'error': {'code': 90001, 'statusCode': 500,
                              'message': 'Channel re-attach failed'},
                })

    mock_ws.on_message_from_client = on_message_from_client

    client.connect()
    await await_connection_state(client, ConnectionState.CONNECTED)

    channel = client.channels.get(channel_name)

    transitions = []
    channel.on(lambda change: transitions.append((clock.now, change.current)))

    await channel.attach()
    assert channel.state == ChannelState.ATTACHED

    # The specification sends an ERROR on the channel to trigger the re-attach.
    # ably-python fails a channel outright on an ERROR, so the re-attach is
    # triggered by a server-initiated DETACHED instead
    mock_ws.send_to_client({
        'action': int(ProtocolMessageAction.DETACHED),
        'channel': channel_name,
        'error': {'code': 90001, 'statusCode': 500, 'message': 'Channel error'},
    })
    await settle()

    delays = []
    for _ in range(30):
        await clock.advance(7000)
        delays = retry_delays(transitions, ChannelState.SUSPENDED, ChannelState.ATTACHING)
        if len(delays) >= 4:
            break

    assert len(delays) >= 4

    assert delays[0] >= channel_retry_timeout * 1.0 * 0.8
    assert delays[0] <= channel_retry_timeout * 1.0

    assert delays[1] >= channel_retry_timeout * (4.0 / 3.0) * 0.8
    assert delays[1] <= channel_retry_timeout * (4.0 / 3.0)

    assert delays[2] >= channel_retry_timeout * (5.0 / 3.0) * 0.8
    assert delays[2] <= channel_retry_timeout * (5.0 / 3.0)

    assert delays[3] >= channel_retry_timeout * 2.0 * 0.8
    assert delays[3] <= channel_retry_timeout * 2.0
