"""Derived from uts/rest/integration/batch_presence.md in ably/specification.

Spec points: RSC24, BGR2, BGF2

DEVIATION: ably-python has no batch API. `AblyRest` exposes no `batch_presence`, and
the package defines neither `BatchResult` nor `BatchPresenceSuccessResult` /
`BatchPresenceFailureResult`; the word "batch" appears nowhere under `ably/`. Every
test here therefore departs from the specification and is gated behind
RUN_DEVIATIONS, against the same spelling
[test/uts/rest/unit/batch_presence_test.py](../unit/batch_presence_test.py) gates on —
`client.batch_presence([...])` giving a result with `success_count`, `failure_count`
and `results` — so that dropping the marker is the only change either tier needs when
RSC24 lands.

The setup halves are real, and the responses they assert against were confirmed by
hand through `client.request('GET', '/presence', params={'channels': ...})` against
the sandbox: the server does return the `successCount` / `failureCount` / `results`
envelope the specification describes, with `code` 40160 and `statusCode` 401 for a
channel the key has no capability for. Two details of that confirmation are recorded
beside the assertions they bear on — the `presence` key the server omits for an empty
channel, and the presence members a closed connection takes with it.

See [deviations-batch-push-channels-integration.md](../../deviations-batch-push-channels-integration.md).
"""

from ably.realtime.connection import ConnectionState
from test.uts.helpers.client import (
    await_connection_state,
    sandbox_realtime_client,
    sandbox_rest_client,
    wall_clock_poll_until,
)
from test.uts.helpers.deviations import deviation
from test.uts.helpers.sandbox import random_id


def result_for(result, channel_name):
    """The specifications' `result.results.find(r => r.channel == channel_name)`."""
    for entry in result.results:
        if entry.channel == channel_name:
            return entry
    raise AssertionError(f'No batch result for channel {channel_name!r}')


def is_success_result(entry):
    """The specifications' `entry IS BatchPresenceSuccessResult`.

    Neither result class exists to name, so a success is told apart from a failure by
    which attribute it carries, as the unit tier does.
    """
    return getattr(entry, 'presence', None) is not None


def is_failure_result(entry):
    """The specifications' `entry IS BatchPresenceFailureResult`."""
    return getattr(entry, 'error', None) is not None


def member_for(entry, client_id):
    """The specifications' `presence.find(m => m.clientId == client_id)`."""
    for member in entry.presence:
        if member.client_id == client_id:
            return member
    raise AssertionError(f'No presence member with clientId {client_id!r}')


async def entering_client(key, use_binary_protocol):
    """A CONNECTED realtime client that may enter presence for any clientId.

    The specifications build this with the full-access key alone and call
    `enterClient` straight away. ably-python needs `client_id='*'` on top: a basic-auth
    connection is told `clientId: "*"` by the server, and `Auth._configure_client_id`
    answers a wildcard from the server by marking the client id validated while leaving
    it `None` (`ably/rest/auth.py:335`), after which `can_assume_client_id` refuses every
    id and `enter_client` raises 40012. The repository's own presence suite carries the
    same `client_id='*'` for the same reason
    (`test/ably/realtime/realtimepresence_test.py:396`).

    The connection is awaited to CONNECTED before any enter, since a presence enter on a
    connection that is still CONNECTING is queued rather than sent.
    """
    client = sandbox_realtime_client(key, client_id='*', use_binary_protocol=use_binary_protocol)
    await await_connection_state(client, ConnectionState.CONNECTED)
    return client


async def enter_members(realtime, channel_name, members):
    """Attaches `channel_name` and enters each `(client_id, data)` pair on it."""
    channel = realtime.channels.get(channel_name)
    await channel.attach()
    for client_id, data in members:
        await channel.presence.enter_client(client_id, data)
    return channel


