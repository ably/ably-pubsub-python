"""Derived from uts/rest/unit/channels_collection.md in ably/specification.

Spec points: RSN1, RSN2, RSN3a, RSN4a, RSN4b

The collection is held in memory, so no request reaches the mock. A mock is still
installed so that nothing in these tests can touch the network.
"""

import uuid

from ably.rest.channel import Channel, Channels
from test.uts.helpers.client import rest_client
from test.uts.helpers.mock_http import MockHttpClient


def random_id():
    return uuid.uuid4().hex[:8]


def offline_client():
    mock_http = MockHttpClient(
        on_connection_attempt=lambda conn: conn.respond_with_success(),
        on_request=lambda request: request.respond_with(200, []),
    )
    return rest_client(mock_http)


# UTS: rest/unit/RSN1/channels-collection-accessible-0
async def test_rsn1_channels_collection_accessible():
    client = offline_client()

    assert isinstance(client.channels, Channels)
    assert client.channels is not None


# UTS: rest/unit/RSN2/check-channel-exists-0
async def test_rsn2_check_channel_exists():
    channel_name = f'test-RSN2-{random_id()}'
    client = offline_client()

    # NOTE: the spec spells this channels.exists(name); Python spells membership
    # as `in`, which Channels implements via __contains__.
    exists_before = channel_name in client.channels

    client.channels.get(channel_name)

    exists_after = channel_name in client.channels

    other_channel_name = f'test-RSN2-other-{random_id()}'
    exists_other = other_channel_name in client.channels

    assert exists_before is False
    assert exists_after is True
    assert exists_other is False


# UTS: rest/unit/RSN2/iterate-channels-1
async def test_rsn2_iterate_channels():
    channel_name_a = f'test-RSN2-a-{random_id()}'
    channel_name_b = f'test-RSN2-b-{random_id()}'
    channel_name_c = f'test-RSN2-c-{random_id()}'
    client = offline_client()

    client.channels.get(channel_name_a)
    client.channels.get(channel_name_b)
    client.channels.get(channel_name_c)

    channel_names = [channel.name for channel in client.channels]

    assert channel_name_a in channel_names
    assert channel_name_b in channel_names
    assert channel_name_c in channel_names
    assert len(channel_names) == 3


# UTS: rest/unit/RSN3a/get-creates-new-channel-0
async def test_rsn3a_get_creates_new_channel():
    channel_name = f'test-RSN3a-{random_id()}'
    client = offline_client()

    channel = client.channels.get(channel_name)

    assert isinstance(channel, Channel)
    assert channel.name == channel_name
    assert (channel_name in client.channels) is True


# UTS: rest/unit/RSN3a/get-returns-existing-channel-1
async def test_rsn3a_get_returns_existing_channel():
    channel_name = f'test-RSN3a-existing-{random_id()}'
    client = offline_client()

    channel1 = client.channels.get(channel_name)
    channel2 = client.channels.get(channel_name)

    assert channel1 is channel2
    assert channel1.name == channel_name


# UTS: rest/unit/RSN3a/subscript-creates-or-returns-2
async def test_rsn3a_subscript_creates_or_returns():
    channel_name = f'test-RSN3a-subscript-{random_id()}'
    client = offline_client()

    channel1 = client.channels[channel_name]
    channel2 = client.channels.get(channel_name)
    channel3 = client.channels[channel_name]

    assert channel1 is channel2
    assert channel2 is channel3
    assert channel1.name == channel_name


# UTS: rest/unit/RSN4a/release-removes-channel-0
async def test_rsn4a_release_removes_channel():
    channel_name = f'test-RSN4a-{random_id()}'
    client = offline_client()

    client.channels.get(channel_name)
    assert (channel_name in client.channels) is True

    client.channels.release(channel_name)

    assert (channel_name in client.channels) is False


# UTS: rest/unit/RSN4b/release-nonexistent-noop-0
async def test_rsn4b_release_nonexistent_noop():
    channel_name = f'test-RSN4b-{random_id()}'
    client = offline_client()

    client.channels.release(channel_name)

    assert (channel_name in client.channels) is False


# UTS: rest/unit/RSN3a/get-after-release-new-instance-3
async def test_rsn3a_get_after_release_new_instance():
    channel_name = f'test-RSN3a-release-{random_id()}'
    client = offline_client()

    channel1 = client.channels.get(channel_name)

    client.channels.release(channel_name)

    channel2 = client.channels.get(channel_name)

    assert channel1 is not channel2
    assert channel2.name == channel_name
    assert (channel_name in client.channels) is True
