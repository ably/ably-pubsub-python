"""Derived from uts/realtime/unit/channels/channel_options.md in ably/specification.

Spec points: DO2a, RTL16, RTL16a, RTS3b, RTS3c, RTS3c1, RTS5, RTS5a, RTS5a1,
RTS5a2, TB2, TB2c, TB2d, TB3, TB4

`ChannelOptions.cipher` is the specification's `cipherParams`, and the options a
channel carries are the mapping `ChannelOptions.to_dict()` produces rather than
a `ChannelOptions` object, so `channel.options['params']` stands in for the
specification's `channel.options.params`.
"""

import asyncio
import base64
from urllib.parse import parse_qs

import pytest

from ably.realtime.connection import ConnectionState
from ably.transport.websockettransport import ProtocolMessageAction
from ably.types.channelmode import ChannelMode
from ably.types.channeloptions import ChannelOptions
from ably.types.channelstate import ChannelState
from ably.util.crypto import get_default_params
from ably.util.exceptions import AblyException
from test.uts.helpers.client import (
    await_channel_state,
    await_connection_state,
    realtime_client,
)
from test.uts.helpers.deviations import deviation
from test.uts.helpers.mock_websocket import (
    CONNECTED_MESSAGE,
    MockWebSocket,
    attached_message,
)

# How long an operation which the specification expects to settle is given
# before a test calls it hung
OPERATION_TIMEOUT = 1.0

# A 256-bit key, base64 encoded as the specification writes it
CIPHER_KEY = 'MDEyMzQ1Njc4OTAxMjM0NTY3ODkwMTIzNDU2Nzg5MDE='


async def connected_client(mock_ws, **kwargs):
    """A client connected through `mock_ws`, which the channel tests open with."""
    client = realtime_client(mock_ws, **kwargs)
    client.connect()
    await await_connection_state(client, ConnectionState.CONNECTED)
    return client


def attaching_mock():
    """A mock which connects and then leaves every ATTACH unanswered."""
    mock_ws = MockWebSocket(
        on_connection_attempt=lambda conn: conn.respond_with_success(CONNECTED_MESSAGE),
    )
    return mock_ws


def attached_mock(attach_messages):
    """A mock which connects and answers each ATTACH with an ATTACHED."""
    mock_ws = MockWebSocket(
        on_connection_attempt=lambda conn: conn.respond_with_success(CONNECTED_MESSAGE),
    )

    def on_message_from_client(msg):
        if msg.get('action') == ProtocolMessageAction.ATTACH:
            attach_messages.append(msg)
            mock_ws.send_to_client(attached_message(msg.get('channel')))

    mock_ws.on_message_from_client = on_message_from_client
    return mock_ws


# UTS: realtime/unit/TB2/channel-options-attributes-0
async def test_tb2_channel_options_attributes():
    options = ChannelOptions()

    assert options.cipher is None
    assert options.params is None
    assert options.modes is None
    # TB4's `attachOnSubscribe` is not among ChannelOptions' attributes; see the
    # TB4 test below


# UTS: realtime/unit/TB2c/options-with-params-0
async def test_tb2c_options_with_params():
    options = ChannelOptions(params={'rewind': '1', 'delta': 'vcdiff'})

    assert options.params['rewind'] == '1'
    assert options.params['delta'] == 'vcdiff'


# UTS: realtime/unit/TB2d/options-with-modes-0
async def test_tb2d_options_with_modes():
    options = ChannelOptions(modes=[ChannelMode.PUBLISH, ChannelMode.SUBSCRIBE])

    assert ChannelMode.PUBLISH in options.modes
    assert ChannelMode.SUBSCRIBE in options.modes
    assert len(options.modes) == 2


# UTS: realtime/unit/TB3/with-cipher-key-0
@deviation
async def test_tb3_with_cipher_key():
    # DEVIATION: TB3's `withCipherKey` constructor is absent from `ChannelOptions`
    # (`ably/types/channeloptions.py`), which takes a `CipherParams` and offers no factory
    # that builds one from a key. `ably.util.crypto.get_default_params({'key': key})` is the
    # nearest equivalent, and it is not on ChannelOptions.
    options = ChannelOptions.with_cipher_key(CIPHER_KEY)

    assert options.cipher is not None
    assert options.cipher.algorithm.lower() == 'aes'
    assert options.cipher.key_length == 256


