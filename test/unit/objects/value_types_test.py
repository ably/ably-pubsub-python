"""The `LiveMap` and `LiveCounter` blueprints a write evaluates: what `create` captures, and when
their contents are validated.

Spec points: RTLMV3d (a blueprint is immutable), RTLM20e1 and RTLMV4c (value validation), RTO16
(the server time an object id is generated from).
"""

import pytest

from ably.pubsub.objects.valuetypes import LiveCounter, LiveMap, evaluate
from ably.pubsub.util.exceptions import AblyException
from test.uts.objects.helpers.standard_test_pool import setup_synced_channel, time_mock_http

SERVER_TIME_MS = 1_700_000_123_000


def test_rtlmv3d_a_blueprint_does_not_change_with_the_values_it_was_created_from():
    """RTLMV3d: changing a JSON value or a `bytearray` after passing it to `LiveMap.create` does
    not change the blueprint, at any depth."""
    meta = {'tags': ['a']}
    raw = bytearray(b'\x01')
    blueprint = LiveMap.create({'meta': meta, 'raw': raw})

    meta['tags'].append('b')
    meta['owner'] = 'Bob'
    raw.append(2)

    map_create = evaluate(blueprint, SERVER_TIME_MS)[-1].operation.map_create_with_object_id.derived_from
    assert map_create.entries['meta'].data.json == {'tags': ['a']}
    assert map_create.entries['raw'].data.bytes == b'\x01'


async def test_rtlm20e1_an_invalid_blueprint_is_rejected_before_the_server_time_is_fetched():
    """RTLM20e1, RTLMV4c, RTO16: `set` validates a blueprint's contents before it asks the server
    for the time its object ids are generated from, so an invalid one costs no request."""
    mock_http = time_mock_http()
    client, channel, root, mock_ws = await setup_synced_channel('test', mock_http=mock_http)

    with pytest.raises(AblyException) as excinfo:
        await root.set('team', LiveMap.create({'lead': 'Carol', 'points': LiveCounter.create('ten')}))

    assert excinfo.value.code == 40003
    assert [request for request in mock_http.captured_requests if request.path == '/time'] == []
