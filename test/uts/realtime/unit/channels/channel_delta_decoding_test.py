"""Derived from uts/realtime/unit/channels/channel_delta_decoding.md in ably/specification.

Spec points: RTL18, RTL18a, RTL18b, RTL18c, RTL19, RTL19a, RTL19b, RTL19c, RTL20, RTL21,
PC3, PC3a

The mock vcdiff encoder and decoder of uts/realtime/unit/helpers/mock_vcdiff.md are
built below rather than in `test/uts/helpers`, since only this specification uses them.
Only the binary form of the encoder is implemented: ably-python's plugin seam is the
binary-only `VCDiffDecoder` (VD2a), so the string overloads the specification offers as
a test-setup convenience have nothing to attach to. `encode` takes text or bytes and
always produces the binary delta the decoder reads.

Deltas travel as raw bytes, which the default msgpack protocol carries directly; only
the RTL19a test, which is about the base64 step, base64-encodes its payloads.

Where a message's encoding ends at `vcdiff` there is no `utf-8` step to turn the delta
result back into text, so the SDK delivers bytes and the assertions below are written
against bytes where the specification writes a string literal. See
[deviations.md](../../../deviations.md).
"""

import base64
import uuid

from ably.realtime.connection import ConnectionState
from ably.transport.websockettransport import ProtocolMessageAction
from ably.types.channelstate import ChannelState
from ably.types.options import VCDiffDecoder
from test.uts.helpers.client import await_connection_state, poll_until, realtime_client
from test.uts.helpers.clock import settle
from test.uts.helpers.deviations import deviation
from test.uts.helpers.mock_websocket import (
    MockWebSocket,
    attached_message,
    connected_message,
    message_protocol_message,
)

CONNECTED_MESSAGE = connected_message('connection-id', connectionKey='connection-key')


def random_id():
    return uuid.uuid4().hex[:8]


def _to_bytes(value):
    return value.encode('utf-8') if isinstance(value, str) else bytes(value)


def _base64url_encode(data):
    return base64.urlsafe_b64encode(data).decode('ascii').rstrip('=')


def _base64url_decode(text):
    return base64.urlsafe_b64decode(text + '=' * (-len(text) % 4))


class MockVCDiffEncoder:
    """Builds the deterministic delta the mock decoder reads.

    A delta is `base64url(base) + '/' + base64url(value)` as UTF-8 bytes, so the base
    the delta was built against is carried inside it and a wrong stored base payload
    shows up as a decode failure rather than as a wrong result.
    """

    def encode(self, base, value):
        return f'{_base64url_encode(_to_bytes(base))}/{_base64url_encode(_to_bytes(value))}'.encode()


class MockVCDiffDecoder(VCDiffDecoder):
    """The VD2a decoder side of the mock, validating the base it is handed.

    `on_decode` is called with the arguments the SDK passed before the delta is read,
    which is how a test inspects them or makes a particular call fail.
    """

    def __init__(self, on_decode=None):
        self.on_decode = on_decode
        self.calls = []

    def decode(self, delta: bytes, base: bytes) -> bytes:
        self.calls.append({'delta': delta, 'base': base})
        if self.on_decode is not None:
            self.on_decode(delta, base)
        parts = delta.decode('utf-8').split('/')
        if len(parts) != 2:
            raise ValueError('Invalid delta format')
        if _base64url_decode(parts[0]) != base:
            raise ValueError('Base mismatch: expected base does not match delta')
        return _base64url_decode(parts[1])


class FailingMockVCDiffDecoder(VCDiffDecoder):
    """A decoder which never decodes anything, for the RTL18 recovery tests."""

    def decode(self, delta: bytes, base: bytes) -> bytes:
        raise ValueError('Simulated vcdiff decode failure')


def delta_message(id, delta, from_id, encoding='vcdiff', **fields):
    """A message carrying `delta` as a vcdiff delta from the message `from_id`."""
    return {
        'id': id,
        'data': delta,
        'encoding': encoding,
        'extras': {'delta': {'from': from_id, 'format': 'vcdiff'}},
        **fields,
    }


