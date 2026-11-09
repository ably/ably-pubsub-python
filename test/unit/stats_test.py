"""Unit tests for the Stats type.

Tests cover:
- TS12p: intervalTime parsed from the intervalId as a UTC time
"""

from datetime import datetime, timezone

import pytest

from ably.pubsub.types.stats import Stats


@pytest.mark.parametrize('interval_id, expected', [
    ('2024-01-02:03:04', datetime(2024, 1, 2, 3, 4, tzinfo=timezone.utc)),
    ('2024-01-02:03', datetime(2024, 1, 2, 3, tzinfo=timezone.utc)),
    ('2024-01-02', datetime(2024, 1, 2, tzinfo=timezone.utc)),
    ('2024-01', datetime(2024, 1, 1, tzinfo=timezone.utc)),
])
def test_interval_time_is_utc(interval_id, expected):
    stats = Stats.from_dict({'intervalId': interval_id})
    assert stats.interval_time == expected
    assert stats.interval_time.tzinfo is timezone.utc
