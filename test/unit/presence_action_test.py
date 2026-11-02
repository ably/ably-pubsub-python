"""PresenceAction is an IntEnum (TP2), as MessageAction and AnnotationAction are.

Tests cover:
- the members and their wire values, and that a member still equals its int
- decoding: a known wire int becomes the member, an unknown one is kept as it came
- encoding: the action reaches JSON and MessagePack as a plain int
- the realtime presence map and the LEAVEs it synthesizes, which hold members
"""

import json
from enum import IntEnum
from types import SimpleNamespace

import msgpack
import pytest

import ably.pubsub.sync.types.presence as sync_presence
import ably.pubsub.types.presence as async_presence
from ably.pubsub.realtime.presence import RealtimePresence, _action_name
from ably.pubsub.types.batch import BatchPresenceSuccessResult
from ably.pubsub.types.presence import PresenceAction, PresenceMessage, make_presence_response_handler
from ably.pubsub.types.testoptions import TestOptions

WIRE_VALUES = [
    ('ABSENT', 0),
    ('PRESENT', 1),
    ('ENTER', 2),
    ('LEAVE', 3),
    ('UPDATE', 4),
]

# The generated synchronous tree has its own PresenceAction and PresenceMessage.
MODULES = [async_presence, sync_presence]


@pytest.mark.parametrize('module', MODULES)
def test_presence_action_is_an_int_enum(module):
    assert issubclass(module.PresenceAction, IntEnum)
    assert [(a.name, a.value) for a in module.PresenceAction] == WIRE_VALUES


@pytest.mark.parametrize('name,value', WIRE_VALUES)
def test_member_compares_equal_to_its_wire_int(name, value):
    action = PresenceAction[name]
    assert action == value
    assert isinstance(action, int)
    assert type(action) is not int
    assert hash(action) == hash(value)
    assert {value: name}[action] == name


@pytest.mark.parametrize('module', MODULES)
@pytest.mark.parametrize('name,value', WIRE_VALUES)
def test_decoding_wraps_the_wire_int(module, name, value):
    msg = module.PresenceMessage.from_encoded({'action': value, 'clientId': 'c'})
    assert msg.action is module.PresenceAction[name]


@pytest.mark.parametrize('module', MODULES)
def test_decoding_a_missing_action_gives_enter(module):
    msg = module.PresenceMessage.from_encoded({'clientId': 'c'})
    assert msg.action is module.PresenceAction.ENTER


@pytest.mark.parametrize('module', MODULES)
def test_decoding_an_unknown_action_keeps_the_wire_value(module):
    msg = module.PresenceMessage.from_encoded({'action': 99, 'clientId': 'c'})
    assert msg.action == 99
    assert type(msg.action) is int


def test_decoding_an_array_wraps_every_action():
    msgs = PresenceMessage.from_encoded_array([{'action': 2}, {'action': 3}, {'action': 4}])
    assert [m.action for m in msgs] == [PresenceAction.ENTER, PresenceAction.LEAVE, PresenceAction.UPDATE]
    assert all(isinstance(m.action, PresenceAction) for m in msgs)


def test_http_presence_response_wraps_actions():
    response = SimpleNamespace(to_native=lambda: [{'action': 1, 'clientId': 'a'}, {'action': 3, 'clientId': 'b'}])
    msgs = make_presence_response_handler(None)(response)
    assert [m.action for m in msgs] == [PresenceAction.PRESENT, PresenceAction.LEAVE]
    assert all(isinstance(m.action, PresenceAction) for m in msgs)


def test_batch_presence_result_wraps_actions():
    result = BatchPresenceSuccessResult.from_dict({'channel': 'ch', 'presence': [{'action': 1, 'clientId': 'a'}]})
    assert result.presence[0].action is PresenceAction.PRESENT


