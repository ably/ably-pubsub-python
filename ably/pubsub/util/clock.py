import time
from typing import Callable

from ably.pubsub.util.helper import Timer


class Clock:
    """The source of time for every decision a client makes from it.

    Token expiry, the server-time offset, the fallback-host cache and the
    transport's idle detection all read the clock, and every delayed callback
    is scheduled through it, so replacing one moves all of them together.

    `now_ms` is the time of day and may step; `monotonic_ms` only ever moves
    forward and is what a duration is measured with.
    """

    def now_ms(self) -> int:
        """The milliseconds elapsed since the unix epoch."""
        return round(time.time_ns() / 1_000_000)

    def monotonic_ms(self) -> float:
        """The milliseconds elapsed since an arbitrary fixed point."""
        return time.monotonic() * 1000

    def timer(self, timeout: float, callback: Callable) -> Timer:
        """Schedules `callback` for `timeout` milliseconds from now."""
        return Timer(timeout, callback)


def select_clock(options) -> Clock:
    """The clock a client reads its time from.

    `TestOptions.clock` substitutes for the real one during tests, letting them
    drive time-dependent behaviour without waiting for it. Clients which supply
    none get `Clock`.
    """
    test_options = getattr(options, '_test_options', None)
    if test_options is not None and test_options.clock is not None:
        return test_options.clock
    return Clock()
