"""Derived from uts/objects/integration/objects_sync_test.md in ably/specification.

Spec points: RTO4, RTO5, RTO17

The objects sync sequence against the sandbox: attaching with object modes gets an
ATTACHED carrying HAS_OBJECTS and an OBJECT_SYNC, after which `channel.object.get()`
resolves; a second client syncs what a first one wrote; and a detach and re-attach syncs
the pool afresh. Only the public API is used.

The specification carries a `## Protocol Variants` section, so every test runs once per
protocol and passes `use_binary_protocol` to each client it builds.

A primitive's `value()` is reached through `as_primitive()`, since ably-python's
`PathObject` is partitioned by type (RTTS); `root` is a `LiveMapPathObject`, so `set` and
`size` are called on it directly.

`AWAIT_STATE` for CONNECTED waits ten seconds, the figure the realtime integration tier
uses for a connect over the network, and `channel.object.get()` is bounded at the fifteen
seconds `objects_gc_test.md` gives the same call. Clients are closed by the suite's fixture.
"""

import asyncio

from ably.pubsub.realtime.connection import ConnectionState
from ably.pubsub.server import ChannelMode, PathObject
from test.uts.helpers.client import await_connection_state, sandbox_realtime_client, wall_clock_poll_until
from test.uts.helpers.sandbox import random_id
from test.uts.objects.helpers.standard_test_pool import objects_channel_options

CONNECT_TIMEOUT = 10.0
SYNC_TIMEOUT = 15.0


async def connected_client(api_key, use_binary_protocol):
    """The specification's `Realtime(options: {...})`, connected and CONNECTED."""
    client = sandbox_realtime_client(api_key, auto_connect=False, use_binary_protocol=use_binary_protocol)
    client.connect()
    await await_connection_state(client, ConnectionState.CONNECTED, timeout=CONNECT_TIMEOUT)
    return client


async def synced_root(channel):
    """The specification's `AWAIT channel.object.get()`, bounded at `SYNC_TIMEOUT`."""
    try:
        return await asyncio.wait_for(channel.object.get(), SYNC_TIMEOUT)
    except asyncio.TimeoutError:
        raise AssertionError(
            f'Timed out after {SYNC_TIMEOUT}s waiting for channel.object.get() on {channel.name!r}') from None


# UTS: objects/integration/RTO4-RTO5/attach-sync-get-0
async def test_rto4_rto5_attach_sync_get(realtime_sandbox, use_binary_protocol):
    channel_name = 'objects-sync-' + random_id()

    client = await connected_client(realtime_sandbox.key_str, use_binary_protocol)
    channel = client.channels.get(channel_name, objects_channel_options())

    root = await synced_root(channel)

    assert isinstance(root, PathObject)
    assert root.path() == ''


# UTS: objects/integration/RTO5-RTO17/two-clients-sync-0
async def test_rto5_rto17_two_clients_sync(realtime_sandbox, use_binary_protocol):
    channel_name = 'objects-two-sync-' + random_id()

    client_a = await connected_client(realtime_sandbox.key_str, use_binary_protocol)
    client_b = await connected_client(realtime_sandbox.key_str, use_binary_protocol)

    channel_a = client_a.channels.get(channel_name, objects_channel_options())
    channel_b = client_b.channels.get(channel_name, objects_channel_options())

    # Client A creates data
    root_a = await synced_root(channel_a)
    await root_a.set('key1', 'value1')

    # Client B attaches and syncs, and should see the data
    root_b = await synced_root(channel_b)
    await wall_clock_poll_until(
        lambda: root_b.get('key1').as_primitive().value() == 'value1',
        description="client B to read key1 == 'value1'")

    assert root_b.get('key1').as_primitive().value() == 'value1'


# UTS: objects/integration/RTO17/reattach-resyncs-0
async def test_rto17_reattach_resyncs(realtime_sandbox, use_binary_protocol):
    channel_name = 'objects-reattach-' + random_id()

    client = await connected_client(realtime_sandbox.key_str, use_binary_protocol)
    channel = client.channels.get(channel_name, objects_channel_options())
    root = await synced_root(channel)

    # Set some data. The write is applied locally once the server ACKs it (RTO20), so
    # it reads back as soon as `set` returns.
    await root.set('before_detach', 'hello')
    assert root.get('before_detach').as_primitive().value() == 'hello'

    # Detach and re-attach
    await channel.detach()
    await channel.attach()

    # Re-sync should restore data
    root = await synced_root(channel)
    await wall_clock_poll_until(
        lambda: root.get('before_detach').as_primitive().value() == 'hello',
        description="before_detach to read 'hello' after the re-sync")

    assert root.get('before_detach').as_primitive().value() == 'hello'


# UTS: objects/integration/RTO4/attach-subscribe-only-0
async def test_rto4_attach_subscribe_only(realtime_sandbox, use_binary_protocol):
    channel_name = 'objects-subscribe-only-' + random_id()

    client = await connected_client(realtime_sandbox.key_str, use_binary_protocol)
    channel = client.channels.get(channel_name, objects_channel_options(ChannelMode.OBJECT_SUBSCRIBE))

    root = await synced_root(channel)

    assert isinstance(root, PathObject)
    assert root.size() == 0