@deviation
# UTS: rest/integration/RSC24/batch-presence-multiple-channels-0
async def test_rsc24_batch_presence_multiple_channels(sandbox, use_binary_protocol):
    channel_a_name = 'batch-presence-a-' + random_id()
    channel_b_name = 'batch-presence-b-' + random_id()

    realtime = await entering_client(sandbox.key(0).key_str, use_binary_protocol)
    await enter_members(realtime, channel_a_name, [('user-1', 'data-a1'), ('user-2', 'data-a2')])
    await enter_members(realtime, channel_b_name, [('user-3', 'data-b1')])

    # The realtime client stays open: the members would leave with the connection, and
    # closing it is the autouse fixture's job in any case.
    rest = sandbox_rest_client(sandbox.key(0).key_str, use_binary_protocol=use_binary_protocol)

    result = await rest.batch_presence([channel_a_name, channel_b_name])

    assert result.success_count == 2
    assert result.failure_count == 0
    assert len(result.results) == 2

    result_a = result_for(result, channel_a_name)
    result_b = result_for(result, channel_b_name)

    assert is_success_result(result_a)
    assert len(result_a.presence) == 2
    client_ids_a = [member.client_id for member in result_a.presence]
    assert 'user-1' in client_ids_a
    assert 'user-2' in client_ids_a

    assert member_for(result_a, 'user-1').data == 'data-a1'

    assert is_success_result(result_b)
    assert len(result_b.presence) == 1
    assert result_b.presence[0].client_id == 'user-3'
    assert result_b.presence[0].data == 'data-b1'


@deviation
# UTS: rest/integration/RSC24/restricted-key-channel-failure-1
async def test_rsc24_restricted_key_channel_failure(sandbox, use_binary_protocol):
    # The specification hard-codes "channel6" as the channel `keys[2]` is allowed. The
    # capability comes back with the provisioned app, so the channel is read off it
    # rather than assumed; it is the only one of the seven given every operation, and
    # presence is the operation this test needs. A wildcard pattern would not do: the
    # specification records that the batch presence endpoint does not honour one.
    capability = sandbox.key(2).capability
    allowed = sorted(name for name, operations in capability.items() if '*' in operations)
    assert allowed, f'keys[2] names no fully-permitted channel: {capability!r}'
    allowed_channel = allowed[0]
    denied_channel = 'denied-batch-' + random_id()

    realtime = await entering_client(sandbox.key(0).key_str, use_binary_protocol)
    await enter_members(realtime, allowed_channel, [('member-1', 'hello')])
    await enter_members(realtime, denied_channel, [('member-2', 'world')])

    # SPEC FAULT: the specification closes the realtime client here, then asserts that
    # the allowed channel still holds `member-1`. Confirmed against the sandbox: closing
    # the connection takes its presence members with it, and the allowed channel comes
    # back with no `presence` at all. The connection is left open, as this file's other
    # two tests say to do in so many words.
    restricted_rest = sandbox_rest_client(
        sandbox.key(2).key_str, use_binary_protocol=use_binary_protocol)

    # `allowed_channel` is a fixed name, so the json and msgpack runs enter `member-1`
    # on the same channel one after the other. Polling lets the previous run's member
    # finish leaving rather than counting it.
    async def one_member_on_the_allowed_channel():
        result = await restricted_rest.batch_presence([allowed_channel, denied_channel])
        success = result_for(result, allowed_channel)
        return result if is_success_result(success) and len(success.presence) == 1 else None

    result = await wall_clock_poll_until(
        one_member_on_the_allowed_channel,
        description=f'one presence member on {allowed_channel}')

    assert result.success_count == 1
    assert result.failure_count == 1
    assert len(result.results) == 2

    success = result_for(result, allowed_channel)
    failure = result_for(result, denied_channel)

    assert is_success_result(success)
    assert len(success.presence) == 1
    assert success.presence[0].client_id == 'member-1'

    assert is_failure_result(failure)
    assert failure.error.code == 40160
    assert failure.error.status_code == 401


@deviation
# UTS: rest/integration/RSC24/empty-channel-presence-2
async def test_rsc24_empty_channel_presence(sandbox, use_binary_protocol):
    empty_channel = 'batch-empty-' + random_id()
    populated_channel = 'batch-populated-' + random_id()

    realtime = await entering_client(sandbox.key(0).key_str, use_binary_protocol)
    await enter_members(realtime, populated_channel, [('someone', 'here')])

    rest = sandbox_rest_client(sandbox.key(0).key_str, use_binary_protocol=use_binary_protocol)

    result = await rest.batch_presence([empty_channel, populated_channel])

    assert result.success_count == 2
    assert result.failure_count == 0
    assert len(result.results) == 2

    empty_result = result_for(result, empty_channel)
    populated_result = result_for(result, populated_channel)

    # The server counts the empty channel a success and leaves `presence` out of its
    # result altogether rather than sending `[]`, so an implementation of BGR2 has to
    # default the field for the specification's assertion to hold.
    assert is_success_result(empty_result)
    assert len(empty_result.presence) == 0

    assert is_success_result(populated_result)
    assert len(populated_result.presence) == 1
    assert populated_result.presence[0].client_id == 'someone'
