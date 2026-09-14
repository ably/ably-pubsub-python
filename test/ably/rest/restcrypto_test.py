import base64
import json
import logging
import os

import pytest
from Crypto import Random

from ably.pubsub.server import AblyException
from ably.pubsub.types.message import Message
from ably.pubsub.util.crypto import CipherParams, generate_random_key, get_cipher, get_default_params
from test.ably import utils
from test.ably.testapp import TestApp
from test.ably.utils import BaseAsyncTestCase, BaseTestCase, VaryByProtocolTestsMetaclass, dont_vary_protocol

log = logging.getLogger(__name__)


class TestRestCrypto(BaseAsyncTestCase, metaclass=VaryByProtocolTestsMetaclass):

    @pytest.fixture(autouse=True)
    async def setup(self):
        self.test_vars = await TestApp.get_test_vars()
        self.ably = await TestApp.get_ably_rest()
        self.ably2 = await TestApp.get_ably_rest()
        yield
        await self.ably.close()
        await self.ably2.close()

    def per_protocol_setup(self, use_binary_protocol):
        # This will be called every test that vary by protocol for each protocol
        self.ably.options.use_binary_protocol = use_binary_protocol
        self.ably2.options.use_binary_protocol = use_binary_protocol
        self.use_binary_protocol = use_binary_protocol

    @dont_vary_protocol
    def test_cbc_channel_cipher(self):
        key = (
            b'\x93\xe3\x5c\xc9\x77\x53\xfd\x1a'
            b'\x79\xb4\xd8\x84\xe7\xdc\xfd\xdf')

        iv = (
            b'\x28\x4c\xe4\x8d\x4b\xdc\x9d\x42'
            b'\x8a\x77\x6b\x53\x2d\xc7\xb5\xc0')

        log.debug(f"KEY_LEN: {len(key)}")
        log.debug(f"IV_LEN: {len(iv)}")
        cipher = get_cipher({'key': key, 'iv': iv})

        plaintext = b"The quick brown fox"
        expected_ciphertext = (
            b'\x28\x4c\xe4\x8d\x4b\xdc\x9d\x42'
            b'\x8a\x77\x6b\x53\x2d\xc7\xb5\xc0'
            b'\x83\x5c\xcf\xce\x0c\xfd\xbe\x37'
            b'\xb7\x92\x12\x04\x1d\x45\x68\xa4'
            b'\xdf\x7f\x6e\x38\x17\x4a\xff\x50'
            b'\x73\x23\xbb\xca\x16\xb0\xe2\x84')

        actual_ciphertext = cipher.encrypt(plaintext)

        assert expected_ciphertext == actual_ciphertext

    async def test_crypto_publish(self):
        channel_name = self.get_channel_name('persisted:crypto_publish_text')
        publish0 = self.ably.channels.get(channel_name, cipher={'key': generate_random_key()})

        await publish0.publish("publish3", "This is a string message payload")
        await publish0.publish("publish4", b"This is a byte[] message payload")
        await publish0.publish("publish5", {"test": "This is a JSONObject message payload"})
        await publish0.publish("publish6", ["This is a JSONArray message payload"])

        history = await publish0.history()
        messages = history.items
        assert messages is not None, "Expected non-None messages"
        assert 4 == len(messages), "Expected 4 messages"

        message_contents = {m.name: m.data for m in messages}
        log.debug(f"message_contents: {str(message_contents)}")

        assert "This is a string message payload" == message_contents["publish3"],\
               "Expect publish3 to be expected String)"

        assert b"This is a byte[] message payload" == message_contents["publish4"],\
               "Expect publish4 to be expected byte[]. Actual: {}".format(str(message_contents['publish4']))

        assert {"test": "This is a JSONObject message payload"} == message_contents["publish5"],\
               "Expect publish5 to be expected JSONObject"

        assert ["This is a JSONArray message payload"] == message_contents["publish6"],\
               "Expect publish6 to be expected JSONObject"

    async def test_crypto_publish_256(self):
        rndfile = Random.new()
        key = rndfile.read(32)
        channel_name = 'persisted:crypto_publish_text_256'
        channel_name += '_bin' if self.use_binary_protocol else '_text'

        publish0 = self.ably.channels.get(channel_name, cipher={'key': key})

        await publish0.publish("publish3", "This is a string message payload")
        await publish0.publish("publish4", b"This is a byte[] message payload")
        await publish0.publish("publish5", {"test": "This is a JSONObject message payload"})
        await publish0.publish("publish6", ["This is a JSONArray message payload"])

        history = await publish0.history()
        messages = history.items
        assert messages is not None, "Expected non-None messages"
        assert 4 == len(messages), "Expected 4 messages"

        message_contents = {m.name: m.data for m in messages}
        log.debug(f"message_contents: {str(message_contents)}")

        assert "This is a string message payload" == message_contents["publish3"],\
               "Expect publish3 to be expected String)"

        assert b"This is a byte[] message payload" == message_contents["publish4"],\
               "Expect publish4 to be expected byte[]. Actual: {}".format(str(message_contents['publish4']))

        assert {"test": "This is a JSONObject message payload"} == message_contents["publish5"],\
               "Expect publish5 to be expected JSONObject"

        assert ["This is a JSONArray message payload"] == message_contents["publish6"],\
               "Expect publish6 to be expected JSONObject"

    async def test_crypto_publish_key_mismatch(self):
        channel_name = self.get_channel_name('persisted:crypto_publish_key_mismatch')

        publish0 = self.ably.channels.get(channel_name, cipher={'key': generate_random_key()})

        await publish0.publish("publish3", "This is a string message payload")
        await publish0.publish("publish4", b"This is a byte[] message payload")
        await publish0.publish("publish5", {"test": "This is a JSONObject message payload"})
        await publish0.publish("publish6", ["This is a JSONArray message payload"])

        rx_channel = self.ably2.channels.get(channel_name, cipher={'key': generate_random_key()})

        with pytest.raises(AblyException) as excinfo:
            await rx_channel.history()

        message = excinfo.value.message
        assert 'invalid-padding' == message or "codec can't decode" in message

    async def test_crypto_send_unencrypted(self):
        channel_name = self.get_channel_name('persisted:crypto_send_unencrypted')
        publish0 = self.ably.channels[channel_name]

        await publish0.publish("publish3", "This is a string message payload")
        await publish0.publish("publish4", b"This is a byte[] message payload")
        await publish0.publish("publish5", {"test": "This is a JSONObject message payload"})
        await publish0.publish("publish6", ["This is a JSONArray message payload"])

        rx_channel = self.ably2.channels.get(channel_name, cipher={'key': generate_random_key()})

        history = await rx_channel.history()
        messages = history.items
        assert messages is not None, "Expected non-None messages"
        assert 4 == len(messages), "Expected 4 messages"

        message_contents = {m.name: m.data for m in messages}
        log.debug(f"message_contents: {str(message_contents)}")

        assert "This is a string message payload" == message_contents["publish3"],\
               "Expect publish3 to be expected String"

        assert b"This is a byte[] message payload" == message_contents["publish4"],\
               "Expect publish4 to be expected byte[]. Actual: {}".format(str(message_contents['publish4']))

        assert {"test": "This is a JSONObject message payload"} == message_contents["publish5"],\
               "Expect publish5 to be expected JSONObject"

        assert ["This is a JSONArray message payload"] == message_contents["publish6"],\
               "Expect publish6 to be expected JSONObject"

    async def test_crypto_encrypted_unhandled(self):
        channel_name = self.get_channel_name('persisted:crypto_send_encrypted_unhandled')
        key = b'0123456789abcdef'
        data = 'foobar'
        publish0 = self.ably.channels.get(channel_name, cipher={'key': key})

        await publish0.publish("publish0", data)

        rx_channel = self.ably2.channels[channel_name]
        history = await rx_channel.history()
        message = history.items[0]
        cipher = get_cipher(get_default_params({'key': key}))
        assert cipher.decrypt(message.data).decode() == data
        assert message.encoding == 'utf-8/cipher+aes-128-cbc'

    @dont_vary_protocol
    def test_cipher_params(self):
        params = CipherParams(secret_key='0123456789abcdef')
        assert params.algorithm == 'AES'
        assert params.mode == 'CBC'
        assert params.key_length == 128

        params = CipherParams(secret_key='0123456789abcdef' * 2)
        assert params.algorithm == 'AES'
        assert params.mode == 'CBC'
        assert params.key_length == 256


