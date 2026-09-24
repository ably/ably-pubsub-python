"""Derived from uts/rest/integration/presence.md in ably/specification.

Spec points: RSP1, RSP3, RSP3a, RSP4, RSP4b, RSP5
"""

import pytest

from ably.http.paginatedresult import PaginatedResult
from ably.realtime.connection import ConnectionState
from ably.types.presence import Presence, PresenceAction, PresenceMessage
from ably.util.exceptions import AblyException
from test.uts.helpers.client import (
    await_connection_state,
    sandbox_realtime_client,
    sandbox_rest_client,
    wall_clock_poll_until,
)
from test.uts.helpers.deviations import deviation
from test.uts.helpers.sandbox import PRESENCE_FIXTURES_CHANNEL, fixture_cipher_params, random_id

# The clientIds the app setup pre-populates on `persisted:presence_fixtures`.
FIXTURE_CLIENT_IDS = (
    'client_bool', 'client_int', 'client_string', 'client_json', 'client_decoded', 'client_encoded')


def member_for(page, client_id):
    """The one fixture member with `client_id`, or None.

    The specifications reach for this with `presence.get(clientId: ...)`, which
    `Presence.get` does not offer; see *Adaptations forced by the absent `clientId`
    filter on `RestPresence#get`* under *Adapted Tests* in
    [deviations.md](../../deviations.md).
    """
    return next((item for item in page.items if item.client_id == client_id), None)


async def connected_realtime(key, client_id, use_binary_protocol):
    """A realtime client already CONNECTED, ready to generate presence events.

    `presence.enter` resolves on the server's ACK, but a call made before the
    connection is up is queued rather than sent, so the wait has to happen
    first.
    """
    client = sandbox_realtime_client(
        key, client_id=client_id, use_binary_protocol=use_binary_protocol)
    await await_connection_state(client, ConnectionState.CONNECTED)
    return client


def presence_history_of_at_least(channel, count):
    """A poll condition giving the presence history page once it holds `count` events."""
    async def condition():
        page = await channel.presence.history()
        return page if len(page.items) >= count else None

    return condition


# UTS: rest/integration/RSP1/access-presence-from-channel-0
async def test_rsp1_access_presence_from_channel(sandbox, use_binary_protocol):
    client = sandbox_rest_client(sandbox.key_str, use_binary_protocol=use_binary_protocol)

    channel = client.channels.get(PRESENCE_FIXTURES_CHANNEL)
    presence = channel.presence

    assert presence is not None
    # NOTE: the spec asserts `presence IS RestPresence`. The class behind
    # `channel.presence` in ably-python is `ably.types.presence.Presence`.
    assert isinstance(presence, Presence)


# UTS: rest/integration/RSP3/get-presence-members-0
async def test_rsp3_get_presence_members(sandbox, use_binary_protocol):
    client = sandbox_rest_client(sandbox.key_str, use_binary_protocol=use_binary_protocol)

    channel = client.channels.get(PRESENCE_FIXTURES_CHANNEL)
    result = await channel.presence.get()

    assert isinstance(result, PaginatedResult)
    assert len(result.items) >= 5

    client_ids = [message.client_id for message in result.items]
    assert 'client_bool' in client_ids
    assert 'client_string' in client_ids
    assert 'client_json' in client_ids


# UTS: rest/integration/RSP3/presence-message-fields-1
async def test_rsp3_presence_message_fields(sandbox, use_binary_protocol):
    client = sandbox_rest_client(sandbox.key_str, use_binary_protocol=use_binary_protocol)

    channel = client.channels.get(PRESENCE_FIXTURES_CHANNEL)
    result = await channel.presence.get()

    member = member_for(result, 'client_string')

    assert member is not None
    assert isinstance(member, PresenceMessage)
    assert member.action == PresenceAction.PRESENT
    assert member.client_id == 'client_string'
    assert member.data == 'This is a string clientData payload'
    assert member.connection_id is not None


# UTS: rest/integration/RSP3a1/get-with-limit-0
async def test_rsp3a1_get_with_limit(sandbox, use_binary_protocol):
    client = sandbox_rest_client(sandbox.key_str, use_binary_protocol=use_binary_protocol)

    channel = client.channels.get(PRESENCE_FIXTURES_CHANNEL)

    result = await channel.presence.get(limit=2)

    assert len(result.items) <= 2
    if result.has_next():
        assert len(result.items) == 2


@deviation
# UTS: rest/integration/RSP3a2/get-with-clientid-filter-0
async def test_rsp3a2_get_with_clientid_filter(sandbox, use_binary_protocol):
    client = sandbox_rest_client(sandbox.key_str, use_binary_protocol=use_binary_protocol)

    channel = client.channels.get(PRESENCE_FIXTURES_CHANNEL)
    result = await channel.presence.get(client_id='client_json')

    assert len(result.items) == 1
    assert result.items[0].client_id == 'client_json'
    # The fixture has no encoding field, so data is returned as a raw string.
    assert isinstance(result.items[0].data, str)
    assert result.items[0].data == '{ "test": "This is a JSONObject clientData payload"}'


