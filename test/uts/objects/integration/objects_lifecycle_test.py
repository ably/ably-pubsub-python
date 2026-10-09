"""Derived from uts/objects/integration/objects_lifecycle_test.md in ably/specification.

Spec points: RTO23, RTPO15, RTPO17

End to end against the sandbox: connect, sync, create and mutate objects through the
root `PathObject`, and read the result from a second client. Only the public API is used.

The specification carries a `## Protocol Variants` section, so every test runs once per
protocol and passes `use_binary_protocol` to each client it builds. Provisioning over REST
is a JSON request whichever protocol the realtime client speaks.

The specification writes its reads and writes against an untyped `PathObject`.
ably-python's `PathObject` is partitioned by type (RTTS), so a counter's `value()` and
`increment()` are reached through `as_live_counter()` and a primitive's `value()` through
`as_primitive()`; `root` is already a `LiveMapPathObject`, so `set` and `size` are called on
it directly. That is a difference of spelling, not of behaviour.

`AWAIT_STATE` for CONNECTED waits ten seconds, the figure the realtime integration tier
uses for a connect over the network. The specification leaves `channel.object.get()`
unbounded; it is bounded here at the fifteen seconds `objects_gc_test.md` gives the same
call, so that a sync that never completes fails with a message naming it rather than at the
package timeout. Clients are closed by the suite's fixture.
"""

import asyncio

from ably.pubsub.realtime.connection import ConnectionState
from ably.pubsub.server import LiveCounter, LiveMap, PathObject
from test.uts.helpers.client import await_connection_state, sandbox_realtime_client, wall_clock_poll_until
from test.uts.helpers.sandbox import random_id
from test.uts.objects.helpers.standard_test_pool import objects_channel_options, provision_objects_via_rest

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


async def synced_pair(api_key, channel_name, use_binary_protocol):
    """The two clients, channels and roots every propagation test opens with."""
    client_a = await connected_client(api_key, use_binary_protocol)
    client_b = await connected_client(api_key, use_binary_protocol)

    channel_a = client_a.channels.get(channel_name, objects_channel_options())
    channel_b = client_b.channels.get(channel_name, objects_channel_options())

    root_a = await synced_root(channel_a)
    root_b = await synced_root(channel_b)
    return root_a, root_b


# UTS: objects/integration/RTO23-RTPO15/set-primitive-propagates-0
async def test_rto23_rtpo15_set_primitive_propagates(realtime_sandbox, use_binary_protocol):
    channel_name = 'objects-lifecycle-' + random_id()
    root_a, root_b = await synced_pair(realtime_sandbox.key_str, channel_name, use_binary_protocol)

    # Client A sets a value
    await root_a.set('greeting', 'hello')

    # Client B subscribes and waits for the update
    events_b = []
    root_b.subscribe(events_b.append)
    await wall_clock_poll_until(
        lambda: root_b.get('greeting').as_primitive().value() == 'hello',
        description="client B to read greeting == 'hello'")

    assert root_b.get('greeting').as_primitive().value() == 'hello'


# UTS: objects/integration/RTPO15/set-counter-value-type-0
async def test_rtpo15_set_counter_value_type(realtime_sandbox, use_binary_protocol):
    channel_name = 'objects-counter-create-' + random_id()
    root_a, root_b = await synced_pair(realtime_sandbox.key_str, channel_name, use_binary_protocol)

    await root_a.set('my_counter', LiveCounter.create(42))
    await wall_clock_poll_until(
        lambda: root_b.get('my_counter').as_live_counter().value() == 42,
        description='client B to read my_counter == 42')

    assert root_b.get('my_counter').as_live_counter().value() == 42
    assert root_b.get('my_counter').instance() is not None


# UTS: objects/integration/RTPO17/increment-propagates-0
async def test_rtpo17_increment_propagates(realtime_sandbox, use_binary_protocol):
    channel_name = 'objects-increment-' + random_id()
    root_a, root_b = await synced_pair(realtime_sandbox.key_str, channel_name, use_binary_protocol)

    # Create a counter first
    await root_a.set('hits', LiveCounter.create(0))
    await wall_clock_poll_until(
        lambda: root_b.get('hits').as_live_counter().value() == 0,
        description='client B to read hits == 0')

    # Increment it
    await root_a.get('hits').as_live_counter().increment(10)
    await wall_clock_poll_until(
        lambda: root_b.get('hits').as_live_counter().value() == 10,
        description='client B to read hits == 10')

    assert root_a.get('hits').as_live_counter().value() == 10
    assert root_b.get('hits').as_live_counter().value() == 10


# UTS: objects/integration/RTPO15/set-map-value-type-0
async def test_rtpo15_set_map_value_type(realtime_sandbox, use_binary_protocol):
    channel_name = 'objects-map-create-' + random_id()
    root_a, root_b = await synced_pair(realtime_sandbox.key_str, channel_name, use_binary_protocol)

    await root_a.set('settings', LiveMap.create({
        'theme': 'dark',
        'fontSize': 14,
    }))
    await wall_clock_poll_until(
        lambda: root_b.get('settings').get('theme').as_primitive().value() == 'dark',
        description="client B to read settings.theme == 'dark'")

    assert root_b.get('settings').get('theme').as_primitive().value() == 'dark'
    assert root_b.get('settings').get('fontSize').as_primitive().value() == 14


# UTS: objects/integration/RTO23/get-returns-path-object-0
async def test_rto23_get_returns_path_object(realtime_sandbox, use_binary_protocol):
    channel_name = 'objects-get-root-' + random_id()

    client = await connected_client(realtime_sandbox.key_str, use_binary_protocol)
    channel = client.channels.get(channel_name, objects_channel_options())

    root = await synced_root(channel)

    assert isinstance(root, PathObject)
    assert root.path() == ''
    assert root.size() == 0


# UTS: objects/integration/RTPO15/rest-provisioned-data-sync-0
async def test_rtpo15_rest_provisioned_data_sync(realtime_sandbox, use_binary_protocol):
    channel_name = 'objects-rest-provision-' + random_id()

    # Provision data via REST before any realtime client connects
    await provision_objects_via_rest(realtime_sandbox.key_str, channel_name, [
        {
            'mapSet': {'key': 'provisioned', 'value': {'string': 'from_rest'}},
            'objectId': 'root',
        },
    ])

    client = await connected_client(realtime_sandbox.key_str, use_binary_protocol)
    channel = client.channels.get(channel_name, objects_channel_options())
    root = await synced_root(channel)

    assert root.get('provisioned').as_primitive().value() == 'from_rest'
