import pytest

from ably import AblyVCDiffDecoder
from ably.types.message import Message
from ably.types.mixins import DecodingContext
from ably.util.exceptions import AblyException

# A VCDIFF window containing only an ADD instruction, independent of source bytes.
DELTA = bytes.fromhex('d6c3c40000000b0500050100') + b'hello' + bytes([6])


def delta_message():
    return {
        'id': 'next',
        'data': DELTA,
        'encoding': 'utf-8/vcdiff',
        'extras': {'delta': {'from': 'initial'}},
    }


@pytest.mark.parametrize('base', ['', b'', bytearray(), b'previous'])
def test_delta_decodes_from_present_base(base):
    context = DecodingContext(base, 'initial', AblyVCDiffDecoder())

    message = Message.from_encoded(delta_message(), context=context)

    assert message.data == 'hello'
    assert context.base_payload == b'hello'
    assert context.last_message_id == 'next'


def test_delta_still_rejects_missing_base():
    context = DecodingContext(None, 'initial', AblyVCDiffDecoder())

    with pytest.raises(AblyException) as error:
        Message.from_encoded(delta_message(), context=context)

    assert error.value.code == 40018
    assert context.base_payload is None
    assert context.last_message_id == 'initial'


def test_batch_chains_delta_after_empty_full_message():
    context = DecodingContext(vcdiff_decoder=AblyVCDiffDecoder())

    messages = Message.from_encoded_array([
        {'id': 'initial', 'data': '', 'encoding': 'utf-8'},
        delta_message(),
    ], context=context)

    assert [message.data for message in messages] == ['', 'hello']
    assert context.base_payload == b'hello'
    assert context.last_message_id == 'next'