@pytest.mark.parametrize('module', MODULES)
@pytest.mark.parametrize('binary', [False, True])
@pytest.mark.parametrize('name,value', WIRE_VALUES)
def test_encoding_sends_a_plain_int(module, binary, name, value):
    msg = module.PresenceMessage(action=module.PresenceAction[name], client_id='c', data='d')
    encoded = msg.to_encoded(binary=binary)
    assert type(encoded['action']) is int
    assert encoded['action'] == value
    assert json.loads(json.dumps(encoded))['action'] == value
    assert msgpack.unpackb(msgpack.packb(encoded))['action'] == value


def test_encoding_a_plain_int_action_is_unchanged():
    encoded = PresenceMessage(action=2, client_id='c').to_encoded()
    assert encoded['action'] == 2
    assert type(encoded['action']) is int


def test_encoding_round_trips():
    sent = PresenceMessage(action=PresenceAction.UPDATE, client_id='c', data='d').to_encoded()
    assert PresenceMessage.from_encoded(sent).action is PresenceAction.UPDATE


@pytest.mark.parametrize('name,value', WIRE_VALUES)
def test_action_name_is_the_event_name(name, value):
    assert _action_name(PresenceAction[name]) == name.lower()
    assert _action_name(value) == name.lower()


def test_action_name_of_an_unknown_action():
    assert _action_name(99) == 'unknown(99)'
    assert _action_name(None) == 'unknown(None)'


def subscribed_presence(connection_id='conn-1'):
    channel = SimpleNamespace(
        name='presence-action',
        ably=SimpleNamespace(
            options=SimpleNamespace(_test_options=TestOptions()),
            connection=SimpleNamespace(connection_manager=SimpleNamespace(connection_id=connection_id)),
        ),
    )
    presence = RealtimePresence(channel)
    events = []
    for event_name in ('present', 'enter', 'leave', 'update', 'absent'):
        presence._subscriptions.on(event_name, lambda m, e=event_name: events.append((e, m)))
    return presence, events


def wire(action, client_id, connection_id, index, timestamp):
    return {'action': action, 'clientId': client_id, 'connectionId': connection_id,
            'id': f'{connection_id}:0:{index}', 'timestamp': timestamp}


# RTP2, RTP18, RTP19: members a SYNC delivers, and the LEAVEs it synthesizes for those it
# leaves out, carry PresenceAction members and are emitted under their lowercase names.
def test_realtime_presence_map_and_synthesized_leaves_hold_members():
    presence, events = subscribed_presence()

    first = PresenceMessage.from_encoded_array([wire(1, 'alice', 'c1', 0, 100), wire(1, 'bob', 'c2', 0, 100)])
    presence.set_presence(first, is_sync=True, sync_channel_serial='seq1:')
    assert [(e, m.action) for e, m in events] == [('present', PresenceAction.PRESENT),
                                                  ('present', PresenceAction.PRESENT)]
    assert all(type(m.action) is PresenceAction for m in presence.members.values())

    events.clear()
    second = PresenceMessage.from_encoded_array([wire(1, 'alice', 'c1', 0, 100)])
    presence.set_presence([], is_sync=True, sync_channel_serial='seq2:cursor')
    presence.set_presence(second, is_sync=True, sync_channel_serial='seq2:')
    assert [(e, m.client_id, m.action) for e, m in events] == [('leave', 'bob', PresenceAction.LEAVE)]
    assert type(events[0][1].action) is PresenceAction

    events.clear()
    presence.set_presence(PresenceMessage.from_encoded_array([wire(2, 'carol', 'c3', 0, 200)]), is_sync=False)
    presence.set_presence(PresenceMessage.from_encoded_array([wire(4, 'carol', 'c3', 1, 300)]), is_sync=False)
    presence.set_presence(PresenceMessage.from_encoded_array([wire(3, 'carol', 'c3', 2, 400)]), is_sync=False)
    assert [(e, m.action) for e, m in events] == [('enter', PresenceAction.ENTER),
                                                  ('update', PresenceAction.UPDATE),
                                                  ('leave', PresenceAction.LEAVE)]
