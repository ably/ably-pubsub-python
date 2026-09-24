"""Derived from uts/rest/unit/encoding/msgpack_interop.md in ably/specification.

Spec points: RSL6a3
"""

import base64
import json
import os

import msgpack
import pytest

from ably.types.message import Message

FIXTURES_PATH = os.path.join(
    os.path.dirname(__file__), '..', '..', '..', '..', '..',
    'submodules', 'test-resources', 'msgpack_test_fixtures.json')

# The pinned ably-common commit predates msgpack_test_fixtures.json, so the fixtures
# are only present once the submodule is moved forward.
requires_fixtures = pytest.mark.skipif(
    not os.path.exists(FIXTURES_PATH),
    reason='ably-common/test-resources/msgpack_test_fixtures.json is not in the pinned submodule')


def load_fixtures():
    with open(FIXTURES_PATH) as fixture_file:
        return json.load(fixture_file)


def wire_message_of(fixture):
    """The single wire message inside the fixture's msgpack ProtocolMessage."""
    msgpack_bytes = base64.b64decode(fixture['msgpack'])
    protocol_message = msgpack.unpackb(msgpack_bytes)
    return protocol_message['messages'][0]


def expected_data_of(fixture):
    if fixture['type'] == 'string':
        if fixture['numRepeat'] > 0:
            return fixture['data'] * fixture['numRepeat']
        return fixture['data']
    if fixture['type'] == 'binary':
        raw_string = fixture['data'] * fixture['numRepeat']
        return raw_string.encode('utf-8')
    return fixture['data']


# NOTE: the spec gives no Test ID for either section of msgpack_interop.md, so the ids
# below are derived from the spec point and the section titles.
# UTS: rest/unit/RSL6a3/decode-interop-fixtures-0
@requires_fixtures
def test_rsl6a3_decode_interop_fixtures():
    fixtures = load_fixtures()

    for fixture in fixtures:
        wire_message = wire_message_of(fixture)
        expected = expected_data_of(fixture)

        message = Message.from_encoded(wire_message)

        assert message.data == expected, fixture['name']
        # NOTE: the spec asserts the encoding IS null. ably-python spells "no encoding
        # remains" as the empty string.
        assert message.encoding == '', fixture['name']

        if fixture['type'] == 'string':
            assert isinstance(message.data, str), fixture['name']
        elif fixture['type'] == 'binary':
            assert wire_message['encoding'] == 'base64', fixture['name']
            assert isinstance(message.data, (bytes, bytearray)), fixture['name']
        else:
            assert wire_message['encoding'] == 'json', fixture['name']
            assert isinstance(message.data, (list, dict)), fixture['name']


# UTS: rest/unit/RSL6a3/round-trip-interop-fixtures-1
@requires_fixtures
def test_rsl6a3_round_trip_interop_fixtures():
    fixtures = load_fixtures()

    for fixture in fixtures:
        wire_message = wire_message_of(fixture)
        message = Message.from_encoded(wire_message)

        re_encoded = message.as_dict(binary=True)
        # use_bin_type=True is what Channel.publish_messages serialises with, and is what
        # keeps the msgpack bin and str types apart across the round trip
        re_bytes = msgpack.packb({'messages': [re_encoded], 'msgSerial': 0}, use_bin_type=True)

        re_pm = msgpack.unpackb(re_bytes)
        re_message = Message.from_encoded(re_pm['messages'][0])

        assert re_message.data == message.data, fixture['name']
        assert re_message.encoding == '', fixture['name']
