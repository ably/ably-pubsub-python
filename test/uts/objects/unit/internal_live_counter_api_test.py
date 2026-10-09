"""Derived from uts/objects/unit/internal_live_counter_api.md in ably/specification.

Spec points: RTLC5, RTLC5c, RTLC11, RTLC11b1, RTLC12, RTLC12e1, RTLC12e2, RTLC12e3, RTLC12e5,
RTLC12g, RTLC13, RTLC13b

The specification reaches `InternalLiveCounter` through the untyped `PathObject` and
`Instance`; ably-python partitions those by type (RTTS), so a counter's `value`,
`increment`, `decrement` and `subscribe` are read through `as_live_counter()`.

The tests that capture what the client sends use the standard synced-channel mock, which
is the specification's hand-written one: it records each OBJECT message and then ACKs it
with `ack_serial(msgSerial, i)`, so every awaited write resolves (RTO20). Captured messages
are the decoded JSON wire, and each captured operation is also compared with the whole
protocol v6 operation, so a legacy (v5) payload field fails the test.
"""

import pytest

from ably.pubsub.objects.objectmessage import ObjectOperationAction
from ably.pubsub.util.exceptions import AblyException
from test.uts.helpers.client import poll_until
from test.uts.objects.helpers.standard_test_pool import (
    build_counter_inc,
    build_object_message,
    objects_connected_message,
    setup_synced_channel,
    standard_mock_websocket,
)


def _capturing_mock_websocket(captured):
    """The specification's capturing mock: the standard synced-channel conversation, with each
    OBJECT message the client sends appended to `captured` before it is ACKed."""
    return standard_mock_websocket(
        on_object=captured.append,
        connected=objects_connected_message(connection_key='key-1'),
    )


# UTS: objects/unit/RTLC5/value-returns-data-0
async def test_rtlc5_value_returns_data():
    ctx = await setup_synced_channel('test')

    counter = ctx.root.get('score')
    assert counter.as_live_counter().value() == 100


# UTS: objects/unit/RTLC12/increment-sends-counter-inc-0
async def test_rtlc12_increment_sends_counter_inc():
    captured = []
    ctx = await setup_synced_channel('test', mock_ws=_capturing_mock_websocket(captured))

    await ctx.root.get('score').as_live_counter().increment(25)

    assert len(captured) == 1
    obj_msg = captured[0]['state'][0]
    assert obj_msg['operation']['action'] == ObjectOperationAction.COUNTER_INC
    assert obj_msg['operation']['objectId'] == 'counter:score@1000'
    assert obj_msg['operation']['counterInc']['number'] == 25
    # The whole operation is the v6 wire shape: a numeric action and a `counterInc` payload
    assert obj_msg['operation'] == {
        'action': int(ObjectOperationAction.COUNTER_INC),
        'objectId': 'counter:score@1000',
        'counterInc': {'number': 25},
    }


# UTS: objects/unit/RTLC12/increment-applies-locally-0
async def test_rtlc12_increment_applies_locally():
    ctx = await setup_synced_channel('test')

    await ctx.root.get('score').as_live_counter().increment(50)

    assert ctx.root.get('score').as_live_counter().value() == 150


# UTS: objects/unit/RTLC12e1/increment-non-number-0
async def test_rtlc12e1_increment_non_number():
    ctx = await setup_synced_channel('test')

    with pytest.raises(AblyException) as excinfo:
        await ctx.root.get('score').as_live_counter().increment('not_a_number')

    assert excinfo.value.code == 40003


# UTS: objects/unit/RTLC13/decrement-negates-0
async def test_rtlc13_decrement_negates():
    captured = []
    ctx = await setup_synced_channel('test', mock_ws=_capturing_mock_websocket(captured))

    await ctx.root.get('score').as_live_counter().decrement(15)

    assert captured[0]['state'][0]['operation']['counterInc']['number'] == -15
    assert ctx.root.get('score').as_live_counter().value() == 85
    assert captured[0]['state'][0]['operation'] == {
        'action': int(ObjectOperationAction.COUNTER_INC),
        'objectId': 'counter:score@1000',
        'counterInc': {'number': -15},
    }


# UTS: objects/unit/RTLC11/counter-update-on-inc-0
async def test_rtlc11_counter_update_on_inc():
    ctx = await setup_synced_channel('test')

    updates = []
    instance = ctx.root.get('score').instance()
    instance.as_live_counter().subscribe(lambda event: updates.append(event))

    ctx.mock_ws.send_to_client(build_object_message('test', [
        build_counter_inc('counter:score@1000', 7, '99', 'remote-site'),
    ]))

    await poll_until(lambda: len(updates) >= 1, timeout=5, description='the counter update to be delivered')

    assert updates[0].message.operation.counter_inc.number == 7


# The `null` row applies: in Python `None` is distinguishable from an omitted amount, which
# defaults to 1. `True` is an `int` in Python and must still be rejected as a non-number.
INVALID_AMOUNTS = [
    pytest.param(None, id='null'),
    pytest.param(float('nan'), id='NaN'),
    pytest.param(float('inf'), id='Infinity'),
    pytest.param(float('-inf'), id='-Infinity'),
    pytest.param('10', id='string'),
    pytest.param(True, id='boolean'),
    pytest.param([1, 2], id='array'),
    pytest.param({'n': 1}, id='object'),
]


# UTS: objects/unit/RTLC12e1/increment-invalid-amounts-table-0
@pytest.mark.parametrize('amount', INVALID_AMOUNTS)
async def test_rtlc12e1_increment_invalid_amounts_table(amount):
    ctx = await setup_synced_channel('test')

    with pytest.raises(AblyException) as excinfo:
        await ctx.root.get('score').as_live_counter().increment(amount)

    assert excinfo.value.code == 40003