# UTS: realtime/unit/TB4/attach-on-subscribe-default-0
@deviation
async def test_tb4_attach_on_subscribe_default():
    # DEVIATION: `attachOnSubscribe` is absent from `ChannelOptions`
    # (`ably/types/channeloptions.py`), which accepts only cipher, params and modes, so
    # passing it raises `TypeError`. `subscribe()` always attaches (RTL7g), with no way to
    # opt out.
    options1 = ChannelOptions()
    options2 = ChannelOptions(attach_on_subscribe=False)

    assert options1.attach_on_subscribe is True
    assert options2.attach_on_subscribe is False


# UTS: realtime/unit/RTS3b/options-set-on-new-0
async def test_rts3b_options_set_on_new():
    channel_name = 'test-RTS3b'
    client = realtime_client()

    channel_options = ChannelOptions(params={'rewind': '1'}, modes=[ChannelMode.SUBSCRIBE])

    channel = client.channels.get(channel_name, channel_options)

    assert channel.options['params']['rewind'] == '1'
    assert ChannelMode.SUBSCRIBE in channel.options['modes']


# UTS: realtime/unit/RTS3c/options-updated-existing-0
async def test_rts3c_options_updated_existing():
    channel_name = 'test-RTS3c'
    client = realtime_client()

    # The specification distinguishes the two sets of options by `attachOnSubscribe`,
    # which ably-python does not have; modes serve the same purpose here, and an
    # unattached channel takes any options without reattaching
    initial_options = ChannelOptions(modes=[ChannelMode.SUBSCRIBE])
    channel = client.channels.get(channel_name, initial_options)

    new_options = ChannelOptions(cipher=get_default_params({'key': CIPHER_KEY}))
    same_channel = client.channels.get(channel_name, new_options)

    assert same_channel is channel
    assert channel.options['cipher'] is not None
    assert 'modes' not in channel.options


# UTS: realtime/unit/RTS3c1/error-reattach-params-0
async def test_rts3c1_error_reattach_params():
    channel_name = 'test-RTS3c1'
    attach_messages = []

    mock_ws = attached_mock(attach_messages)
    client = await connected_client(mock_ws)

    channel = client.channels.get(channel_name)
    await asyncio.wait_for(channel.attach(), OPERATION_TIMEOUT)
    assert channel.state == ChannelState.ATTACHED

    new_options = ChannelOptions(params={'rewind': '1'})

    with pytest.raises(AblyException) as error:
        client.channels.get(channel_name, new_options)
    assert error.value.code == 40000

    assert channel.options.get('params') is None


# UTS: realtime/unit/RTS3c1/error-reattach-modes-1
async def test_rts3c1_error_reattach_modes():
    channel_name = 'test-RTS3c1-attaching'

    mock_ws = attaching_mock()
    client = await connected_client(mock_ws)

    channel = client.channels.get(channel_name)
    attach_future = asyncio.ensure_future(channel.attach())
    await await_channel_state(channel, ChannelState.ATTACHING, OPERATION_TIMEOUT)

    new_options = ChannelOptions(modes=[ChannelMode.SUBSCRIBE])

    with pytest.raises(AblyException) as error:
        client.channels.get(channel_name, new_options)
    assert error.value.code == 40000

    attach_future.cancel()


# UTS: realtime/unit/RTL16/set-options-updates-0
async def test_rtl16_set_options_updates():
    channel_name = 'test-RTL16'
    client = realtime_client()
    channel = client.channels.get(channel_name)

    # The specification also sets `attachOnSubscribe`, which ChannelOptions does not
    # carry; see the TB4 test
    new_options = ChannelOptions(params={'delta': 'vcdiff'})
    await asyncio.wait_for(channel.set_options(new_options), OPERATION_TIMEOUT)

    assert channel.options['params']['delta'] == 'vcdiff'


