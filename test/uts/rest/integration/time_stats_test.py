"""Derived from uts/rest/integration/time_stats.md in ably/specification.

Spec points: RSC16, RSC6
"""

import time as wall_clock
from datetime import datetime, timedelta, timezone

import pytest_asyncio

from ably import AblyRest
from ably.http.paginatedresult import PaginatedResult
from ably.types.stats import Stats
from test.uts.helpers.client import sandbox_rest_client
from test.uts.helpers.sandbox import SANDBOX_ENDPOINT

# The tolerance the specification allows between the server's clock and this
# one, as milliseconds.
CLOCK_TOLERANCE_MS = 5000

# The units a stats interval may be aggregated over, which is the
# specification's `["minute", "hour", "day", "month"]`.
STATS_UNITS = ('minute', 'hour', 'day', 'month')

# How far back the injected interval sits. A freshly provisioned app has no
# stats at all, so the interval has to be old enough to be complete and recent
# enough that a query bounded at `now` still reaches it.
STATS_INTERVAL_AGE = timedelta(minutes=3)


@pytest_asyncio.fixture(scope='module')
async def app_with_stats(sandbox):
    """The sandbox app, with one minute of traffic recorded against it.

    The specification allows for `stats()` returning nothing — "stats may be
    empty for a new sandbox app" — and guards its assertions on the interval's
    shape behind `IF result.items.length > 0`. Against an app that has never
    seen traffic that branch never runs, which would leave both stats tests
    asserting only that the call returned. So the app is given a minute's worth
    of traffic first, through the sandbox's own `POST /stats` injection
    endpoint, and the assertions the specification guards are made
    unconditionally below.

    Injecting rather than publishing is what the repository's own sandbox stats
    suite does: real traffic is aggregated on the server's schedule, so there
    is no bounded wait after which a published message is certain to be
    counted, whereas an injected interval is queryable at once.
    """
    interval = (datetime.now(timezone.utc).replace(tzinfo=None) - STATS_INTERVAL_AGE).replace(
        second=0, microsecond=0)
    client = AblyRest(key=sandbox.key(0).key_str, endpoint=SANDBOX_ENDPOINT,
                      use_binary_protocol=False)
    try:
        await client.http.post('/stats', body=[{
            'intervalId': Stats.to_interval_id(interval, 'minute'),
            'inbound': {'realtime': {'messages': {'count': 50, 'data': 5000}}},
            'outbound': {'realtime': {'messages': {'count': 20, 'data': 2000}}},
        }])
    finally:
        await client.close()
    return sandbox


# UTS: rest/integration/RSC16/time-returns-server-time-0
async def test_rsc16_time_returns_server_time(sandbox):
    client = sandbox_rest_client(sandbox.key(0).key_str)

    before_request = wall_clock.time() * 1000
    server_time = await client.time()
    after_request = wall_clock.time() * 1000

    # NOTE: the specification asserts the result IS DateTime. `time()` in this
    # SDK returns milliseconds since the epoch, so the type assertion becomes a
    # numeric one and the comparisons below are made in the same units. This is
    # an idiomatic spelling of the same requirement, not a deviation.
    assert isinstance(server_time, (int, float))
    assert not isinstance(server_time, bool)

    # Server time should be reasonably close to client time
    # (allowing for network latency and minor clock differences)
    assert server_time >= before_request - CLOCK_TOLERANCE_MS
    assert server_time <= after_request + CLOCK_TOLERANCE_MS


# UTS: rest/integration/RSC6/stats-returns-result-0
async def test_rsc6_stats_returns_result(app_with_stats):
    client = sandbox_rest_client(app_with_stats.key(0).key_str)

    result = await client.stats()

    # Result should be a PaginatedResult
    assert isinstance(result, PaginatedResult)
    assert isinstance(result.items, list)

    # The specification guards these on `items.length > 0`; `app_with_stats`
    # makes the app's stats non-empty so that they are reached.
    assert len(result.items) > 0
    assert isinstance(result.items[0].interval_id, str)
    assert result.items[0].unit in STATS_UNITS


# UTS: rest/integration/RSC6/stats-with-parameters-1
async def test_rsc6_stats_with_parameters(app_with_stats):
    client = sandbox_rest_client(app_with_stats.key(0).key_str)

    # Request stats with specific parameters
    result = await client.stats(limit=5, direction='forwards', unit='hour')

    # Should succeed with parameters applied
    assert isinstance(result, PaginatedResult)
    assert len(result.items) <= 5

    # The specification asserts only the limit, which an empty page satisfies
    # whether or not the query reached the server. `app_with_stats` puts one
    # interval in range, so `unit` shows that the parameter was applied rather
    # than dropped.
    assert len(result.items) > 0
    assert all(stat.unit == 'hour' for stat in result.items)
