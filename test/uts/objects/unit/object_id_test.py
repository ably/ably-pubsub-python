"""Derived from uts/objects/unit/object_id.md in ably/specification.

Spec points: RTO14, RTO14a1, RTO14b, RTO14b1, RTO14b2, RTO14c

A pure function: `generate_object_id(object_type, initial_value, nonce, timestamp_ms)` is the
specification's `generateObjectId(type:, initialValue:, nonce:, timestamp:)`, producing
`[type]:[hash]@[timestamp]`.
"""

import base64
import hashlib
import re

from ably.pubsub.objects.objectid import generate_object_id

# RFC 4648 s.5's URL-safe alphabet, with no padding
BASE64URL_UNPADDED = re.compile(r'[A-Za-z0-9_-]+')


def _is_base64url(value):
    """Whether `value` is unpadded base64url that decodes: the alphabet, and a length no
    encoding produces (one more than a multiple of four) excluded."""
    if not BASE64URL_UNPADDED.fullmatch(value) or len(value) % 4 == 1:
        return False
    base64.urlsafe_b64decode(value + '=' * (-len(value) % 4))
    return True


def _expected_hash(initial_value, nonce):
    """RTO14b, computed here independently: the unpadded base64url SHA-256 digest of the
    UTF-8 string `initial_value:nonce`."""
    digest = hashlib.sha256(f'{initial_value}:{nonce}'.encode()).digest()
    return base64.urlsafe_b64encode(digest).decode('ascii').rstrip('=')


# UTS: objects/unit/RTO14/objectid-format-counter-0
def test_rto14_objectid_format_counter():
    object_id = generate_object_id('counter', '{"counter":{"count":42}}', 'test-nonce-12345678', 1700000000000)

    assert object_id.startswith('counter:')
    assert '@1700000000000' in object_id
    parts = object_id.split(':')
    # The shape is asserted before indexing, so a malformed id fails on an assertion
    assert len(parts) == 2
    type_part = parts[0]
    rest = parts[1]
    hash_and_ts = rest.split('@')
    assert len(hash_and_ts) == 2
    hash_part = hash_and_ts[0]
    ts_part = hash_and_ts[1]
    assert type_part == 'counter'
    assert ts_part == '1700000000000'
    assert _is_base64url(hash_part)
    assert '+' not in hash_part
    assert '/' not in hash_part
    assert '=' not in hash_part
    # The hash itself, which RTO14b1 and RTO14b2 determine and the specification's
    # assertions leave open: the digest of the initial value and the nonce, joined by ':'
    assert hash_part == _expected_hash('{"counter":{"count":42}}', 'test-nonce-12345678')


# UTS: objects/unit/RTO14/objectid-format-map-0
def test_rto14_objectid_format_map():
    object_id = generate_object_id(
        'map', '{"map":{"semantics":"LWW","entries":{}}}', 'test-nonce-12345678', 1700000000000)

    assert object_id.startswith('map:')
    assert '@1700000000000' in object_id


# UTS: objects/unit/RTO14/deterministic-0
def test_rto14_deterministic():
    id1 = generate_object_id('counter', '{"counter":{"count":0}}', 'same-nonce-1234567', 1700000000000)
    id2 = generate_object_id('counter', '{"counter":{"count":0}}', 'same-nonce-1234567', 1700000000000)

    assert id1 == id2


# UTS: objects/unit/RTO14/different-nonce-0
def test_rto14_different_nonce():
    id1 = generate_object_id('counter', '{"counter":{"count":0}}', 'nonce-aaaaaaaaaaaaa', 1700000000000)
    id2 = generate_object_id('counter', '{"counter":{"count":0}}', 'nonce-bbbbbbbbbbbbb', 1700000000000)

    assert id1 != id2


# UTS: objects/unit/RTO14b/base64url-encoding-0
def test_rto14b_base64url_encoding():
    object_id = generate_object_id('counter', '{"counter":{"count":0}}', 'test-nonce-12345678', 1700000000000)
    parts = object_id.split(':')
    # The shape is asserted before indexing, so a malformed id fails on an assertion
    assert len(parts) == 2
    hash_and_ts = parts[1].split('@')
    assert len(hash_and_ts) == 2
    hash_part = hash_and_ts[0]

    assert '+' not in hash_part
    assert '/' not in hash_part
    assert not hash_part.endswith('=')
