import base64
import binascii
import json
import logging
import os
import uuid
from unittest import mock

import httpx
import msgpack
import pytest

from ably.pubsub.rest.auth import Auth
from ably.pubsub.server import AblyException, IncompatibleClientIdException, api_version
from ably.pubsub.types.message import Message
from ably.pubsub.types.tokendetails import TokenDetails
from ably.pubsub.util import case
from test.ably import utils
from test.ably.testapp import TestApp
from test.ably.utils import BaseAsyncTestCase, VaryByProtocolTestsMetaclass, assert_waiter, dont_vary_protocol

log = logging.getLogger(__name__)


# Ignore library warning regarding client_id
@pytest.mark.filterwarnings('ignore::DeprecationWarning')
class TestRestChannelPublish(BaseAsyncTestCase, metaclass=VaryByProtocolTestsMetaclass):

    @pytest.fixture(autouse=True)
    async def setup(self):
        self.test_vars = await TestApp.get_test_vars()
        self.ably = await TestApp.get_ably_rest()
        self.client_id = uuid.uuid4().hex
        self.ably_with_client_id = await TestApp.get_ably_rest(client_id=self.client_id, use_token_auth=True)
        yield
        await self.ably.close()
        await self.ably_with_client_id.close()

    def per_protocol_setup(self, use_binary_protocol):
        self.ably.options.use_binary_protocol = use_binary_protocol
        self.ably_with_client_id.options.use_binary_protocol = use_binary_protocol
        self.use_binary_protocol = use_binary_protocol

    async def test_publish_various_datatypes_text(self):
        publish0 = self.ably.channels[
            self.get_channel_name('persisted:publish0')]

        await publish0.publish("publish0", "This is a string message payload")
        await publish0.publish("publish1", b"This is a byte[] message payload")
        await publish0.publish("publish2", {"test": "This is a JSONObject message payload"})
        await publish0.publish("publish3", ["This is a JSONArray message payload"])

        # Get the history for this channel
        history = await publish0.history()
        messages = history.items
        assert messages is not None, "Expected non-None messages"
        assert len(messages) == 4, "Expected 4 messages"

        message_contents = {m.name: m.data for m in messages}
        log.debug(f"message_contents: {str(message_contents)}")

        assert message_contents["publish0"] == "This is a string message payload", \
            "Expect publish0 to be expected String)"

        assert message_contents["publish1"] == b"This is a byte[] message payload", \
            "Expect publish1 to be expected byte[]. Actual: {}".format(str(message_contents['publish1']))

        assert message_contents["publish2"] == {"test": "This is a JSONObject message payload"}, \
            "Expect publish2 to be expected JSONObject"

        assert message_contents["publish3"] == ["This is a JSONArray message payload"], \
            "Expect publish3 to be expected JSONObject"

    @dont_vary_protocol
    async def test_unsupported_payload_must_raise_exception(self):
        channel = self.ably.channels["persisted:publish0"]
        for data in [1, 1.1, True]:
            with pytest.raises(AblyException):
                await channel.publish('event', data)

    async def test_publish_message_list(self):
        channel = self.ably.channels[
            self.get_channel_name('persisted:message_list_channel')]

        expected_messages = [Message(f"name-{i}", str(i)) for i in range(3)]

        await channel.publish(messages=expected_messages)

        # Get the history for this channel
        history = await channel.history()
        messages = history.items

        assert messages is not None, "Expected non-None messages"
        assert len(messages) == len(expected_messages), "Expected 3 messages"

        for m, expected_m in zip(messages, reversed(expected_messages)):
            assert m.name == expected_m.name
            assert m.data == expected_m.data

    async def test_message_list_generate_one_request(self):
        channel = self.ably.channels[
            self.get_channel_name('persisted:message_list_channel_one_request')]

        expected_messages = [Message(f"name-{i}", str(i)) for i in range(3)]

        with mock.patch('ably.pubsub.rest.rest.Http.post',
                        wraps=channel.ably.http.post) as post_mock:
            await channel.publish(messages=expected_messages)
        assert post_mock.call_count == 1

        if self.use_binary_protocol:
            messages = msgpack.unpackb(post_mock.call_args[1]['body'])
        else:
            messages = json.loads(post_mock.call_args[1]['body'])

        for i, message in enumerate(messages):
            assert message['name'] == 'name-' + str(i)
            assert message['data'] == str(i)

    async def test_publish_error(self):
        ably = await TestApp.get_ably_rest(use_binary_protocol=self.use_binary_protocol)
        await ably.auth.authorize(
            token_params={'capability': {"only_subscribe": ["subscribe"]}})

        with pytest.raises(AblyException) as excinfo:
            await ably.channels["only_subscribe"].publish()

        assert 401 == excinfo.value.status_code
        assert 40160 == excinfo.value.code
        await ably.close()

    async def test_publish_message_null_name(self):
        channel = self.ably.channels[
            self.get_channel_name('persisted:message_null_name_channel')]

        data = "String message"
        await channel.publish(name=None, data=data)

        # Get the history for this channel
        history = await channel.history()
        messages = history.items

        assert messages is not None, "Expected non-None messages"
        assert len(messages) == 1, "Expected 1 message"
        assert messages[0].name is None
        assert messages[0].data == data

    async def test_publish_message_null_data(self):
        channel = self.ably.channels[
            self.get_channel_name('persisted:message_null_data_channel')]

        name = "Test name"
        await channel.publish(name=name, data=None)

        # Get the history for this channel
        history = await channel.history()
        messages = history.items

        assert messages is not None, "Expected non-None messages"
        assert len(messages) == 1, "Expected 1 message"

        assert messages[0].name == name
        assert messages[0].data is None

    async def test_publish_message_null_name_and_data(self):
        channel = self.ably.channels[
            self.get_channel_name('persisted:null_name_and_data_channel')]

        await channel.publish(name=None, data=None)
        await channel.publish()

        # Get the history for this channel
        history = await channel.history()
        messages = history.items

        assert messages is not None, "Expected non-None messages"
        assert len(messages) == 2, "Expected 2 messages"

        for m in messages:
            assert m.name is None
            assert m.data is None

    async def test_publish_message_null_name_and_data_keys_arent_sent(self):
        channel = self.ably.channels[
            self.get_channel_name('persisted:null_name_and_data_keys_arent_sent_channel')]

        with mock.patch('ably.pubsub.rest.rest.Http.post',
                        wraps=channel.ably.http.post) as post_mock:
            await channel.publish(name=None, data=None)

            history = await channel.history()
            messages = history.items

            assert messages is not None, "Expected non-None messages"
            assert len(messages) == 1, "Expected 1 message"

            assert post_mock.call_count == 1

            if self.use_binary_protocol:
                posted_body = msgpack.unpackb(post_mock.call_args[1]['body'])
            else:
                posted_body = json.loads(post_mock.call_args[1]['body'])

            assert 'name' not in posted_body
            assert 'data' not in posted_body

    async def test_message_attr(self):
        publish0 = self.ably.channels[
            self.get_channel_name('persisted:publish_message_attr')]

        messages = [Message('publish',
                            {"test": "This is a JSONObject message payload"},
                            client_id='client_id')]
        await publish0.publish(messages=messages)

        # Get the history for this channel
        history = await publish0.history()
        message = history.items[0]
        assert isinstance(message, Message)
        assert message.id
        assert message.name
        assert message.data == {'test': 'This is a JSONObject message payload'}
        assert message.encoding == ''
        assert message.client_id == 'client_id'
        assert isinstance(message.timestamp, int)

    async def test_token_is_bound_to_options_client_id_after_publish(self):
        # null before publish
        assert self.ably_with_client_id.auth.token_details is None

        # created after message publish and will have client_id
        channel = self.ably_with_client_id.channels[
            self.get_channel_name('persisted:restricted_to_client_id')]
        await channel.publish(name='publish', data='test')

        # defined after publish
        assert isinstance(self.ably_with_client_id.auth.token_details, TokenDetails)
        assert self.ably_with_client_id.auth.token_details.client_id == self.client_id
        assert self.ably_with_client_id.auth.auth_mechanism == Auth.Method.TOKEN
        history = await channel.history()
        assert history.items[0].client_id == self.client_id

    async def test_publish_message_without_client_id_on_identified_client(self):
        channel = self.ably_with_client_id.channels[
            self.get_channel_name('persisted:no_client_id_identified_client')]

        with mock.patch('ably.pubsub.rest.rest.Http.post',
                        wraps=channel.ably.http.post) as post_mock:
            await channel.publish(name='publish', data='test')

            history = await channel.history()
            messages = history.items

            assert messages is not None, "Expected non-None messages"
            assert len(messages) == 1, "Expected 1 message"

            assert post_mock.call_count == 2

            if self.use_binary_protocol:
                posted_body = msgpack.unpackb(
                    post_mock.mock_calls[0][2]['body'])
            else:
                posted_body = json.loads(
                    post_mock.mock_calls[0][2]['body'])

            assert 'client_id' not in posted_body

            # Get the history for this channel
            history = await channel.history()
            messages = history.items

            assert messages is not None, "Expected non-None messages"
            assert len(messages) == 1, "Expected 1 message"

            assert messages[0].client_id == self.ably_with_client_id.client_id

    async def test_publish_message_with_client_id_on_identified_client(self):
        # works if same
        channel = self.ably_with_client_id.channels[
            self.get_channel_name('persisted:with_client_id_identified_client')]
        message = Message(name='publish', data='test', client_id=self.ably_with_client_id.client_id)
        await channel.publish(message)

        history = await channel.history()
        messages = history.items

        assert messages is not None, "Expected non-None messages"
        assert len(messages) == 1, "Expected 1 message"

        assert messages[0].client_id == self.ably_with_client_id.client_id

        message = Message(name='publish', data='test', client_id='invalid')
        # fails if different
        with pytest.raises(IncompatibleClientIdException):
            await channel.publish(message)

    async def test_publish_message_with_wrong_client_id_on_implicit_identified_client(self):
        new_token = await self.ably.auth.authorize(token_params={'client_id': uuid.uuid4().hex})
        new_ably = await TestApp.get_ably_rest(key=None,
                                               token=new_token.token,
                                               use_binary_protocol=self.use_binary_protocol)

        channel = new_ably.channels[
            self.get_channel_name('persisted:wrong_client_id_implicit_client')]

        message = Message(name='publish', data='test', client_id='invalid')
        with pytest.raises(AblyException) as excinfo:
            await channel.publish(message)

        assert 400 == excinfo.value.status_code
        assert 40012 == excinfo.value.code
        await new_ably.close()

    # RSA15b
    async def test_wildcard_client_id_can_publish_as_others(self):
        wildcard_token_details = await self.ably.auth.request_token({'client_id': '*'})
        wildcard_ably = await TestApp.get_ably_rest(
            key=None,
            token_details=wildcard_token_details,
            use_binary_protocol=self.use_binary_protocol)

        assert wildcard_ably.auth.client_id == '*'
        channel = wildcard_ably.channels[
            self.get_channel_name('persisted:wildcard_client_id')]
        await channel.publish(name='publish1', data='no client_id')
        some_client_id = uuid.uuid4().hex
        message = Message(name='publish2', data='some client_id', client_id=some_client_id)
        await channel.publish(message)

        history = await channel.history()
        messages = history.items

        assert messages is not None, "Expected non-None messages"
        assert len(messages) == 2, "Expected 2 messages"

        assert messages[0].client_id == some_client_id
        assert messages[1].client_id is None

        await wildcard_ably.close()

    # TM2h
    @dont_vary_protocol
    async def test_invalid_connection_key(self):
        channel = self.ably.channels["persisted:invalid_connection_key"]
        message = Message(data='payload', connection_key='should.be.wrong')
        with pytest.raises(AblyException) as excinfo:
            await channel.publish(messages=[message])

        assert 400 == excinfo.value.status_code
        assert 40006 == excinfo.value.code

    # TM2i, RSL6a2, RSL1h
    async def test_publish_extras(self):
        channel = self.ably.channels[
            self.get_channel_name('canpublish:extras_channel')]
        extras = {
            'push': {
                'notification': {"title": "Testing"},
            }
        }
        message = Message(name='test-name', data='test-data', extras=extras)
        await channel.publish(message)

        # Get the history for this channel
        history = await channel.history()
        message = history.items[0]
        assert message.name == 'test-name'
        assert message.data == 'test-data'
        assert message.extras == extras

    # RSL6a1
    async def test_interoperability(self):
        name = self.get_channel_name('persisted:interoperability_channel')
        channel = self.ably.channels[name]

        url = 'https://{}/channels/{}/messages'.format(self.test_vars["host"], name)
        key = self.test_vars['keys'][0]
        auth = (key['key_name'], key['key_secret'])

        type_mapping = {
            'string': str,
            'jsonObject': dict,
            'jsonArray': list,
            'binary': bytearray,
        }

        path = os.path.join(utils.get_submodule_dir(__file__), 'test-resources', 'messages-encoding.json')
        with open(path) as f:
            data = json.load(f)
            for input_msg in data['messages']:
                msg_data = input_msg['data']
                encoding = input_msg['encoding']
                expected_type = input_msg['expectedType']
                if expected_type == 'binary':
                    expected_value = input_msg.get('expectedHexValue')
                    expected_value = expected_value.encode('ascii')
                    expected_value = binascii.a2b_hex(expected_value)
                else:
                    expected_value = input_msg.get('expectedValue')

                # 1)
                await channel.publish(data=expected_value)

                async def check_data(encoding=encoding, msg_data=msg_data):
                    async with httpx.AsyncClient(http2=True) as client:
                        r = await client.get(url, auth=auth)
                        item = r.json()[0]
                        encoding_is_correct = item.get('encoding') == encoding
                        if encoding == 'json':
                            return encoding_is_correct and json.loads(item['data']) == json.loads(msg_data)
                        else:
                            return encoding_is_correct and item['data'] == msg_data

                await assert_waiter(check_data)

                # 2)
                await channel.publish(messages=[Message(data=msg_data, encoding=encoding)])

                async def check_history(expected_value=expected_value, expected_type=expected_type):
                    history = await channel.history()
                    message = history.items[0]
                    return message.data == expected_value and isinstance(message.data, type_mapping[expected_type])

                await assert_waiter(check_history)

    # https://github.com/ably/ably-python/issues/130
    async def test_publish_slash(self):
        channel = self.ably.channels.get(self.get_channel_name('persisted:widgets/'))
        name, data = 'Name', 'Data'
        await channel.publish(name, data)
        history = await channel.history()
        assert len(history.items) == 1
        assert history.items[0].name == name
        assert history.items[0].data == data

    # RSL1l
    @dont_vary_protocol
    async def test_publish_params(self):
        channel = self.ably.channels.get(self.get_channel_name())

        message = Message('name', 'data')
        with pytest.raises(AblyException) as excinfo:
            await channel.publish(message, {'_forceNack': True})

        assert 400 == excinfo.value.status_code
        assert 40099 == excinfo.value.code


