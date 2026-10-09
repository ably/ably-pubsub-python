"""Derived from uts/objects/integration/objects_gc_test.md in ably/specification.

Spec points: RTO10, RTLM19, RTLM5d2h, RTLM7

Tombstone semantics end to end against the sandbox: removing a map entry tombstones it
(RTLM7), a tombstoned entry reads back as absent (RTLM5d2h), and the key can be set again,
with a fresh object id where the new value is an object (RTO10, RTLM19). Only the public
API is used.

The GC sweep itself is not exercised here, as the specification's Scope section says: its
five-minute cadence and the server's grace period are not observable within an
integration test's budget, so the sweep is covered at the unit tier against a `FakeClock`.
Every wait here is on real time.

The specification carries a `## Protocol Variants` section, so every test runs once per
protocol and passes `use_binary_protocol` to the client it builds.

The specification's `value() == null` is `None` in Python. A counter's `value()` is reached
through `as_live_counter()` and a primitive's through `as_primitive()`, since ably-python's
`PathObject` is partitioned by type (RTTS); either view answers `None` once the path no
longer resolves (RTTS5d1), and each test has already seen a value at that path, so the
`None` is the removal rather than a value that never arrived. Clients are closed by the
suite's fixture.
"""

import asyncio

from ably.pubsub.realtime.connection import ConnectionState
from ably.pubsub.server import LiveCounter
from test.uts.helpers.client import await_connection_state, sandbox_realtime_client, wall_clock_poll_until
from test.uts.helpers.sandbox import random_id
from test.uts.objects.helpers.standard_test_pool import objects_channel_options

# The specification's `AWAIT_STATE ... WITH timeout` and `AWAIT channel.object.get() WITH
# timeout`, in seconds.
CONNECT_TIMEOUT = 15.0
SYNC_TIMEOUT = 15.0


async def synced_root(api_key, channel_name, use_binary_protocol):
    """The setup both tests share: a CONNECTED client and the synced root of `channel_name`."""
    client = sandbox_realtime_client(api_key, auto_connect=False, use_binary_protocol=use_binary_protocol)
    client.connect()
    await await_connection_state(client, ConnectionState.CONNECTED, timeout=CONNECT_TIMEOUT)

    channel = client.channels.get(channel_name, objects_channel_options())
    try:
        return await asyncio.wait_for(channel.object.get(), SYNC_TIMEOUT)
    except asyncio.TimeoutError:
        raise AssertionError(
            f'Timed out after {SYNC_TIMEOUT}s waiting for channel.object.get() on {channel_name!r}') from None


# UTS: objects/integration/RTO10/tombstoned-object-gc-recreate-0
async def test_rto10_tombstoned_object_gc_recreate(realtime_sandbox, use_binary_protocol):
    channel_name = 'objects-gc-object-' + random_id()
    root = await synced_root(realtime_sandbox.key_str, channel_name, use_binary_protocol)

    # Create a counter
    await root.set('counter', LiveCounter.create(42))
    await wall_clock_poll_until(
        lambda: root.get('counter').as_live_counter().value() == 42,
        description='counter to read 42')

    counter_id = root.get('counter').instance().id

    # Remove it (tombstones the entry and the object, RTLM7)
    await root.remove('counter')

    # RTLM5d2h: tombstoned entries read back as None
    await wall_clock_poll_until(
        lambda: root.get('counter').as_live_counter().value() is None,
        description='the removed counter to read None')

    # Create a new counter at the same key
    await root.set('counter', LiveCounter.create(99))
    await wall_clock_poll_until(
        lambda: root.get('counter').as_live_counter().value() == 99,
        description='the new counter to read 99')

    assert root.get('counter').as_live_counter().value() == 99
    assert root.get('counter').instance().id != counter_id


# UTS: objects/integration/RTLM19/tombstoned-entry-gc-reset-0
async def test_rtlm19_tombstoned_entry_gc_reset(realtime_sandbox, use_binary_protocol):
    channel_name = 'objects-gc-entry-' + random_id()
    root = await synced_root(realtime_sandbox.key_str, channel_name, use_binary_protocol)

    # Set then remove a key
    await root.set('ephemeral', 'temporary')
    await wall_clock_poll_until(
        lambda: root.get('ephemeral').as_primitive().value() == 'temporary',
        description="ephemeral to read 'temporary'")

    await root.remove('ephemeral')

    # RTLM5d2h: tombstoned entries read back as None
    await wall_clock_poll_until(
        lambda: root.get('ephemeral').as_primitive().value() is None,
        description='the removed entry to read None')

    # Set the same key again
    await root.set('ephemeral', 'revived')
    await wall_clock_poll_until(
        lambda: root.get('ephemeral').as_primitive().value() == 'revived',
        description="ephemeral to read 'revived'")

    assert root.get('ephemeral').as_primitive().value() == 'revived'