def attaching_mock(channel_name, attach_messages=None, attach_replies=None):
    """A mock which connects and confirms attaches for `channel_name`.

    `attach_replies` caps how many ATTACHes are answered, so that a test can leave a
    recovery attach outstanding; every ATTACH is answered when it is None.
    """
    mock_ws = MockWebSocket(
        on_connection_attempt=lambda conn: conn.respond_with_success(CONNECTED_MESSAGE),
    )

    def on_message_from_client(msg):
        if msg.get('action') == ProtocolMessageAction.ATTACH:
            if attach_messages is not None:
                attach_messages.append(msg)
            if attach_replies is None or len(mock_ws.attaches_answered) < attach_replies:
                mock_ws.attaches_answered.append(msg)
                mock_ws.send_to_client(attached_message(channel_name))

    mock_ws.attaches_answered = []
    mock_ws.on_message_from_client = on_message_from_client
    return mock_ws


async def attached_channel(mock_ws, channel_name, **kwargs):
    """A channel attached over `mock_ws`, which every test here starts from."""
    client = realtime_client(mock_ws, **kwargs)
    channel = client.channels.get(channel_name)
    client.connect()
    await await_connection_state(client, ConnectionState.CONNECTED)
    await channel.attach()
    return channel


def recorder(received):
    """A subscribe listener appending each message it is given to `received`."""
    def record(message):
        received.append(message)
    return record


def state_recorder(state_changes):
    """A channel listener appending each state change to `state_changes`."""
    def record(state_change):
        state_changes.append(state_change)
    return record


# UTS: realtime/unit/RTL21/ascending-index-order-0
async def test_rtl21_ascending_index_order():
    channel_name = f'test-RTL21-order-{random_id()}'
    encoder = MockVCDiffEncoder()
    received_messages = []

    mock_ws = attaching_mock(channel_name)
    channel = await attached_channel(mock_ws, channel_name, vcdiff_decoder=MockVCDiffDecoder())
    await channel.subscribe(recorder(received_messages))

    base_data = 'first message'
    second_data = 'second message'
    third_data = 'third message'

    # The second and third messages are deltas from the ones before them, so they only
    # decode if the array is processed in index order
    mock_ws.send_to_client(message_protocol_message(channel_name, [
        {'id': 'serial:0', 'data': base_data, 'encoding': None},
        delta_message('serial:1', encoder.encode(base_data, second_data), from_id='serial:0'),
        delta_message('serial:2', encoder.encode(second_data, third_data), from_id='serial:1'),
    ], id='serial:0'))
    await poll_until(lambda: len(received_messages) == 3, description='all three messages arrive')

    assert received_messages[0].data == 'first message'
    assert received_messages[1].data == b'second message'
    assert received_messages[2].data == b'third message'


# UTS: realtime/unit/RTL19b/stores-base-payload-0
async def test_rtl19b_stores_base_payload():
    channel_name = f'test-RTL19b-base-{random_id()}'
    encoder = MockVCDiffEncoder()
    received_messages = []

    mock_ws = attaching_mock(channel_name)
    channel = await attached_channel(mock_ws, channel_name, vcdiff_decoder=MockVCDiffDecoder())
    await channel.subscribe(recorder(received_messages))

    mock_ws.send_to_client(message_protocol_message(channel_name, [
        {'id': 'msg-1:0', 'data': 'base payload', 'encoding': None},
    ], id='msg-1:0'))
    await poll_until(lambda: len(received_messages) == 1, description='the base message arrives')

    delta = encoder.encode('base payload', 'updated payload')
    mock_ws.send_to_client(message_protocol_message(channel_name, [
        delta_message('msg-2:0', delta, from_id='msg-1:0'),
    ], id='msg-2:0'))
    await poll_until(lambda: len(received_messages) == 2, description='the delta message arrives')

    assert received_messages[0].data == 'base payload'
    assert received_messages[1].data == b'updated payload'


# UTS: realtime/unit/RTL19b/json-wire-form-base-1
async def test_rtl19b_json_wire_form_base():
    channel_name = f'test-RTL19b-json-base-{random_id()}'
    encoder = MockVCDiffEncoder()
    received_messages = []

    mock_ws = attaching_mock(channel_name)
    channel = await attached_channel(mock_ws, channel_name, vcdiff_decoder=MockVCDiffDecoder())
    await channel.subscribe(recorder(received_messages))

    json_string = '{"foo":"bar","count":1}'
    mock_ws.send_to_client(message_protocol_message(channel_name, [
        {'id': 'msg-1:0', 'data': json_string, 'encoding': 'json'},
    ], id='msg-1:0'))
    await poll_until(lambda: len(received_messages) == 1, description='the base message arrives')

    # The delta is computed against the JSON string on the wire, not the parsed object,
    # so it only decodes if the wire form was stored as the base payload
    new_json_string = '{"foo":"baz","count":2}'
    delta = encoder.encode(json_string, new_json_string)
    mock_ws.send_to_client(message_protocol_message(channel_name, [
        delta_message('msg-2:0', delta, from_id='msg-1:0', encoding='utf-8/vcdiff'),
    ], id='msg-2:0'))
    await poll_until(lambda: len(received_messages) == 2, description='the delta message arrives')

    assert received_messages[0].data == {'foo': 'bar', 'count': 1}
    assert received_messages[1].data == new_json_string


