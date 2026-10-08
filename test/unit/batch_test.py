"""Unit tests for the batch types and the inputs the batch methods accept.

Tests cover:
- BSP2: a dict standing in for a BatchPublishSpec
- RSC22, RSC24: inputs refused before any request is made
"""

import pytest

from ably.pubsub.server import create_http_client
from ably.pubsub.types.batch import BatchPublishSpec
from ably.pubsub.types.message import Message


def test_batch_publish_spec_factory_accepts_spec():
    spec = BatchPublishSpec(channels=['a'], messages=[Message('event', 'data')])
    assert BatchPublishSpec.factory(spec) is spec


def test_batch_publish_spec_factory_accepts_dict():
    messages = [Message('event', 'data')]
    spec = BatchPublishSpec.factory({'channels': ['a', 'b'], 'messages': messages})
    assert spec.channels == ['a', 'b']
    assert spec.messages is messages


def test_batch_publish_spec_factory_rejects_other_types():
    with pytest.raises(TypeError):
        BatchPublishSpec.factory('a')


async def test_batch_presence_rejects_a_single_channel_name():
    client = create_http_client(key='fake.key:secret')
    try:
        with pytest.raises(TypeError):
            await client.batch_presence('channel')
    finally:
        await client.close()
