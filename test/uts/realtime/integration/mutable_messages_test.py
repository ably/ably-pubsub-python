"""Derived from uts/realtime/integration/mutable_messages.md in ably/specification.

Spec points: RTL28, RTL31, RTL32, RTAN1, RTAN2, RTAN4

The realtime counterpart of `rest/integration/mutable_messages_test.py`: the mutations
travel as MESSAGE and ANNOTATION ProtocolMessages over the websocket rather than as HTTP
requests, and a second connection watches them arrive.

Every channel name carries the `mutable:` prefix. `test-app-setup.json` configures that
namespace with `mutableMessages: true`, and the mutation and annotation operations are
refused on a channel outside it.

`RealtimeChannel.publish()` takes its name and data positionally — the keyword form the
REST channel accepts raises `ValueError` here — and both `channel.subscribe()` and
`annotations.subscribe()` are coroutines, because each carries out an implicit attach.
`get_message` and `get_message_versions` on a realtime channel delegate to the REST
implementation, so they read the message store over HTTP and see it only once it is
consistent; the two polls below are the specification's `poll_until_success` around them.
"""

from ably.http.paginatedresult import PaginatedResult
from ably.realtime.connection import ConnectionState
from ably.types.annotation import Annotation, AnnotationAction
from ably.types.channelmode import ChannelMode
from ably.types.channeloptions import ChannelOptions
from ably.types.channelstate import ChannelState
from ably.types.message import Message, MessageAction
from ably.types.operations import MessageOperation, UpdateDeleteResult
from ably.util.exceptions import AblyException
from test.uts.helpers.client import (
    await_channel_state,
    await_connection_state,
    sandbox_realtime_client,
    wall_clock_poll_until,
)
from test.uts.helpers.sandbox import random_id

# The specification's channel prefix, and the annotation type it annotates with.
MUTABLE_NAMESPACE = 'mutable:'
REACTION_TYPE = 'com.ably.reactions'

# What the specification's `poll_until_success` gives a message store read. The store is
# eventually consistent, so a serial-scoped read answers 404, or answers with the version
# before the one being waited for, until the write has landed.
STORE_TIMEOUT = 20.0

# The modes the specification gives the two ends of the annotation tests.
PUBLISHER_MODES = [
    ChannelMode.PUBLISH,
    ChannelMode.SUBSCRIBE,
    ChannelMode.ANNOTATION_PUBLISH,
    ChannelMode.ANNOTATION_SUBSCRIBE,
]
SUBSCRIBER_MODES = [ChannelMode.SUBSCRIBE, ChannelMode.ANNOTATION_SUBSCRIBE]


def mutable_channel_name(name):
    """The channel a specification builds as `"mutable:rt-..." + random_id()`."""
    return f'{MUTABLE_NAMESPACE}{name}-{random_id()}'


async def connected_pair(api_key, use_binary_protocol):
    """The two clients every observing test in the specification opens with."""
    client_a = sandbox_realtime_client(api_key, use_binary_protocol=use_binary_protocol)
    client_b = sandbox_realtime_client(api_key, use_binary_protocol=use_binary_protocol)

    client_a.connect()
    client_b.connect()

    await await_connection_state(client_a, ConnectionState.CONNECTED, timeout=10)
    await await_connection_state(client_b, ConnectionState.CONNECTED, timeout=10)

    return client_a, client_b


async def await_messages(received_messages, count, description):
    """The specification's `poll_until(received_messages.length >= count)`."""
    await wall_clock_poll_until(
        lambda: len(received_messages) >= count, interval=0.2, description=description)