# UTS: rest/integration/RSP3/get-empty-channel-2
async def test_rsp3_get_empty_channel(sandbox, use_binary_protocol):
    client = sandbox_rest_client(sandbox.key_str, use_binary_protocol=use_binary_protocol)

    channel_name = f'presence-empty-{random_id()}'
    channel = client.channels.get(channel_name)

    result = await channel.presence.get()

    assert isinstance(result.items, list)
    assert len(result.items) == 0
    assert result.has_next() is False


# UTS: rest/integration/RSP4/history-returns-events-0
async def test_rsp4_history_returns_events(sandbox, use_binary_protocol):
    client = sandbox_rest_client(sandbox.key_str, use_binary_protocol=use_binary_protocol)

    channel_name = f'presence-history-{random_id()}'

    realtime = await connected_realtime(sandbox.key_str, 'test-client', use_binary_protocol)

    realtime_channel = realtime.channels.get(channel_name)
    await realtime_channel.presence.enter('entered')
    await realtime_channel.presence.update('updated')
    await realtime_channel.presence.leave('left')
    # NOTE: the spec closes the realtime client here. The suite's autouse
    # teardown closes every client it built, after the assertions have run.

    rest_channel = client.channels.get(channel_name)

    history = await wall_clock_poll_until(
        presence_history_of_at_least(rest_channel, 3),
        description='the three presence events to reach history')

    assert len(history.items) >= 3

    actions = [message.action for message in history.items]
    assert PresenceAction.ENTER in actions
    assert PresenceAction.UPDATE in actions
    assert PresenceAction.LEAVE in actions


# UTS: rest/integration/RSP4b1/history-time-range-0
async def test_rsp4b1_history_time_range(sandbox, use_binary_protocol):
    client = sandbox_rest_client(sandbox.key_str, use_binary_protocol=use_binary_protocol)

    channel_name = f'presence-history-time-{random_id()}'

    # NOTE: the spec reads `now_millis()` from the test's own clock. The bounds
    # are read from the server instead, so that clock skew between the runner
    # and the sandbox cannot put the events outside the window being asserted.
    time_before = await client.time()

    realtime = await connected_realtime(sandbox.key_str, 'time-test-client', use_binary_protocol)

    realtime_channel = realtime.channels.get(channel_name)
    await realtime_channel.presence.enter('test')
    await realtime_channel.presence.leave()

    time_after = await client.time()

    rest_channel = client.channels.get(channel_name)
    await wall_clock_poll_until(
        presence_history_of_at_least(rest_channel, 2),
        description='the enter and leave to reach history')

    history = await rest_channel.presence.history(start=time_before, end=time_after)

    assert len(history.items) >= 2


# UTS: rest/integration/RSP4b2/history-direction-forwards-0
async def test_rsp4b2_history_direction_forwards(sandbox, use_binary_protocol):
    client = sandbox_rest_client(sandbox.key_str, use_binary_protocol=use_binary_protocol)

    channel_name = f'presence-direction-{random_id()}'

    realtime = await connected_realtime(sandbox.key_str, 'direction-client', use_binary_protocol)

    realtime_channel = realtime.channels.get(channel_name)
    await realtime_channel.presence.enter('first')
    await realtime_channel.presence.update('second')
    await realtime_channel.presence.update('third')

    rest_channel = client.channels.get(channel_name)
    await wall_clock_poll_until(
        presence_history_of_at_least(rest_channel, 3),
        description='the three ordered presence events to reach history')

    history_forwards = await rest_channel.presence.history(direction='forwards')

    assert len(history_forwards.items) >= 3
    assert history_forwards.items[0].data == 'first'

    history_backwards = await rest_channel.presence.history(direction='backwards')

    assert history_backwards.items[0].data == 'third'


# UTS: rest/integration/RSP4b3/history-limit-pagination-0
async def test_rsp4b3_history_limit_pagination(sandbox, use_binary_protocol):
    client = sandbox_rest_client(sandbox.key_str, use_binary_protocol=use_binary_protocol)

    channel_name = f'presence-limit-{random_id()}'

    realtime = await connected_realtime(sandbox.key_str, 'limit-client', use_binary_protocol)

    realtime_channel = realtime.channels.get(channel_name)
    for index in range(1, 6):
        await realtime_channel.presence.update(f'update-{index}')

    rest_channel = client.channels.get(channel_name)
    await wall_clock_poll_until(
        presence_history_of_at_least(rest_channel, 5),
        description='the five presence updates to reach history')

    page1 = await rest_channel.presence.history(limit=2)

    assert len(page1.items) == 2
    assert page1.has_next() is True

    page2 = await page1.next()

    assert page2 is not None
    assert len(page2.items) >= 1


