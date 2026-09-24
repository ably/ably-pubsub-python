"""Derived from uts/rest/integration/publish.md in ably/specification.

Spec points: RSL1d, RSL1k5, RSL1l1, RSL1m4, RSL1n
"""

import pytest

from ably.types.message import Message
from ably.util.exceptions import AblyException
from test.uts.helpers.client import sandbox_rest_client, wall_clock_poll_until
from test.uts.helpers.sandbox import random_id


# UTS: rest/integration/RSL1d/publish-failure-error-0
async def test_rsl1d_publish_failure_error(sandbox, use_binary_protocol):
    restricted_key = sandbox.key(2)

    channel_name = 'forbidden-channel-' + random_id()
    # keys[2] names channel0 to channel6 one by one, so a generated name is covered by
    # none of them. Read off the key rather than assumed, so that a change to the app
    # setup shows up here rather than turning the test into one that proves nothing.
    assert channel_name not in restricted_key.capability

    restricted_client = sandbox_rest_client(
        restricted_key.key_str, use_binary_protocol=use_binary_protocol)
    restricted_channel = restricted_client.channels.get(channel_name)

    with pytest.raises(AblyException) as excinfo:
        await restricted_channel.publish(name='event', data='data')

    assert excinfo.value.code == 40160
    assert excinfo.value.status_code == 401


# UTS: rest/integration/RSL1n/publish-result-serials-0
async def test_rsl1n_publish_result_serials(sandbox, use_binary_protocol):
    client = sandbox_rest_client(sandbox.key_str, use_binary_protocol=use_binary_protocol)
    channel_name = 'test-serials-' + random_id()
    channel = client.channels.get(channel_name)

    result1 = await channel.publish(name='event1', data='data1')

    assert isinstance(result1.serials, list)
    assert len(result1.serials) == 1
    assert isinstance(result1.serials[0], str)
    assert len(result1.serials[0]) > 0

    result2 = await channel.publish(messages=[
        Message(name='event2', data='data2'),
        Message(name='event3', data='data3'),
        Message(name='event4', data='data4'),
    ])

    assert len(result2.serials) == 3
    assert all(isinstance(serial, str) and len(serial) > 0 for serial in result2.serials)
    assert len(set(result2.serials)) == 3


# UTS: rest/integration/RSL1k5/idempotent-client-ids-0
async def test_rsl1k5_idempotent_client_ids(sandbox, use_binary_protocol):
    client = sandbox_rest_client(sandbox.key_str, use_binary_protocol=use_binary_protocol)
    channel_name = 'idempotent-explicit-' + random_id()
    channel = client.channels.get(channel_name)

    fixed_id = 'client-supplied-id-' + random_id()

    # publish(message=...) raises TypeError, so the Message goes positionally. The id is
    # the client's own, so the library leaves it alone: it only generates ids when every
    # message in the batch lacks one (RSL1k1).
    for i in (1, 2, 3):
        await channel.publish(Message(id=fixed_id, name='event', data=f'data-{i}'))

    async def any_message_in_history():
        result = await channel.history()
        return result if len(result.items) > 0 else None

    history = await wall_clock_poll_until(
        any_message_in_history, description='the published message to reach history')

    assert len(history.items) == 1
    assert history.items[0].id == fixed_id
    # The data should be from the first publish (subsequent ones are no-ops)
    assert history.items[0].data == 'data-1'


# UTS: rest/integration/RSL1l1/publish-params-force-nack-0
async def test_rsl1l1_publish_params_force_nack(sandbox, use_binary_protocol):
    client = sandbox_rest_client(sandbox.key_str, use_binary_protocol=use_binary_protocol)
    channel_name = 'force-nack-test-' + random_id()
    channel = client.channels.get(channel_name)

    # publish(name=, data=, params=) raises; params reaches the query string only through
    # the Message form, where it is the second positional argument.
    with pytest.raises(AblyException) as excinfo:
        await channel.publish(Message(name='event', data='data'), {'_forceNack': 'true'})

    assert excinfo.value.code == 40099


# UTS: rest/integration/RSL1m4/clientid-mismatch-rejected-0
async def test_rsl1m4_clientid_mismatch_rejected(sandbox, use_binary_protocol):
    key_client = sandbox_rest_client(sandbox.key_str, use_binary_protocol=use_binary_protocol)

    # request_token takes its token params as a positional dict; every keyword on it is an
    # auth option.
    token_details = await key_client.auth.request_token({'client_id': 'authenticated-client-id'})

    # The spec passes the bare token string, not the TokenDetails, so the client does not
    # know the clientId the token carries and cannot rule the publish out locally. The
    # message goes to the server, which is what this test is here to exercise. Passing
    # `token_details=` instead would have the library reject it in
    # `Channel.__publish_request_body` with the same 400/40012 before any request left.
    token_client = sandbox_rest_client(
        token=token_details.token, use_binary_protocol=use_binary_protocol)

    channel_name = 'clientid-mismatch-' + random_id()
    channel = token_client.channels.get(channel_name)

    with pytest.raises(AblyException) as excinfo:
        await channel.publish(Message(
            name='event',
            data='data',
            client_id='different-client-id',  # Doesn't match authenticated clientId
        ))

    assert excinfo.value.code == 40012
    assert excinfo.value.status_code == 400