# UTS: realtime/integration/RTL32/update-message-observed-0
async def test_rtl32_update_message_observed(realtime_sandbox, use_binary_protocol):
    channel_name = mutable_channel_name('rt-update')
    client_a, client_b = await connected_pair(realtime_sandbox.key_str, use_binary_protocol)

    channel_a = client_a.channels.get(channel_name)
    channel_b = client_b.channels.get(channel_name)

    await channel_b.attach()

    received_messages = []
    await channel_b.subscribe(lambda msg: received_messages.append(msg))

    await channel_a.attach()

    await channel_a.publish('original', 'v1')

    await await_messages(received_messages, 1, 'client B to receive the original')

    serial = received_messages[0].serial

    update_result = await channel_a.update_message(
        Message(serial=serial, name='updated', data='v2'),
        operation=MessageOperation(description='edited'))

    await await_messages(received_messages, 2, 'client B to receive the update')

    assert isinstance(update_result, UpdateDeleteResult)
    assert isinstance(update_result.version_serial, str)
    assert len(update_result.version_serial) > 0

    assert received_messages[0].action == MessageAction.MESSAGE_CREATE
    assert received_messages[0].name == 'original'
    assert received_messages[0].data == 'v1'
    assert isinstance(received_messages[0].serial, str)
    assert len(received_messages[0].serial) > 0

    update_msg = received_messages[1]
    assert update_msg.action == MessageAction.MESSAGE_UPDATE
    assert update_msg.name == 'updated'
    assert update_msg.data == 'v2'
    assert update_msg.serial == serial


# UTS: realtime/integration/RTL32/delete-message-observed-1
async def test_rtl32_delete_message_observed(realtime_sandbox, use_binary_protocol):
    channel_name = mutable_channel_name('rt-delete')
    client_a, client_b = await connected_pair(realtime_sandbox.key_str, use_binary_protocol)

    channel_a = client_a.channels.get(channel_name)
    channel_b = client_b.channels.get(channel_name)

    await channel_b.attach()

    received_messages = []
    await channel_b.subscribe(lambda msg: received_messages.append(msg))

    await channel_a.attach()

    await channel_a.publish('to-delete', 'ephemeral')

    await await_messages(received_messages, 1, 'client B to receive the original')

    serial = received_messages[0].serial

    delete_result = await channel_a.delete_message(Message(serial=serial))

    await await_messages(received_messages, 2, 'client B to receive the delete')

    assert isinstance(delete_result, UpdateDeleteResult)
    assert isinstance(delete_result.version_serial, str)
    assert len(delete_result.version_serial) > 0

    delete_msg = received_messages[1]
    assert delete_msg.action == MessageAction.MESSAGE_DELETE
    assert delete_msg.serial == serial


# UTS: realtime/integration/RTL32/append-message-observed-2
async def test_rtl32_append_message_observed(realtime_sandbox, use_binary_protocol):
    channel_name = mutable_channel_name('rt-append')
    client_a, client_b = await connected_pair(realtime_sandbox.key_str, use_binary_protocol)

    channel_a = client_a.channels.get(channel_name)
    channel_b = client_b.channels.get(channel_name)

    await channel_b.attach()

    received_messages = []
    await channel_b.subscribe(lambda msg: received_messages.append(msg))

    await channel_a.attach()

    await channel_a.publish('appendable', 'original')

    await await_messages(received_messages, 1, 'client B to receive the original')

    serial = received_messages[0].serial

    append_result = await channel_a.append_message(
        Message(serial=serial, data='appended-data'),
        operation=MessageOperation(description='thread reply'))

    await await_messages(received_messages, 2, 'client B to receive the append')

    assert isinstance(append_result, UpdateDeleteResult)
    assert isinstance(append_result.version_serial, str)
    assert len(append_result.version_serial) > 0

    append_msg = received_messages[1]
    assert append_msg.action == MessageAction.MESSAGE_APPEND
    assert append_msg.data == 'appended-data'
    assert append_msg.serial == serial