# UTS: realtime/unit/RTL19a/base64-decoded-before-store-0
async def test_rtl19a_base64_decoded_before_store():
    channel_name = f'test-RTL19a-base64-{random_id()}'
    encoder = MockVCDiffEncoder()
    received_messages = []

    mock_ws = attaching_mock(channel_name)
    channel = await attached_channel(mock_ws, channel_name, vcdiff_decoder=MockVCDiffDecoder())
    await channel.subscribe(recorder(received_messages))

    base_binary = bytes([0x48, 0x65, 0x6C, 0x6C, 0x6F])
    mock_ws.send_to_client(message_protocol_message(channel_name, [
        {'id': 'msg-1:0', 'data': 'SGVsbG8=', 'encoding': 'base64'},
    ], id='msg-1:0'))
    await poll_until(lambda: len(received_messages) == 1, description='the base message arrives')

    new_binary = bytes([0x57, 0x6F, 0x72, 0x6C, 0x64])
    delta = encoder.encode(base_binary, new_binary)
    mock_ws.send_to_client(message_protocol_message(channel_name, [
        delta_message('msg-2:0', base64.b64encode(delta).decode('ascii'),
                      from_id='msg-1:0', encoding='vcdiff/base64'),
    ], id='msg-2:0'))
    await poll_until(lambda: len(received_messages) == 2, description='the delta message arrives')

    assert received_messages[0].data == base_binary
    assert received_messages[1].data == new_binary


# UTS: realtime/unit/RTL19c/delta-result-becomes-base-0
async def test_rtl19c_delta_result_becomes_base():
    channel_name = f'test-RTL19c-chain-{random_id()}'
    encoder = MockVCDiffEncoder()
    received_messages = []

    mock_ws = attaching_mock(channel_name)
    channel = await attached_channel(mock_ws, channel_name, vcdiff_decoder=MockVCDiffDecoder())
    await channel.subscribe(recorder(received_messages))

    mock_ws.send_to_client(message_protocol_message(channel_name, [
        {'id': 'msg-1:0', 'data': 'value-A', 'encoding': None},
    ], id='msg-1:0'))
    await poll_until(lambda: len(received_messages) == 1, description='the base message arrives')

    mock_ws.send_to_client(message_protocol_message(channel_name, [
        delta_message('msg-2:0', encoder.encode('value-A', 'value-B'), from_id='msg-1:0'),
    ], id='msg-2:0'))
    await poll_until(lambda: len(received_messages) == 2, description='the first delta arrives')

    # The third message is a delta from the second, so it only decodes if the result of
    # the first delta became the base payload
    mock_ws.send_to_client(message_protocol_message(channel_name, [
        delta_message('msg-3:0', encoder.encode('value-B', 'value-C'), from_id='msg-2:0'),
    ], id='msg-3:0'))
    await poll_until(lambda: len(received_messages) == 3, description='the second delta arrives')

    assert received_messages[0].data == 'value-A'
    assert received_messages[1].data == b'value-B'
    assert received_messages[2].data == b'value-C'


# UTS: realtime/unit/RTL20/mismatched-id-triggers-recovery-0
async def test_rtl20_mismatched_id_triggers_recovery():
    channel_name = f'test-RTL20-mismatch-{random_id()}'
    encoder = MockVCDiffEncoder()
    state_changes = []
    attach_messages = []

    mock_ws = attaching_mock(channel_name, attach_messages)
    channel = await attached_channel(mock_ws, channel_name, vcdiff_decoder=MockVCDiffDecoder())
    channel.on(state_recorder(state_changes))

    mock_ws.send_to_client(message_protocol_message(channel_name, [
        {'id': 'msg-1:0', 'data': 'base payload', 'encoding': None},
    ], id='msg-1:0', channelSerial='serial-1'))
    await settle()

    state_changes.clear()
    initial_attach_count = len(attach_messages)

    delta = encoder.encode('base payload', 'new payload')
    mock_ws.send_to_client(message_protocol_message(channel_name, [
        delta_message('msg-2:0', delta, from_id='msg-999:0'),
    ], id='msg-2:0'))
    await poll_until(lambda: len(attach_messages) > initial_attach_count,
                     description='a recovery ATTACH is sent')

    # RTL18c: the recovery ATTACH carries the serial of the last message that decoded
    recovery_attach = attach_messages[-1]
    assert recovery_attach['channelSerial'] == 'serial-1'

    attaching = [change for change in state_changes if change.current == ChannelState.ATTACHING]
    assert len(attaching) == 1
    assert attaching[0].reason.code == 40018


