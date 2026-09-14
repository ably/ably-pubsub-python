import logging
import random
import string

import pytest

from ably.pubsub.server import AblyException
from ably.pubsub.types.annotation import Annotation, AnnotationAction
from ably.pubsub.types.message import Message
from test.ably.testapp import TestApp
from test.ably.utils import BaseAsyncTestCase, assert_waiter

log = logging.getLogger(__name__)


@pytest.mark.parametrize("transport", ["json", "msgpack"], ids=["JSON", "MsgPack"])
class TestRestAnnotations(BaseAsyncTestCase):

    @pytest.fixture(autouse=True)
    async def setup(self, transport):
        self.test_vars = await TestApp.get_test_vars()
        client_id = ''.join(random.choices(string.ascii_letters + string.digits, k=10))
        self.ably = await TestApp.get_ably_rest(
            use_binary_protocol=True if transport == 'msgpack' else False,
            client_id=client_id,
        )

    async def test_publish_annotation_success(self):
        """Test successfully publishing an annotation on a message"""
        channel = self.ably.channels[self.get_channel_name('mutable:annotation_publish_test')]

        # First publish a message
        result = await channel.publish('test-event', 'test data')
        assert result.serials is not None
        assert len(result.serials) > 0
        serial = result.serials[0]

        # Publish an annotation
        await channel.annotations.publish(serial, Annotation(
            type='reaction:distinct.v1',
            name='👍'
        ))

        annotations_result = None

        # Wait for annotations to appear
        async def check_annotations():
            nonlocal annotations_result
            annotations_result = await channel.annotations.get(serial)
            return len(annotations_result.items) == 1

        await assert_waiter(check_annotations, timeout=10)

        # Get annotations to verify
        annotations = annotations_result.items
        assert len(annotations) >= 1
        assert annotations[0].message_serial == serial
        assert annotations[0].type == 'reaction:distinct.v1'
        assert annotations[0].name == '👍'

    async def test_publish_annotation_with_message_object(self):
        """Test publishing an annotation using a Message object"""
        channel = self.ably.channels[self.get_channel_name('mutable:annotation_publish_msg_obj')]

        # Publish a message
        result = await channel.publish('test-event', 'test data')
        serial = result.serials[0]

        # Create a message object
        message = Message(serial=serial)

        # Publish annotation with message object
        await channel.annotations.publish(message, Annotation(
            type='reaction:distinct.v1',
            name='😕'
        ))

        annotations_result = None

        # Wait for annotations to appear
        async def check_annotations():
            nonlocal annotations_result
            annotations_result = await channel.annotations.get(serial)
            return len(annotations_result.items) == 1

        await assert_waiter(check_annotations, timeout=10)

        # Verify
        annotations_result = await channel.annotations.get(serial)
        annotations = annotations_result.items
        assert len(annotations) >= 1
        assert annotations[0].name == '😕'

    async def test_publish_annotation_without_serial_fails(self):
        """Test that publishing without a serial raises an exception"""
        channel = self.ably.channels[self.get_channel_name('mutable:annotation_no_serial')]

        with pytest.raises(AblyException) as exc_info:
            await channel.annotations.publish(None, Annotation(type='reaction', name='👍'))

        assert exc_info.value.status_code == 400
        assert exc_info.value.code == 40003

    async def test_delete_annotation_success(self):
        """Test successfully deleting an annotation"""
        channel = self.ably.channels[self.get_channel_name('mutable:annotation_delete_test')]

        # Publish a message
        result = await channel.publish('test-event', 'test data')
        serial = result.serials[0]

        # Publish an annotation
        await channel.annotations.publish(serial, Annotation(
            type='reaction:distinct.v1',
            name='👍'
        ))

        annotations_result = None

        # Wait for annotation to appear
        async def check_annotation():
            nonlocal annotations_result
            annotations_result = await channel.annotations.get(serial)
            return len(annotations_result.items) >= 1

        await assert_waiter(check_annotation, timeout=10)

        # Delete the annotation
        await channel.annotations.delete(serial, Annotation(
            type='reaction:distinct.v1',
            name='👍'
        ))

        # Wait for annotation to appear
        async def check_deleted_annotation():
            nonlocal annotations_result
            annotations_result = await channel.annotations.get(serial)
            return len(annotations_result.items) >= 2

        await assert_waiter(check_deleted_annotation, timeout=10)
        assert annotations_result.items[-1].type == 'reaction:distinct.v1'
        assert annotations_result.items[-1].action == AnnotationAction.ANNOTATION_DELETE

    async def test_get_all_annotations(self):
        """Test retrieving all annotations for a message"""
        channel = self.ably.channels[self.get_channel_name('mutable:annotation_get_all_test')]

        # Publish a message
        result = await channel.publish('test-event', 'test data')
        serial = result.serials[0]

        # Publish annotations
        await channel.annotations.publish(serial, Annotation(type='reaction:distinct.v1', name='👍'))
        await channel.annotations.publish(serial, Annotation(type='reaction:distinct.v1', name='😕'))
        await channel.annotations.publish(serial, Annotation(type='reaction:distinct.v1', name='👎'))

        # Wait and get all annotations
        async def check_annotations():
            res = await channel.annotations.get(serial)
            return len(res.items) >= 3

        await assert_waiter(check_annotations, timeout=10)

        annotations_result = await channel.annotations.get(serial)
        annotations = annotations_result.items
        assert len(annotations) >= 3
        assert annotations[0].type == 'reaction:distinct.v1'
        assert annotations[0].message_serial == serial
        # Verify serials are in order
        if len(annotations) > 1:
            assert annotations[1].serial > annotations[0].serial
        if len(annotations) > 2:
            assert annotations[2].serial > annotations[1].serial

    async def test_annotation_properties(self):
        """Test that annotation properties are correctly set"""
        channel = self.ably.channels[self.get_channel_name('mutable:annotation_properties_test')]

        # Publish a message
        result = await channel.publish('test-event', 'test data')
        serial = result.serials[0]

        # Publish annotation with various properties
        await channel.annotations.publish(serial, Annotation(
            type='reaction:distinct.v1',
            name='❤️',
            data={'count': 5}
        ))

        # Retrieve and verify
        async def check_annotation():
            res = await channel.annotations.get(serial)
            return len(res.items) > 0

        await assert_waiter(check_annotation, timeout=10)

        annotations_result = await channel.annotations.get(serial)
        annotation = annotations_result.items[0]
        assert annotation.message_serial == serial
        assert annotation.type == 'reaction:distinct.v1'
        assert annotation.name == '❤️'
        assert annotation.serial is not None
        assert annotation.serial > serial