class TestRestChannelPublishIdempotent(BaseAsyncTestCase, metaclass=VaryByProtocolTestsMetaclass):

    @pytest.fixture(autouse=True)
    async def setup(self):
        self.ably = await TestApp.get_ably_rest()
        self.ably_idempotent = await TestApp.get_ably_rest(idempotent_rest_publishing=True)
        yield
        await self.ably.close()
        await self.ably_idempotent.close()

    def per_protocol_setup(self, use_binary_protocol):
        self.ably.options.use_binary_protocol = use_binary_protocol
        self.use_binary_protocol = use_binary_protocol

    # TO3n
    @dont_vary_protocol
    async def test_idempotent_rest_publishing(self):
        # Test default value
        if api_version < '1.2':
            assert self.ably.options.idempotent_rest_publishing is False
        else:
            assert self.ably.options.idempotent_rest_publishing is True

        # Test setting value explicitly
        ably = await TestApp.get_ably_rest(idempotent_rest_publishing=True)
        assert ably.options.idempotent_rest_publishing is True
        await ably.close()

        ably = await TestApp.get_ably_rest(idempotent_rest_publishing=False)
        assert ably.options.idempotent_rest_publishing is False
        await ably.close()

    # RSL1j
    @dont_vary_protocol
    async def test_message_serialization(self):
        channel = self.get_channel()

        data = {
            'name': 'name',
            'data': 'data',
            'client_id': 'client_id',
            'extras': {},
            'id': 'foobar',
        }
        message = Message(**data)
        request_body = channel._Channel__publish_request_body(messages=[message])
        input_keys = {case.snake_to_camel(x) for x in data.keys()}
        assert input_keys - set(request_body) == set()

    # RSL1k1
    @dont_vary_protocol
    def test_idempotent_library_generated(self):
        channel = self.ably_idempotent.channels[self.get_channel_name()]

        message = Message('name', 'data')
        request_body = channel._Channel__publish_request_body(messages=[message])
        base_id, serial = request_body['id'].split(':')
        assert len(base64.b64decode(base_id)) >= 9
        assert serial == '0'

    # RSL1k2
    @dont_vary_protocol
    def test_idempotent_client_supplied(self):
        channel = self.ably_idempotent.channels[self.get_channel_name()]

        message = Message('name', 'data', id='foobar')
        request_body = channel._Channel__publish_request_body(messages=[message])
        assert request_body['id'] == 'foobar'

    # RSL1k3
    @dont_vary_protocol
    def test_idempotent_mixed_ids(self):
        channel = self.ably_idempotent.channels[self.get_channel_name()]

        messages = [
            Message('name', 'data', id='foobar'),
            Message('name', 'data'),
        ]
        request_body = channel._Channel__publish_request_body(messages=messages)
        assert request_body[0]['id'] == 'foobar'
        assert 'id' not in request_body[1]

    def get_ably_rest(self, *args, **kwargs):
        kwargs['use_binary_protocol'] = self.use_binary_protocol
        return TestApp.get_ably_rest(*args, **kwargs)

    # RSL1k4
    async def test_idempotent_library_generated_retry(self):
        test_vars = await TestApp.get_test_vars()
        ably = await self.get_ably_rest(idempotent_rest_publishing=True, fallback_hosts=[test_vars["host"]] * 3)
        channel = ably.channels[self.get_channel_name()]

        state = {'failures': 0}
        client = httpx.AsyncClient(http2=True)
        send = client.send

        async def side_effect(*args, **kwargs):
            x = await send(args[1])
            if state['failures'] < 2:
                state['failures'] += 1
                raise Exception('faked exception')
            return x

        messages = [Message('name1', 'data1')]
        with mock.patch('httpx.AsyncClient.send', side_effect=side_effect, autospec=True):
            await channel.publish(messages=messages)

        assert state['failures'] == 2
        history = await channel.history()
        assert len(history.items) == 1
        await client.aclose()
        await ably.close()

    # RSL1k5
    async def test_idempotent_client_supplied_publish(self):
        ably = await self.get_ably_rest(idempotent_rest_publishing=True)
        channel = ably.channels[self.get_channel_name()]

        messages = [Message('name1', 'data1', id='foobar')]
        await channel.publish(messages=messages)
        await channel.publish(messages=messages)
        await channel.publish(messages=messages)
        history = await channel.history()
        assert len(history.items) == 1
        await ably.close()