# UTS: realtime/unit/RTL20/last-id-updated-on-decode-1
async def test_rtl20_last_id_updated_on_decode():
    channel_name = f'test-RTL20-id-update-{random_id()}'
    encoder = MockVCDiffEncoder()
    received_messages = []

    mock_ws = attaching_mock(channel_name)
    channel = await attached_channel(mock_ws, channel_name, vcdiff_decoder=MockVCDiffDecoder())
    await channel.subscribe(recorder(received_messages))

    mock_ws.send_to_client(message_protocol_message(channel_name, [
        {'id': 'serial:0', 'data': 'first', 'encoding': None},
        {'id': 'serial:1', 'data': 'second', 'encoding': None},
    ], id='serial:0'))
    await poll_until(lambda: len(received_messages) == 2, description='both messages arrive')

    # The delta references the last message of the previous array, so it only decodes if
    # that id was the one stored
    mock_ws.send_to_client(message_protocol_message(channel_name, [
        delta_message('msg-2:0', encoder.encode('second', 'third'), from_id='serial:1'),
    ], id='msg-2:0'))
    await poll_until(lambda: len(received_messages) == 3, description='the delta message arrives')

    assert received_messages[0].data == 'first'
    assert received_messages[1].data == 'second'
    assert received_messages[2].data == b'third'


# UTS: realtime/unit/PC3/vcdiff-plugin-decodes-0
async def test_pc3_vcdiff_plugin_decodes():
    channel_name = f'test-PC3-decode-{random_id()}'
    encoder = MockVCDiffEncoder()
    decode_calls = []

    def on_decode(delta, base):
        decode_calls.append({'delta': delta, 'base': base})

    received_messages = []

    mock_ws = attaching_mock(channel_name)
    channel = await attached_channel(
        mock_ws, channel_name, vcdiff_decoder=MockVCDiffDecoder(on_decode=on_decode))
    await channel.subscribe(recorder(received_messages))

    mock_ws.send_to_client(message_protocol_message(channel_name, [
        {'id': 'msg-1:0', 'data': 'hello world', 'encoding': None},
    ], id='msg-1:0'))
    await poll_until(lambda: len(received_messages) == 1, description='the base message arrives')

    delta = encoder.encode('hello world', 'goodbye world')
    mock_ws.send_to_client(message_protocol_message(channel_name, [
        delta_message('msg-2:0', delta, from_id='msg-1:0'),
    ], id='msg-2:0'))
    await poll_until(lambda: len(received_messages) == 2, description='the delta message arrives')

    assert len(decode_calls) == 1
    # PC3a: a string base payload reaches the decoder as its UTF-8 bytes
    assert decode_calls[0]['base'] == b'hello world'
    assert decode_calls[0]['delta'] == delta

    assert received_messages[1].data == b'goodbye world'


# UTS: realtime/unit/PC3/no-plugin-fails-1
@deviation
async def test_pc3_no_plugin_fails():
    channel_name = f'test-PC3-no-plugin-{random_id()}'
    state_changes = []

    mock_ws = attaching_mock(channel_name)
    channel = await attached_channel(mock_ws, channel_name)
    channel.on(state_recorder(state_changes))

    mock_ws.send_to_client(message_protocol_message(channel_name, [
        delta_message('msg-1:0', 'some-delta-data', from_id='msg-0:0'),
    ], id='msg-1:0'))
    await poll_until(lambda: channel.state == ChannelState.FAILED,
                     description='the channel fails for want of a vcdiff decoder')

    assert channel.error_reason.code == 40019


