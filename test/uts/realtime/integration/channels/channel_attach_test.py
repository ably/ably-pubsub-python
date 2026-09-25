"""Derived from uts/realtime/integration/channels/channel_attach_test.md in ably/specification.

Spec points: RTL4, RTL4c, RTL5, RTL5d, RTL14

There is no `## Protocol Variants` section, so these run against JSON only and take no
`use_binary_protocol`; `sandbox_realtime_client` already defaults to it.

`RealtimeChannel.publish()` takes its arguments positionally. The keyword form the
specification writes, which `RestChannel.publish()` does accept, raises
`ValueError: publish() expects either (name, data) or a message object or array of
messages` before anything reaches the server.

The specification's `AWAIT_STATE` for CONNECTED is given ten seconds here. `await_connection_state`
defaults to five, which is the budget a mock-backed test needs; a real connect to the sandbox
opens a websocket over the network, and ten is the figure the sibling `channel_history_test.md`
spells out for the same wait.
"""

import pytest

from ably.realtime.channel import ChannelState
from ably.realtime.connection import ConnectionState
from ably.util.exceptions import AblyException
from test.uts.helpers.client import await_connection_state, sandbox_realtime_client
from test.uts.helpers.sandbox import random_id


async def connected_client(key):
    """A realtime client built as the specification's setup builds one, already CONNECTED."""
    client = sandbox_realtime_client(key, auto_connect=False)
    client.connect()
    await await_connection_state(client, ConnectionState.CONNECTED, timeout=10)
    return client


# UTS: realtime/integration/RTL4c/attach-succeeds-0
async def test_rtl4c_attach_succeeds(realtime_sandbox):
    client = await connected_client(realtime_sandbox.key_str)

    channel = client.channels.get('attach-RTL4c-' + random_id())
    assert channel.state == ChannelState.INITIALIZED

    await channel.attach()

    assert channel.state == ChannelState.ATTACHED
    assert channel.error_reason is None


# UTS: realtime/integration/RTL5d/detach-succeeds-0
async def test_rtl5d_detach_succeeds(realtime_sandbox):
    client = await connected_client(realtime_sandbox.key_str)

    channel = client.channels.get('detach-RTL5d-' + random_id())
    await channel.attach()
    assert channel.state == ChannelState.ATTACHED

    await channel.detach()

    assert channel.state == ChannelState.DETACHED


# UTS SPEC ERROR: the section heading and its prose say the channel transitions to FAILED
# on a channel-scoped ERROR, but the test steps below say the opposite — a subscribe-only
# key attaches successfully to any channel — and the assertions never read the channel
# state. The steps are what the server does, so they are what is derived here.
# UTS: realtime/integration/RTL14/insufficient-capability-failed-0
async def test_rtl14_insufficient_capability_failed(realtime_sandbox):
    # keys[3] is the subscribe-only key, {"*": ["subscribe"]}. Read off the key rather
    # than assumed, so that a change to the app setup shows up here rather than turning
    # the test into one that proves nothing.
    subscribe_only_key = realtime_sandbox.key(3)
    assert subscribe_only_key.capability == {'*': ['subscribe']}

    client = await connected_client(subscribe_only_key.key_str)

    channel = client.channels.get('publish-not-allowed-' + random_id())

    # Attach succeeds: a subscribe-only key can attach to any channel.
    await channel.attach()
    assert channel.state == ChannelState.ATTACHED

    # The publish is refused: the key lacks the publish capability.
    with pytest.raises(AblyException) as excinfo:
        await channel.publish('test', 'data')

    assert excinfo.value.code == 40160
    assert excinfo.value.status_code == 401

    # The error is channel-scoped, so the connection is left alone.
    assert client.connection.state == ConnectionState.CONNECTED