# UTS: realtime/unit/RTL16a/triggers-reattach-0
@deviation
async def test_rtl16a_triggers_reattach():
    # DEVIATION: `set_options` never returns for an attached channel. It calls
    # `_attach_impl()` directly and then awaits the internal state emitter
    # (`ably/realtime/channel.py:99-102`), but the server's ATTACHED arrives while the
    # channel is still ATTACHED, so `_on_message` takes the RTL12 branch (`:722-726`) and
    # emits `update` on the public emitter alone. Nothing ever reaches the internal
    # emitter, so the await hangs. Because `_attach_impl()` is called in place of
    # `_request_state(ATTACHING)`, no ATTACHING state change is emitted either. The
    # options themselves are stored, before the reattach is requested.
    channel_name = 'test-RTL16a'
    attach_messages = []

    mock_ws = attached_mock(attach_messages)
    client = await connected_client(mock_ws)

    channel = client.channels.get(channel_name)
    await asyncio.wait_for(channel.attach(), OPERATION_TIMEOUT)
    assert channel.state == ChannelState.ATTACHED

    state_changes = []

    def record(change):
        state_changes.append(change)

    channel.on(record)

    new_options = ChannelOptions(params={'rewind': '1'})
    # The specification awaits this without a deadline; a deadline is what turns the
    # hang into a failure rather than a stuck test run
    await asyncio.wait_for(channel.set_options(new_options), OPERATION_TIMEOUT)

    assert any(change.current == ChannelState.ATTACHING for change in state_changes)
    assert channel.state == ChannelState.ATTACHED
    assert channel.options['params']['rewind'] == '1'


# UTS: realtime/unit/RTS5a/creates-derived-channel-0
@deviation
async def test_rts5a_creates_derived_channel():
    # DEVIATION: `Channels.get_derived` is absent (`ably/realtime/channel.py:964`), as is
    # `DeriveOptions`. `Channels.__getattr__` (`ably/rest/channel.py:408`) answers any
    # unknown attribute with a channel of that name, so the call raises
    # `TypeError: 'RealtimeChannel' object is not callable` rather than AttributeError.
    from ably import DeriveOptions

    base_channel_name = 'test-RTS5a'
    client = realtime_client()

    derive_options = DeriveOptions(filter="name == 'foo'")

    channel = client.channels.get_derived(base_channel_name, derive_options)

    assert channel.name.startswith('[filter=')
    assert channel.name.endswith(']' + base_channel_name)


# UTS: realtime/unit/RTS5a1/filter-base64-encoded-0
@deviation
async def test_rts5a1_filter_base64_encoded():
    # DEVIATION: derived channels are absent; see the RTS5a test.
    from ably import DeriveOptions

    base_channel_name = 'test-RTS5a1'
    client = realtime_client()

    channel_filter = "name == 'test'"
    derive_options = DeriveOptions(filter=channel_filter)

    channel = client.channels.get_derived(base_channel_name, derive_options)
    expected_encoded = base64.b64encode(channel_filter.encode()).decode()

    assert channel.name == '[filter=' + expected_encoded + ']' + base_channel_name


# UTS: realtime/unit/RTS5a2/derived-with-params-0
@deviation
async def test_rts5a2_derived_with_params():
    # DEVIATION: derived channels are absent; see the RTS5a test.
    from ably import DeriveOptions

    base_channel_name = 'test-RTS5a2'
    client = realtime_client()

    derive_options = DeriveOptions(filter="type == 'message'")
    channel_options = ChannelOptions(params={'rewind': '1', 'delta': 'vcdiff'})

    channel = client.channels.get_derived(base_channel_name, derive_options, channel_options)

    assert channel.name.endswith(']' + base_channel_name)

    qualifier = channel.name[channel.name.index('[') + 1:channel.name.index(']')]
    assert qualifier.startswith('filter=')

    assert '?' in qualifier
    parsed_params = parse_qs(qualifier.split('?')[1])
    assert parsed_params['rewind'] == ['1']
    assert parsed_params['delta'] == ['vcdiff']
    assert len(parsed_params) == 2


# UTS: realtime/unit/RTS5/get-derived-with-options-0
@deviation
async def test_rts5_get_derived_with_options():
    # DEVIATION: derived channels are absent; see the RTS5a test. `attachOnSubscribe` is
    # absent too; see the TB4 test.
    from ably import DeriveOptions

    base_channel_name = 'test-RTS5'
    client = realtime_client()

    derive_options = DeriveOptions(filter='true')
    channel_options = ChannelOptions(modes=[ChannelMode.SUBSCRIBE], attach_on_subscribe=False)

    channel = client.channels.get_derived(base_channel_name, derive_options, channel_options)

    assert ChannelMode.SUBSCRIBE in channel.options['modes']
    assert channel.options['attachOnSubscribe'] is False


# UTS: realtime/unit/DO2a/filter-attribute-0
@deviation
async def test_do2a_filter_attribute():
    # DEVIATION: `DeriveOptions` is absent from the library, so the import fails.
    from ably import DeriveOptions

    derive_options = DeriveOptions(filter="name == 'event' && data.count > 10")

    assert derive_options.filter == "name == 'event' && data.count > 10"