# UTS: realtime/unit/RTL18/decode-failure-recovery-0
async def test_rtl18_decode_failure_recovery():
    channel_name = f'test-RTL18-recovery-{random_id()}'
    state_changes = []
    attach_messages = []
    received_messages = []

    mock_ws = attaching_mock(channel_name, attach_messages)
    channel = await attached_channel(
        mock_ws, channel_name, vcdiff_decoder=FailingMockVCDiffDecoder())
    channel.on(state_recorder(state_changes))
    await channel.subscribe(recorder(received_messages))

    mock_ws.send_to_client(message_protocol_message(channel_name, [
        {'id': 'msg-1:0', 'data': 'base payload', 'encoding': None},
    ], id='msg-1:0', channelSerial='serial-100'))
    await poll_until(lambda: len(received_messages) == 1, description='the base message arrives')

    state_changes.clear()
    initial_attach_count = len(attach_messages)

    mock_ws.send_to_client(message_protocol_message(channel_name, [
        delta_message('msg-2:0', b'fake-delta-payload', from_id='msg-1:0'),
    ], id='msg-2:0', channelSerial='serial-200'))
    await poll_until(lambda: len(attach_messages) > initial_attach_count,
                     description='a recovery ATTACH is sent')
    await settle()

    # RTL18b: the message the decoder could not read was discarded
    assert len(received_messages) == 1
    assert received_messages[0].data == 'base payload'

    # RTL18c: the recovery ATTACH carries the serial of the last message that decoded
    assert attach_messages[-1]['channelSerial'] == 'serial-100'

    attaching = [change for change in state_changes if change.current == ChannelState.ATTACHING]
    assert len(attaching) == 1
    assert attaching[0].reason.code == 40018


# UTS: realtime/unit/RTL18c/recovery-completes-on-attached-0
async def test_rtl18c_recovery_completes_on_attached():
    channel_name = f'test-RTL18c-complete-{random_id()}'
    received_messages = []
    decode_attempts = []

    def fail_first(delta, base):
        decode_attempts.append(delta)
        if len(decode_attempts) == 1:
            raise ValueError('Simulated decode failure')

    mock_ws = attaching_mock(channel_name)
    channel = await attached_channel(
        mock_ws, channel_name, vcdiff_decoder=MockVCDiffDecoder(on_decode=fail_first))
    await channel.subscribe(recorder(received_messages))

    mock_ws.send_to_client(message_protocol_message(channel_name, [
        {'id': 'msg-1:0', 'data': 'original base', 'encoding': None},
    ], id='msg-1:0', channelSerial='serial-1'))
    await poll_until(lambda: len(received_messages) == 1, description='the base message arrives')

    mock_ws.send_to_client(message_protocol_message(channel_name, [
        delta_message('msg-2:0', b'bad-delta', from_id='msg-1:0'),
    ], id='msg-2:0', channelSerial='serial-2'))
    await poll_until(lambda: len(decode_attempts) == 1, description='the delta fails to decode')

    # The server confirms the recovery ATTACH, which returns the channel to ATTACHED
    await poll_until(lambda: channel.state == ChannelState.ATTACHED,
                     description='the channel recovers to ATTACHED')

    mock_ws.send_to_client(message_protocol_message(channel_name, [
        {'id': 'msg-3:0', 'data': 'fresh after recovery', 'encoding': None},
    ], id='msg-3:0', channelSerial='serial-3'))
    await poll_until(lambda: len(received_messages) == 2,
                     description='the message sent after recovery arrives')

    assert channel.state == ChannelState.ATTACHED
    # RTL18b: the failed delta was discarded, so only the base and the fresh message arrived
    assert received_messages[0].data == 'original base'
    assert received_messages[1].data == 'fresh after recovery'


# UTS: realtime/unit/RTL18/single-recovery-at-time-1
async def test_rtl18_single_recovery_at_time():
    channel_name = f'test-RTL18-single-recovery-{random_id()}'
    attach_messages = []

    # Only the first ATTACH is answered, so the recovery attach stays outstanding
    mock_ws = attaching_mock(channel_name, attach_messages, attach_replies=1)
    channel = await attached_channel(
        mock_ws, channel_name, vcdiff_decoder=FailingMockVCDiffDecoder())

    initial_attach_count = len(attach_messages)

    mock_ws.send_to_client(message_protocol_message(channel_name, [
        {'id': 'msg-1:0', 'data': 'base', 'encoding': None},
    ], id='msg-1:0', channelSerial='serial-1'))
    await settle()

    mock_ws.send_to_client(message_protocol_message(channel_name, [
        delta_message('msg-2:0', b'bad-delta-1', from_id='msg-1:0'),
    ], id='msg-2:0'))
    await poll_until(lambda: channel.state == ChannelState.ATTACHING,
                     description='the first failure starts recovery')

    mock_ws.send_to_client(message_protocol_message(channel_name, [
        delta_message('msg-3:0', b'bad-delta-2', from_id='msg-2:0'),
    ], id='msg-3:0'))
    await settle()

    assert len(attach_messages) - initial_attach_count == 1
