"""A fake clock, implementing the fake timers that the Universal Test
Specifications are written against.

The pseudocode convention lives in
``uts/realtime/unit/helpers/mock_websocket.md`` in the ably/specification
repository: ``enable_fake_timers()`` followed by ``ADVANCE_TIME(ms)``. Here a
test builds a `FakeClock`, hands `clock.timer` to the client as
`TestOptions(timer=clock.timer)`, and calls `await clock.advance(ms)`.

Prefer a real short interval where a client option or `connectionDetails`
reaches the behaviour under test; see the fake-time section of
[deviations.md](../deviations.md).
"""

import asyncio
import inspect

# How many times `advance` yields to the event loop after firing a timer, so
# that tasks the callback started run to completion before the next timer fires
# or `advance` returns.
SETTLE_PASSES = 20

# A ceiling on how many timers one `advance` fires, so that a callback which
# reschedules itself with no delay fails the test instead of hanging it.
MAX_TIMERS_PER_ADVANCE = 1000


async def settle(passes=SETTLE_PASSES):
    """Yields to the event loop until the tasks already queued have run.

    This is the `process_pending_events()` convention of ``uts/README.md``,
    with no notional or real time passing. One yield is rarely enough on the
    realtime paths, which chain `create_task` several levels deep.
    """
    for _ in range(passes):
        await asyncio.sleep(0)


class FakeTimer:
    """A scheduled callback which fires when the clock reaches its due time."""

    def __init__(self, clock, due, callback):
        self.due = due
        self.callback = callback
        self.cancelled = False
        self.fired = False
        self.__clock = clock

    def cancel(self):
        self.cancelled = True
        self.__clock._discard(self)

    def __repr__(self):
        return f'FakeTimer(due={self.due}, callback={self.callback!r})'


class FakeClock:
    """Records timers against a notional time which only `advance` moves.

    `clock.timer` has the signature of `ably.util.helper.Timer`, so it can be
    passed straight to `TestOptions(timer=...)`. Nothing fires until a test
    asks for it.
    """

    def __init__(self, settle_passes=SETTLE_PASSES):
        self.now = 0.0
        self.fired = []
        self.__pending = []
        self.__settle_passes = settle_passes

    def timer(self, timeout, callback):
        """Schedules `callback` for `timeout` milliseconds from the clock's now."""
        timer = FakeTimer(self, self.now + timeout, callback)
        self.__pending.append(timer)
        return timer

    @property
    def pending(self):
        """The timers still waiting to fire, in the order they were scheduled."""
        return list(self.__pending)

    def _discard(self, timer):
        if timer in self.__pending:
            self.__pending.remove(timer)

    async def advance(self, ms):
        """Moves the clock forward by `ms`, firing every timer that falls due.

        Timers fire in due order, earliest first, and the clock reads each
        timer's due time while its callback runs, so a timer scheduled from
        within a callback is due relative to the moment it was scheduled. The
        due set is recomputed after every callback rather than taken once at
        the start, so a timer scheduled into the remainder of the window fires
        within the same `advance` — the window runs to a fixed point.

        Between callbacks, and once more before returning, the event loop is
        given a chance to settle, so the work a callback started has landed by
        the time `advance` returns or the next timer fires.
        """
        target = self.now + ms
        for _ in range(MAX_TIMERS_PER_ADVANCE):
            due = self.__next_due(target)
            if due is None:
                break
            self.now = due.due
            self.__pending.remove(due)
            due.fired = True
            self.fired.append(due)
            await self.__invoke(due.callback)
            await self.settle()
        else:
            raise RuntimeError(
                f'advance({ms}) fired {MAX_TIMERS_PER_ADVANCE} timers without emptying the '
                'window; a callback is most likely rescheduling itself with no delay'
            )
        self.now = target
        await self.settle()

    async def settle(self):
        """Yields to the event loop until the tasks already queued have run."""
        await settle(self.__settle_passes)

    def __next_due(self, target):
        candidates = [t for t in self.__pending if not t.cancelled and t.due <= target]
        if not candidates:
            return None
        # min() is stable, so timers sharing a due time fire in schedule order
        return min(candidates, key=lambda t: t.due)

    @staticmethod
    async def __invoke(callback):
        if asyncio.iscoroutinefunction(callback):
            await callback()
        else:
            result = callback()
            if inspect.isawaitable(result):
                await result
