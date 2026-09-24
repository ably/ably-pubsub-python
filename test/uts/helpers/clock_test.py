"""Tests for the `FakeClock` helper."""

import asyncio

import pytest

from test.uts.helpers.clock import FakeClock


def recorder():
    """A list, and a callable which appends a label to it."""
    fired = []

    def record(label):
        return lambda: fired.append(label)

    return fired, record


async def test_advance_fires_a_timer_that_falls_due():
    clock = FakeClock()
    fired, record = recorder()
    clock.timer(1000, record('a'))

    await clock.advance(1000)

    assert fired == ['a']


async def test_advance_does_not_fire_a_timer_early():
    clock = FakeClock()
    fired, record = recorder()
    clock.timer(1000, record('a'))

    await clock.advance(999)
    assert fired == []

    await clock.advance(1)
    assert fired == ['a']


async def test_advance_fires_in_due_order_not_schedule_order():
    clock = FakeClock()
    fired, record = recorder()
    clock.timer(3000, record('third'))
    clock.timer(1000, record('first'))
    clock.timer(2000, record('second'))

    await clock.advance(5000)

    assert fired == ['first', 'second', 'third']


async def test_timers_sharing_a_due_time_fire_in_schedule_order():
    clock = FakeClock()
    fired, record = recorder()
    clock.timer(1000, record('a'))
    clock.timer(1000, record('b'))
    clock.timer(1000, record('c'))

    await clock.advance(1000)

    assert fired == ['a', 'b', 'c']


async def test_a_timer_fires_only_once():
    clock = FakeClock()
    fired, record = recorder()
    clock.timer(1000, record('a'))

    await clock.advance(1000)
    await clock.advance(1000)

    assert fired == ['a']


async def test_now_advances_by_the_full_window():
    clock = FakeClock()
    clock.timer(1000, lambda: None)

    await clock.advance(2500)

    assert clock.now == 2500


async def test_a_callback_sees_the_clock_at_its_own_due_time():
    clock = FakeClock()
    observed = []
    clock.timer(1000, lambda: observed.append(clock.now))
    clock.timer(2000, lambda: observed.append(clock.now))

    await clock.advance(5000)

    assert observed == [1000, 2000]


async def test_cancel_stops_a_timer_firing():
    clock = FakeClock()
    fired, record = recorder()
    timer = clock.timer(1000, record('a'))

    timer.cancel()
    await clock.advance(5000)

    assert fired == []
    assert clock.pending == []


async def test_cancel_leaves_the_other_timers_alone():
    clock = FakeClock()
    fired, record = recorder()
    clock.timer(1000, record('a'))
    clock.timer(2000, record('b')).cancel()
    clock.timer(3000, record('c'))

    await clock.advance(5000)

    assert fired == ['a', 'c']


async def test_cancelling_twice_is_harmless():
    clock = FakeClock()
    fired, record = recorder()
    timer = clock.timer(1000, record('a'))

    timer.cancel()
    timer.cancel()
    await clock.advance(5000)

    assert fired == []


async def test_a_callback_can_schedule_a_timer_due_inside_the_same_window():
    clock = FakeClock()
    fired, record = recorder()

    def schedule_next():
        fired.append('first')
        clock.timer(1000, record('second'))

    clock.timer(1000, schedule_next)

    await clock.advance(5000)

    assert fired == ['first', 'second']


async def test_a_callback_can_schedule_a_timer_due_beyond_the_window():
    clock = FakeClock()
    fired, record = recorder()

    def schedule_next():
        fired.append('first')
        clock.timer(1000, record('second'))

    clock.timer(1000, schedule_next)

    await clock.advance(1000)
    assert fired == ['first']

    await clock.advance(1000)
    assert fired == ['first', 'second']


async def test_a_callback_can_cancel_a_timer_that_has_not_fired():
    clock = FakeClock()
    fired, record = recorder()
    victim = clock.timer(2000, record('victim'))

    def cancel_victim():
        fired.append('first')
        victim.cancel()

    clock.timer(1000, cancel_victim)

    await clock.advance(5000)

    assert fired == ['first']


async def test_a_callback_can_cancel_a_timer_due_at_the_same_moment():
    clock = FakeClock()
    fired, record = recorder()

    def cancel_victim():
        fired.append('first')
        victim.cancel()

    clock.timer(1000, cancel_victim)
    victim = clock.timer(1000, record('victim'))

    await clock.advance(1000)

    assert fired == ['first']


async def test_an_async_callback_is_awaited():
    clock = FakeClock()
    fired = []

    async def callback():
        await asyncio.sleep(0)
        fired.append('a')

    clock.timer(1000, callback)

    await clock.advance(1000)

    assert fired == ['a']


async def test_an_async_callback_completes_before_the_next_timer_fires():
    clock = FakeClock()
    fired = []

    async def slow():
        for _ in range(5):
            await asyncio.sleep(0)
        fired.append('slow')

    clock.timer(1000, slow)
    clock.timer(2000, lambda: fired.append('later'))

    await clock.advance(5000)

    assert fired == ['slow', 'later']


async def test_a_callback_returning_a_coroutine_is_awaited():
    clock = FakeClock()
    fired = []

    async def work():
        fired.append('a')

    clock.timer(1000, lambda: work())

    await clock.advance(1000)

    assert fired == ['a']


async def test_a_task_a_callback_starts_has_run_by_the_time_advance_returns():
    clock = FakeClock()
    fired = []

    async def background():
        await asyncio.sleep(0)
        fired.append('background')

    clock.timer(1000, lambda: asyncio.ensure_future(background()))

    await clock.advance(1000)

    assert fired == ['background']


async def test_pending_lists_the_timers_still_waiting():
    clock = FakeClock()
    early = clock.timer(1000, lambda: None)
    late = clock.timer(9000, lambda: None)

    assert clock.pending == [early, late]

    await clock.advance(1000)

    assert clock.pending == [late]


async def test_fired_records_the_timers_that_have_gone_off():
    clock = FakeClock()
    timer = clock.timer(1000, lambda: None)

    await clock.advance(1000)

    assert clock.fired == [timer]
    assert timer.fired


async def test_a_callback_that_reschedules_with_no_delay_raises_rather_than_hanging():
    clock = FakeClock()

    def reschedule():
        clock.timer(0, reschedule)

    clock.timer(0, reschedule)

    with pytest.raises(RuntimeError, match='rescheduling itself'):
        await clock.advance(1)


async def test_settle_passes_no_time():
    clock = FakeClock()
    fired, record = recorder()
    clock.timer(0, record('a'))

    await clock.settle()

    assert fired == []
    assert clock.now == 0
