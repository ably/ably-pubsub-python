"""Derived from uts/rest/integration/mutable_messages.md in ably/specification.

Spec points: RSL1n, RSL11, RSL14, RSL15, RSAN1, RSAN2, RSAN3
"""

from ably.http.paginatedresult import PaginatedResult
from ably.types.annotation import Annotation, AnnotationAction
from ably.types.message import Message, MessageAction
from ably.types.operations import MessageOperation, PublishResult, UpdateDeleteResult
from ably.util.exceptions import AblyException
from test.uts.helpers.client import sandbox_rest_client, wall_clock_poll_until
from test.uts.helpers.sandbox import random_id

# The specification's channel prefix. `test-app-setup.json` configures the
# `mutable` namespace with `mutableMessages: true`, and getMessage,
# updateMessage, deleteMessage, appendMessage and the annotation endpoints are
# all refused on a channel outside it.
MUTABLE_NAMESPACE = 'mutable:'

# The annotation type the specification annotates with.
REACTION_TYPE = 'com.ably.reactions'

# What the specification's `poll_until_success` gives a store read. The store is
# eventually consistent, so a serial-scoped read answers 404 until the write it
# is looking for has landed.
STORE_TIMEOUT = 20.0


def mutable_channel(client, name):
    """The channel a specification builds as `"mutable:test-..." + random_id()`."""
    return client.channels.get(f'{MUTABLE_NAMESPACE}{name}-{random_id()}')


def not_found(error):
    """Whether `error` is the store saying "not yet", rather than a real failure.

    The specification's `poll_until_success` "treats any read error as keep
    polling". Only the not-found is swallowed here: every other error means the
    request was wrong rather than early, and swallowing it would leave the test
    timing out on a message it could never explain.
    """
    return isinstance(error, AblyException) and error.status_code == 404


async def poll_get_message(channel, serial, action=None, description=None):
    """The specification's `poll_until_success` around `getMessage`.

    `get_message` is not `@catch_all`-wrapped, so the store's 404 arrives as an
    `AblyException` carrying that status rather than as a 50000. Returns the
    message once it exists and, where `action` is given, once it carries that
    action.
    """
    async def visible():
        try:
            message = await channel.get_message(serial)
        except AblyException as error:
            if not_found(error):
                return None
            raise
        if action is not None and message.action != action:
            return None
        return message

    return await wall_clock_poll_until(
        visible,
        timeout=STORE_TIMEOUT,
        description=description or f'message {serial} to be readable')


async def poll_message_versions(channel, serial, count):
    """The specification's `poll_until_success` around `getMessageVersions`."""
    async def enough_versions():
        try:
            result = await channel.get_message_versions(serial)
        except AblyException as error:
            if not_found(error):
                return None
            raise
        return result if len(result.items) >= count else None

    return await wall_clock_poll_until(
        enough_versions,
        timeout=STORE_TIMEOUT,
        description=f'{count} versions of message {serial}')


async def poll_annotations(channel, serial, count):
    """The specification's `poll_until_success` around `annotations.get`."""
    async def enough_annotations():
        try:
            result = await channel.annotations.get(serial)
        except AblyException as error:
            if not_found(error):
                return None
            raise
        return result if len(result.items) >= count else None

    return await wall_clock_poll_until(
        enough_annotations,
        timeout=STORE_TIMEOUT,
        description=f'{count} annotations on message {serial}')


# UTS: rest/integration/RSL1n/publish-returns-serials-0
async def test_rsl1n_publish_returns_serials(sandbox, use_binary_protocol):
    client = sandbox_rest_client(sandbox.key(0).key_str, use_binary_protocol=use_binary_protocol)
    channel = mutable_channel(client, 'test-RSL1n-serials')

    result1 = await channel.publish('event1', 'data1')

    assert isinstance(result1, PublishResult)
    assert isinstance(result1.serials, list)
    assert len(result1.serials) == 1
    assert isinstance(result1.serials[0], str)
    assert len(result1.serials[0]) > 0

    result2 = await channel.publish([
        Message('event2', 'data2'),
        Message('event3', 'data3'),
        Message('event4', 'data4'),
    ])

    assert len(result2.serials) == 3
    assert all(isinstance(serial, str) and len(serial) > 0 for serial in result2.serials)

    assert result2.serials[0] != result2.serials[1]
    assert result2.serials[1] != result2.serials[2]


# UTS: rest/integration/RSL11/get-message-by-serial-0
async def test_rsl11_get_message_by_serial(sandbox, use_binary_protocol):
    client = sandbox_rest_client(sandbox.key(0).key_str, use_binary_protocol=use_binary_protocol)
    channel = mutable_channel(client, 'test-RSL11-getMessage')

    publish_result = await channel.publish('test-event', 'hello world')
    serial = publish_result.serials[0]

    msg = await poll_get_message(channel, serial, description='the published message to be gettable')

    assert isinstance(msg, Message)
    assert msg.name == 'test-event'
    assert msg.data == 'hello world'
    assert msg.serial == serial
    assert msg.action == MessageAction.MESSAGE_CREATE
    assert msg.timestamp is not None


