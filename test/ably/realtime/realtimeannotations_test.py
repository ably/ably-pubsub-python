import asyncio
import logging
import random
import string

import pytest

from ably.types.annotation import Annotation, AnnotationAction
from ably.types.channelmode import ChannelMode
from ably.types.channeloptions import ChannelOptions
from ably.types.message import MessageAction
from test.ably.testapp import TestApp
from test.ably.utils import BaseAsyncTestCase, ReusableFuture, assert_waiter

log = logging.getLogger(__name__)


@pytest.mark.parametrize("transport", ["json", "msgpack"], ids=["JSON", "MsgPack"])
class TestRealtimeAnnotations(BaseAsyncTestCase):

    @pytest.fixture(autouse=True)
    async def setup(self, transport):
        self.test_vars = await TestApp.get_test_vars()

        client_id = ''.join(random.choices(string.ascii_letters + string.digits, k=10))
        self.realtime_client = await TestApp.get_ably_realtime(
            use_binary_protocol=True if transport == 'msgpack' else False,
            client_id=client_id,
        )
        self.rest_client = await TestApp.get_ably_rest(
            use_binary_protocol=True if transport == 'msgpack' else False,
            client_id=client_id,
        )

    async def test_publish_and_subscribe_annotations(self):
        """RTAN1/RTAN4: Publish and subscribe to annotations via realtime and REST"""
        channel_options = ChannelOptions(modes=[
            ChannelMode.PUBLISH,
            ChannelMode.SUBSCRIBE,
            ChannelMode.ANNOTATION_PUBLISH,
            ChannelMode.ANNOTATION_SUBSCRIBE
        ])
        channel_name = self.get_channel_name('mutable:publish_and_subscribe_annotations')
        channel = self.realtime_client.channels.get(
            channel_name,
            channel_options,
        )
        rest_channel = self.rest_client.channels.get(channel_name)
        await channel.attach()

        # Setup annotation listener
        annotation_future = asyncio.Future()

        async def on_annotation(annotation):
            if not annotation_future.done():
                annotation_future.set_result(annotation)

        await channel.annotations.subscribe(on_annotation)

        # The summary for a message is delivered as a separate message carrying the same
        # serial, once the server has aggregated the annotations made against it, so the
        # message's own create echo reaches this listener first
        message_summary = asyncio.Future()

        def on_message(msg):
            if msg.action == MessageAction.MESSAGE_SUMMARY and not message_summary.done():
                message_summary.set_result(msg)

        await channel.subscribe('message', on_message)

        # Publish a message
        publish_result = await channel.publish('message', 'foobar')

        # Publish annotation using realtime
        await channel.annotations.publish(publish_result.serials[0], Annotation(
            type='reaction:distinct.v1',
            name='👍'
        ))

        # Wait for annotation
        annotation = await annotation_future
        assert annotation.action == AnnotationAction.ANNOTATION_CREATE
        assert annotation.message_serial == publish_result.serials[0]
        assert annotation.type == 'reaction:distinct.v1'
        assert annotation.name == '👍'
        assert annotation.serial > annotation.message_serial

        # Wait for summary message
        summary = await message_summary
        assert summary.action == MessageAction.MESSAGE_SUMMARY
        assert summary.serial == publish_result.serials[0]
        assert summary.annotations.summary['reaction:distinct.v1']['👍']['total'] == 1

        # Try again but with REST publish
        annotation_future2 = asyncio.Future()

        async def on_annotation2(annotation):
            if not annotation_future2.done():
                annotation_future2.set_result(annotation)

        await channel.annotations.subscribe(on_annotation2)

        await rest_channel.annotations.publish(publish_result.serials[0], Annotation(
            type='reaction:distinct.v1',
            name='😕'
        ))

        annotation = await annotation_future2
        assert annotation.action == AnnotationAction.ANNOTATION_CREATE
        assert annotation.message_serial == publish_result.serials[0]
        assert annotation.type == 'reaction:distinct.v1'
        assert annotation.name == '😕'
        assert annotation.serial > annotation.message_serial

    async def test_get_all_annotations_for_a_message(self):
        """RTAN3: Retrieve all annotations for a message"""
        channel_options = ChannelOptions(modes=[
            ChannelMode.PUBLISH,
            ChannelMode.SUBSCRIBE,
            ChannelMode.ANNOTATION_PUBLISH,
            ChannelMode.ANNOTATION_SUBSCRIBE
        ])
        channel = self.realtime_client.channels.get(
            self.get_channel_name('mutable:get_all_annotations_for_a_message'),
            channel_options
        )
        await channel.attach()

        # Publish a message
        publish_result = await channel.publish('message', 'foobar')

        # Publish multiple annotations
        emojis = ['👍', '😕', '👎']
        for emoji in emojis:
            await channel.annotations.publish(publish_result.serials[0], Annotation(
                type='reaction:distinct.v1',
                name=emoji
            ))

        # Wait for all annotations to appear
        annotations = []

        async def check_annotations():
            nonlocal annotations
            res = await channel.annotations.get(publish_result.serials[0], {})
            annotations = res.items
            return len(annotations) == 3

        await assert_waiter(check_annotations, timeout=10)

        # Verify annotations
        assert annotations[0].action == AnnotationAction.ANNOTATION_CREATE
        assert annotations[0].message_serial == publish_result.serials[0]
        assert annotations[0].type == 'reaction:distinct.v1'
        assert annotations[0].name == '👍'
        assert annotations[1].name == '😕'
        assert annotations[2].name == '👎'
        assert annotations[1].serial > annotations[0].serial
        assert annotations[2].serial > annotations[1].serial

    async def test_subscribe_by_annotation_type(self):
        """RTAN4c: Subscribe to annotations filtered by type"""
        channel_options = ChannelOptions(modes=[
            ChannelMode.PUBLISH,
            ChannelMode.SUBSCRIBE,
            ChannelMode.ANNOTATION_PUBLISH,
            ChannelMode.ANNOTATION_SUBSCRIBE
        ])
        channel = self.realtime_client.channels.get(
            self.get_channel_name('mutable:subscribe_by_type'),
            channel_options
        )
        await channel.attach()

        # Setup message listener
        message_future = asyncio.Future()

        def on_message(msg):
            if not message_future.done():
                message_future.set_result(msg)

        await channel.subscribe('message', on_message)

        # Subscribe to specific annotation type
        reaction_future = asyncio.Future()

        async def on_reaction(annotation):
            if not reaction_future.done():
                reaction_future.set_result(annotation)

        await channel.annotations.subscribe('reaction:distinct.v1', on_reaction)

        # Publish message and annotation
        publish_result = await channel.publish('message', 'test')

        await channel.annotations.publish(publish_result.serials[0], Annotation(
            type='reaction:distinct.v1',
            name='👍'
        ))

        # Should receive the annotation
        annotation = await reaction_future
        assert annotation.type == 'reaction:distinct.v1'
        assert annotation.name == '👍'

    async def test_unsubscribe_annotations(self):
        """RTAN5: Unsubscribe from annotation events"""
        channel_options = ChannelOptions(modes=[
            ChannelMode.PUBLISH,
            ChannelMode.SUBSCRIBE,
            ChannelMode.ANNOTATION_PUBLISH,
            ChannelMode.ANNOTATION_SUBSCRIBE
        ])
        channel = self.realtime_client.channels.get(
            self.get_channel_name('mutable:unsubscribe_annotations'),
            channel_options
        )
        await channel.attach()

        annotations_received = []
        annotation_future = ReusableFuture()

        async def on_annotation(annotation):
            annotations_received.append(annotation)
            annotation_future.set_result(annotation)

        await channel.annotations.subscribe(on_annotation)

        # Publish message and first annotation
        publish_result = await channel.publish('message', 'test')

        await channel.annotations.publish(publish_result.serials[0], Annotation(
            type='reaction:distinct.v1',
            name='👍'
        ))

        # Wait for the first annotation to appear
        await annotation_future.get()
        assert len(annotations_received) == 1

        # Unsubscribe
        channel.annotations.unsubscribe(on_annotation)

        await channel.annotations.subscribe(lambda annotation: annotation_future.set_result(annotation))

        # Publish another annotation
        await channel.annotations.publish(publish_result.serials[0], Annotation(
            type='reaction:distinct.v1',
            name='😕'
        ))

        # Wait for the second annotation to appear in another listener
        await annotation_future.get()

        assert len(annotations_received) == 1

    async def test_delete_annotation(self):
        """RTAN2: Delete an annotation via realtime"""
        channel_options = ChannelOptions(modes=[
            ChannelMode.PUBLISH,
            ChannelMode.SUBSCRIBE,
            ChannelMode.ANNOTATION_PUBLISH,
            ChannelMode.ANNOTATION_SUBSCRIBE
        ])
        channel = self.realtime_client.channels.get(
            self.get_channel_name('mutable:delete_annotation'),
            channel_options
        )
        await channel.attach()

        # Setup message listener
        message_future = asyncio.Future()

        def on_message(msg):
            if not message_future.done():
                message_future.set_result(msg)

        await channel.subscribe('message', on_message)

        annotations_received = []
        annotation_future = ReusableFuture()
        async def on_annotation(annotation):
            annotations_received.append(annotation)
            annotation_future.set_result(annotation)

        await channel.annotations.subscribe(on_annotation)

        # Publish message and annotation
        await channel.publish('message', 'test')
        message = await message_future

        await channel.annotations.publish(message.serial, Annotation(
            type='reaction:distinct.v1',
            name='👍'
        ))

        await annotation_future.get()

        # Wait for create annotation
        assert len(annotations_received) == 1
        assert annotations_received[0].action == AnnotationAction.ANNOTATION_CREATE

        # Delete the annotation
        await channel.annotations.delete(message.serial, Annotation(
            type='reaction:distinct.v1',
            name='👍'
        ))

        # Wait for delete annotation
        await annotation_future.get()

        assert len(annotations_received) == 2
        assert annotations_received[1].action == AnnotationAction.ANNOTATION_DELETE

    async def test_subscribe_without_annotation_mode_warns(self, caplog):
        """RTAN4e: Subscribing without ANNOTATION_SUBSCRIBE mode logs a warning.

        Per spec, the library should log a warning indicating that the user has tried
        to add an annotation listener without having requested the ANNOTATION_SUBSCRIBE
        channel mode.
        """
        # Create channel without annotation_subscribe mode
        channel_options = ChannelOptions(modes=[
            ChannelMode.PUBLISH,
            ChannelMode.SUBSCRIBE
        ])
        channel = self.realtime_client.channels.get(
            self.get_channel_name('mutable:no_annotation_mode'),
            channel_options
        )
        await channel.attach()

        async def on_annotation(annotation):
            pass

        # RTAN4e: Should log a warning (not raise), and still register the listener
        with caplog.at_level(logging.WARNING, logger='ably.realtime.annotations'):
            await channel.annotations.subscribe(on_annotation)

        # Verify warning was logged mentioning the missing mode
        assert any('ANNOTATION_SUBSCRIBE' in record.message for record in caplog.records)

        # Listener should still be registered (subscribe didn't fail)
        # Unsubscribe to clean up
        channel.annotations.unsubscribe(on_annotation)