# UTS: rest/integration/RSP5/decode-string-data-0
async def test_rsp5_decode_string_data(sandbox, use_binary_protocol):
    client = sandbox_rest_client(sandbox.key_str, use_binary_protocol=use_binary_protocol)

    channel = client.channels.get(PRESENCE_FIXTURES_CHANNEL)
    # NOTE: the spec calls `presence.get(clientId: "client_string")` and asserts
    # `items.length == 1`. `Presence.get` takes no clientId filter, so the whole
    # member set is fetched and filtered here instead.
    result = await channel.presence.get()
    member = member_for(result, 'client_string')

    assert member is not None
    assert isinstance(member.data, str)
    assert member.data == 'This is a string clientData payload'


# UTS: rest/integration/RSP5/decode-json-data-1
async def test_rsp5_decode_json_data(sandbox, use_binary_protocol):
    client = sandbox_rest_client(sandbox.key_str, use_binary_protocol=use_binary_protocol)

    channel = client.channels.get(PRESENCE_FIXTURES_CHANNEL)
    # NOTE: the spec calls `presence.get(clientId: "client_decoded")` and asserts
    # `items.length == 1`; filtered in Python for want of the clientId param.
    result = await channel.presence.get()
    member = member_for(result, 'client_decoded')

    assert member is not None
    assert isinstance(member.data, dict)
    assert member.data['example']['json'] == 'Object'


# UTS: rest/integration/RSP5/decode-encrypted-data-2
async def test_rsp5_decode_encrypted_data(sandbox, use_binary_protocol):
    client = sandbox_rest_client(sandbox.key_str, use_binary_protocol=use_binary_protocol)

    # `Presence` snapshots the channel's cipher when the channel is built, so
    # the cipher goes in on the first `channels.get` for this client.
    channel = client.channels.get(PRESENCE_FIXTURES_CHANNEL, cipher=fixture_cipher_params())

    # NOTE: the spec calls `presence.get(clientId: "client_encoded")` and asserts
    # `items.length == 1`; filtered in Python for want of the clientId param.
    result = await channel.presence.get()
    member = member_for(result, 'client_encoded')

    assert member is not None
    assert member.data is not None
    # The fixture encrypts the same payload `client_decoded` carries in the clear.
    assert member.data == {'example': {'json': 'Object'}}


# UTS: rest/integration/RSP5/decode-history-messages-3
async def test_rsp5_decode_history_messages(sandbox, use_binary_protocol):
    client = sandbox_rest_client(sandbox.key_str, use_binary_protocol=use_binary_protocol)

    channel_name = f'presence-decode-history-{random_id()}'

    realtime = await connected_realtime(sandbox.key_str, 'decode-client', use_binary_protocol)

    json_data = {'key': 'value', 'number': 123}
    realtime_channel = realtime.channels.get(channel_name)
    await realtime_channel.presence.enter(json_data)

    rest_channel = client.channels.get(channel_name)
    history = await wall_clock_poll_until(
        presence_history_of_at_least(rest_channel, 1),
        description='the entered presence member to reach history')

    assert isinstance(history.items[0].data, dict)
    assert history.items[0].data['key'] == 'value'
    assert history.items[0].data['number'] == 123


# UTS: rest/integration/RSP3/full-pagination-3
async def test_rsp3_full_pagination(sandbox, use_binary_protocol):
    client = sandbox_rest_client(sandbox.key_str, use_binary_protocol=use_binary_protocol)

    channel = client.channels.get(PRESENCE_FIXTURES_CHANNEL)

    page1 = await channel.presence.get(limit=2)

    all_members = list(page1.items)

    current_page = page1
    while current_page.has_next():
        current_page = await current_page.next()
        all_members.extend(current_page.items)

    assert len(all_members) >= 5

    client_ids = [member.client_id for member in all_members]
    assert len(set(client_ids)) == len(client_ids)
    assert set(client_ids) == set(FIXTURE_CLIENT_IDS)


# UTS: rest/integration/RSP3/invalid-credentials-rejected-4
async def test_rsp3_invalid_credentials_rejected(sandbox, use_binary_protocol):
    client = sandbox_rest_client('invalid.key:secret', use_binary_protocol=use_binary_protocol)

    with pytest.raises(AblyException) as excinfo:
        await client.channels.get('test').presence.get()

    assert excinfo.value.status_code == 401
    assert 40100 <= excinfo.value.code < 40200


# UTS: rest/integration/RSP3/subscribe-capability-sufficient-5
async def test_rsp3_subscribe_capability_sufficient(sandbox, use_binary_protocol):
    restricted_key = sandbox.key(3).key_str

    client = sandbox_rest_client(restricted_key, use_binary_protocol=use_binary_protocol)

    # Subscribe capability is sufficient for presence.get.
    result = await client.channels.get(PRESENCE_FIXTURES_CHANNEL).presence.get()
    assert result is not None
    assert len(result.items) >= 5