# UTS: rest/integration/RSL15/update-message-0
async def test_rsl15_update_message(sandbox, use_binary_protocol):
    client = sandbox_rest_client(sandbox.key(0).key_str, use_binary_protocol=use_binary_protocol)
    channel = mutable_channel(client, 'test-RSL15-update')

    publish_result = await channel.publish('original', 'original-data')
    serial = publish_result.serials[0]

    update_result = await channel.update_message(
        Message(serial=serial, name='updated', data='updated-data'),
        MessageOperation(description='edited content'),
    )

    assert isinstance(update_result, UpdateDeleteResult)
    assert isinstance(update_result.version_serial, str)
    assert len(update_result.version_serial) > 0

    updated_msg = await poll_get_message(
        channel, serial, action=MessageAction.MESSAGE_UPDATE,
        description='the update to be visible')

    assert updated_msg.name == 'updated'
    assert updated_msg.data == 'updated-data'
    assert updated_msg.action == MessageAction.MESSAGE_UPDATE
    assert updated_msg.version.description == 'edited content'


# UTS: rest/integration/RSL15/delete-message-1
async def test_rsl15_delete_message(sandbox, use_binary_protocol):
    client = sandbox_rest_client(sandbox.key(0).key_str, use_binary_protocol=use_binary_protocol)
    channel = mutable_channel(client, 'test-RSL15-delete')

    publish_result = await channel.publish('to-delete', 'delete-me')
    serial = publish_result.serials[0]

    delete_result = await channel.delete_message(Message(serial=serial))

    assert isinstance(delete_result, UpdateDeleteResult)
    assert isinstance(delete_result.version_serial, str)
    assert len(delete_result.version_serial) > 0

    deleted_msg = await poll_get_message(
        channel, serial, action=MessageAction.MESSAGE_DELETE,
        description='the delete to be visible')

    assert deleted_msg.action == MessageAction.MESSAGE_DELETE


# UTS: rest/integration/RSL14/get-message-versions-0
async def test_rsl14_get_message_versions(sandbox, use_binary_protocol):
    client = sandbox_rest_client(sandbox.key(0).key_str, use_binary_protocol=use_binary_protocol)
    channel = mutable_channel(client, 'test-RSL14-versions')

    publish_result = await channel.publish('versioned', 'v1')
    serial = publish_result.serials[0]

    await channel.update_message(
        Message(serial=serial, data='v2'),
        MessageOperation(description='first edit'),
    )
    await channel.update_message(
        Message(serial=serial, data='v3'),
        MessageOperation(description='second edit'),
    )

    versions = await poll_message_versions(channel, serial, 3)

    assert isinstance(versions, PaginatedResult)
    assert len(versions.items) >= 3

    for item in versions.items:
        assert isinstance(item, Message)
        assert item.serial == serial


# UTS: rest/integration/RSL15/append-message-2
async def test_rsl15_append_message(sandbox, use_binary_protocol):
    client = sandbox_rest_client(sandbox.key(0).key_str, use_binary_protocol=use_binary_protocol)
    channel = mutable_channel(client, 'test-RSL15-append')

    publish_result = await channel.publish('appendable', 'original')
    serial = publish_result.serials[0]

    append_result = await channel.append_message(
        Message(serial=serial, data='appended-data'),
        MessageOperation(description='appended content'),
    )

    assert isinstance(append_result, UpdateDeleteResult)
    assert isinstance(append_result.version_serial, str)
    assert len(append_result.version_serial) > 0


# UTS: rest/integration/RSAN1/annotation-lifecycle-0
async def test_rsan1_annotation_lifecycle(sandbox, use_binary_protocol):
    client = sandbox_rest_client(sandbox.key(0).key_str, use_binary_protocol=use_binary_protocol)
    channel = mutable_channel(client, 'test-RSAN-lifecycle')

    publish_result = await channel.publish('annotatable', 'content')
    serial = publish_result.serials[0]

    await channel.annotations.publish(serial, Annotation(type=REACTION_TYPE, name='like'))

    annotations = await poll_annotations(channel, serial, 1)
    assert len(annotations.items) >= 1

    found = False
    for ann in annotations.items:
        if ann.type == REACTION_TYPE and ann.name == 'like':
            found = True
            assert ann.action == AnnotationAction.ANNOTATION_CREATE
            assert ann.message_serial == serial
    assert found is True

    await channel.annotations.delete(serial, Annotation(type=REACTION_TYPE, name='like'))


# UTS: rest/integration/RSAN3/get-annotations-paginated-0
async def test_rsan3_get_annotations_paginated(sandbox, use_binary_protocol):
    client = sandbox_rest_client(sandbox.key(0).key_str, use_binary_protocol=use_binary_protocol)
    channel = mutable_channel(client, 'test-RSAN3-paginated')

    publish_result = await channel.publish('multi-annotated', 'content')
    serial = publish_result.serials[0]

    await channel.annotations.publish(serial, Annotation(type=REACTION_TYPE, name='like'))
    await channel.annotations.publish(serial, Annotation(type=REACTION_TYPE, name='heart'))

    result = await poll_annotations(channel, serial, 2)

    assert isinstance(result, PaginatedResult)
    assert len(result.items) >= 2

    for ann in result.items:
        assert isinstance(ann, Annotation)
        assert ann.message_serial == serial
        assert ann.type == REACTION_TYPE
        assert ann.timestamp is not None