class AbstractTestCryptoWithFixture:

    @pytest.fixture(autouse=True)
    def setUpClass(self):
        resources_path = os.path.join(utils.get_submodule_dir(__file__), 'test-resources', self.fixture_file)
        with open(resources_path) as f:
            self.fixture = json.loads(f.read())
            self.params = {
                'secret_key': base64.b64decode(self.fixture['key'].encode('ascii')),
                'mode': self.fixture['mode'],
                'algorithm': self.fixture['algorithm'],
                'iv': base64.b64decode(self.fixture['iv'].encode('ascii')),
            }
            self.cipher_params = CipherParams(**self.params)
            self.cipher = get_cipher(self.cipher_params)
            self.items = self.fixture['items']

    def get_encoded(self, encoded_item):
        if encoded_item.get('encoding') == 'base64':
            return base64.b64decode(encoded_item['data'].encode('ascii'))
        elif encoded_item.get('encoding') == 'json':
            return json.loads(encoded_item['data'])
        return encoded_item['data']

    # TM3
    def test_decode(self):
        for item in self.items:
            assert item['encoded']['name'] == item['encrypted']['name']
            message = Message.from_encoded(item['encrypted'], self.cipher)
            assert message.encoding == ''
            expected_data = self.get_encoded(item['encoded'])
            assert expected_data == message.data

    # TM3
    def test_decode_array(self):
        items_encrypted = [item['encrypted'] for item in self.items]
        messages = Message.from_encoded_array(items_encrypted, self.cipher)
        for i, message in enumerate(messages):
            assert message.encoding == ''
            expected_data = self.get_encoded(self.items[i]['encoded'])
            assert expected_data == message.data

    def test_encode(self):
        for item in self.items:
            # need to reset iv
            self.cipher_params = CipherParams(**self.params)
            self.cipher = get_cipher(self.cipher_params)
            data = self.get_encoded(item['encoded'])
            expected = item['encrypted']
            message = Message(item['encoded']['name'], data)
            message.encrypt(self.cipher)
            as_dict = message.as_dict()
            assert as_dict['data'] == expected['data']
            assert as_dict['encoding'] == expected['encoding']


class TestCryptoWithFixture128(AbstractTestCryptoWithFixture, BaseTestCase):
    fixture_file = 'crypto-data-128.json'


class TestCryptoWithFixture256(AbstractTestCryptoWithFixture, BaseTestCase):
    fixture_file = 'crypto-data-256.json'