# UTS: realtime/integration/RTL32/full-mutation-lifecycle-3
async def test_rtl32_full_mutation_lifecycle(realtime_sandbox, use_binary_protocol):
    channel_name = mutable_channel_name('rt-lifecycle')
    client_a, client_b = await connected_pair(realtime_sandbox.key_str, use_binary_protocol)

    channel_a = client_a.channels.get(channel_name)
    channel_b = client_b.channels.get(channel_name)

    await channel_b.attach()

    received_messages = []
    await channel_b.subscribe(lambda msg: received_messages.append(msg))

    await channel_a.attach()

    await channel_a.publish('lifecycle', 'v1')
    await await_messages(received_messages, 1, 'client B to receive the create')

    serial = received_messages[0].serial

    await channel_a.update_message(
        Message(serial=serial, name='lifecycle', data='v2'),
        operation=MessageOperation(description='edit 1'))
    await await_messages(received_messages, 2, 'client B to receive the update')

    await channel_a.append_message(
        Message(serial=serial, data='reply-data'),
        operation=MessageOperation(description='thread reply'))
    await await_messages(received_messages, 3, 'client B to receive the append')

    await channel_a.delete_message(Message(serial=serial))
    await await_messages(received_messages, 4, 'client B to receive the delete')

    assert len(received_messages) == 4

    assert received_messages[0].action == MessageAction.MESSAGE_CREATE
    assert received_messages[0].name == 'lifecycle'
    assert received_messages[0].data == 'v1'
    assert received_messages[0].serial == serial

    assert received_messages[1].action == MessageAction.MESSAGE_UPDATE
    assert received_messages[1].name == 'lifecycle'
    assert received_messages[1].data == 'v2'
    assert received_messages[1].serial == serial

    assert received_messages[2].action == MessageAction.MESSAGE_APPEND
    assert received_messages[2].data == 'reply-data'
    assert received_messages[2].serial == serial

    assert received_messages[3].action == MessageAction.MESSAGE_DELETE
    assert received_messages[3].serial == serial


# UTS: realtime/integration/RTL28/get-message-and-versions-0
async def test_rtl28_get_message_and_versions(realtime_sandbox, use_binary_protocol):
    channel_name = mutable_channel_name('rt-get-versions')
    client = sandbox_realtime_client(
        realtime_sandbox.key_str, use_binary_protocol=use_binary_protocol)

    client.connect()
    await await_connection_state(client, ConnectionState.CONNECTED, timeout=10)

    channel = client.channels.get(channel_name)
    await channel.attach()

    received_messages = []
    await channel.subscribe(lambda msg: received_messages.append(msg))

    await channel.publish('versioned', 'v1')

    await await_messages(received_messages, 1, 'the published message')

    serial = received_messages[0].serial

    await channel.update_message(
        Message(serial=serial, data='v2'), operation=MessageOperation(description='first edit'))
    await channel.update_message(
        Message(serial=serial, data='v3'), operation=MessageOperation(description='second edit'))

    # The message store is eventually consistent, so the two reads poll rather than
    # sleeping a fixed interval: a message that is already readable may still be a stale
    # version, and a version listing may still be short. Only the store's 404 is
    # swallowed — every other error means the request was wrong rather than early, and
    # swallowing it would leave the test timing out on a message it could never explain.
    async def latest_version():
        try:
            message = await channel.get_message(serial)
        except AblyException as error:
            if error.status_code == 404:
                return None
            raise
        if message.action == MessageAction.MESSAGE_UPDATE and message.data == 'v3':
            return message
        return None

    msg = await wall_clock_poll_until(
        latest_version, timeout=STORE_TIMEOUT, description='the second update to be readable')

    async def full_history():
        try:
            result = await channel.get_message_versions(serial)
        except AblyException as error:
            if error.status_code == 404:
                return None
            raise
        return result if len(result.items) >= 3 else None

    versions = await wall_clock_poll_until(
        full_history, timeout=STORE_TIMEOUT, description='the full version history')

    assert isinstance(msg, Message)
    assert msg.serial == serial
    assert msg.data == 'v3'
    assert msg.action == MessageAction.MESSAGE_UPDATE

    assert isinstance(versions, PaginatedResult)
    assert len(versions.items) >= 3  # original + 2 updates

    for item in versions.items:
        assert isinstance(item, Message)
        assert item.serial == serial


# UTS: realtime/integration/RTAN1/annotation-publish-delete-0
async def test_rtan1_annotation_publish_delete(realtime_sandbox, use_binary_protocol):
    channel_name = mutable_channel_name('rt-annotations')
    client_a, client_b = await connected_pair(realtime_sandbox.key_str, use_binary_protocol)

    channel_a = client_a.channels.get(channel_name, ChannelOptions(modes=PUBLISHER_MODES))
    channel_b = client_b.channels.get(channel_name, ChannelOptions(modes=SUBSCRIBER_MODES))

    await channel_b.attach()

    received_annotations = []
    await channel_b.annotations.subscribe(lambda ann: received_annotations.append(ann))

    # Client A subscribes to its own messages to capture the serial to annotate.
    received_messages = []
    await channel_a.subscribe(lambda msg: received_messages.append(msg))

    await channel_a.attach()

    await channel_a.publish('annotatable', 'content')

    await await_messages(received_messages, 1, 'the message to annotate')

    serial = received_messages[0].serial

    await channel_a.annotations.publish(serial, Annotation(type=REACTION_TYPE, name='like'))

    await wall_clock_poll_until(
        lambda: len(received_annotations) >= 1, interval=0.2,
        description='the annotation to arrive on client B')

    await channel_a.annotations.delete(serial, Annotation(type=REACTION_TYPE, name='like'))

    await wall_clock_poll_until(
        lambda: len(received_annotations) >= 2, interval=0.2,
        description='the annotation delete to arrive on client B')

    assert len(received_annotations) == 2

    create_ann = received_annotations[0]
    assert create_ann.action == AnnotationAction.ANNOTATION_CREATE
    assert create_ann.type == REACTION_TYPE
    assert create_ann.name == 'like'
    assert create_ann.message_serial == serial

    delete_ann = received_annotations[1]
    assert delete_ann.action == AnnotationAction.ANNOTATION_DELETE
    assert delete_ann.type == REACTION_TYPE
    assert delete_ann.name == 'like'
    assert delete_ann.message_serial == serial


# UTS: realtime/integration/RTAN4c/annotation-type-filtering-0
async def test_rtan4c_annotation_type_filtering(realtime_sandbox, use_binary_protocol):
    channel_name = mutable_channel_name('rt-ann-filter')
    client_a, client_b = await connected_pair(realtime_sandbox.key_str, use_binary_protocol)

    channel_a = client_a.channels.get(channel_name, ChannelOptions(modes=PUBLISHER_MODES))
    channel_b = client_b.channels.get(channel_name, ChannelOptions(modes=SUBSCRIBER_MODES))

    await channel_b.attach()

    filtered_annotations = []
    await channel_b.annotations.subscribe(
        REACTION_TYPE, lambda ann: filtered_annotations.append(ann))

    # The unfiltered listener is what tells the test when all three have been delivered,
    # so that a filtered listener which wrongly received the third type is caught rather
    # than raced past.
    all_annotations = []
    await channel_b.annotations.subscribe(lambda ann: all_annotations.append(ann))

    received_messages = []
    await channel_a.subscribe(lambda msg: received_messages.append(msg))

    await channel_a.attach()

    await channel_a.publish('multi-type', 'content')

    await await_messages(received_messages, 1, 'the message to annotate')

    serial = received_messages[0].serial

    await channel_a.annotations.publish(serial, Annotation(type=REACTION_TYPE, name='like'))
    await channel_a.annotations.publish(
        serial, Annotation(type='com.example.comments', name='comment'))
    await channel_a.annotations.publish(serial, Annotation(type=REACTION_TYPE, name='heart'))

    await wall_clock_poll_until(
        lambda: len(all_annotations) >= 3, interval=0.2,
        description='all three annotations to arrive on client B')

    assert len(all_annotations) == 3

    assert len(filtered_annotations) == 2
    assert filtered_annotations[0].type == REACTION_TYPE
    assert filtered_annotations[0].name == 'like'
    assert filtered_annotations[1].type == REACTION_TYPE
    assert filtered_annotations[1].name == 'heart'


# UTS: realtime/integration/RTAN4d/annotation-implicit-attach-0
async def test_rtan4d_annotation_implicit_attach(realtime_sandbox, use_binary_protocol):
    channel_name = mutable_channel_name('rt-ann-implicit-attach')
    client = sandbox_realtime_client(
        realtime_sandbox.key_str, use_binary_protocol=use_binary_protocol)

    client.connect()
    await await_connection_state(client, ConnectionState.CONNECTED, timeout=10)

    channel = client.channels.get(
        channel_name, ChannelOptions(modes=[ChannelMode.ANNOTATION_SUBSCRIBE]))

    assert channel.state == ChannelState.INITIALIZED

    await channel.annotations.subscribe(lambda ann: None)

    await await_channel_state(channel, ChannelState.ATTACHED, timeout=10)

    assert channel.state == ChannelState.ATTACHED
