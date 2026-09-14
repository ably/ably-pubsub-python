import pytest

from ably.pubsub.types.capability import Capability
from ably.pubsub.util.exceptions import AblyException
from test.ably.testapp import TestApp
from test.ably.utils import BaseAsyncTestCase, VaryByProtocolTestsMetaclass, dont_vary_protocol


class TestRestCapability(BaseAsyncTestCase, metaclass=VaryByProtocolTestsMetaclass):

    @pytest.fixture(autouse=True)
    async def setup(self):
        self.test_vars = await TestApp.get_test_vars()
        self.ably = await TestApp.get_ably_rest()
        yield
        await self.ably.close()

    def per_protocol_setup(self, use_binary_protocol):
        self.ably.options.use_binary_protocol = use_binary_protocol

    async def test_blanket_intersection_with_key(self):
        key = self.test_vars['keys'][1]
        token_details = await self.ably.auth.request_token(key_name=key['key_name'], key_secret=key['key_secret'])
        expected_capability = Capability(key["capability"])
        assert token_details.token is not None, "Expected token"
        assert expected_capability == token_details.capability, "Unexpected capability."

    async def test_equal_intersection_with_key(self):
        key = self.test_vars['keys'][1]

        token_details = await self.ably.auth.request_token(
            key_name=key['key_name'],
            key_secret=key['key_secret'],
            token_params={'capability': key['capability']})

        expected_capability = Capability(key["capability"])

        assert token_details.token is not None, "Expected token"
        assert expected_capability == token_details.capability, "Unexpected capability"

    @dont_vary_protocol
    async def test_empty_ops_intersection(self):
        key = self.test_vars['keys'][1]
        with pytest.raises(AblyException):
            await self.ably.auth.request_token(
                key_name=key['key_name'],
                key_secret=key['key_secret'],
                token_params={'capability': {'testchannel': ['subscribe']}})

    @dont_vary_protocol
    async def test_empty_paths_intersection(self):
        key = self.test_vars['keys'][1]
        with pytest.raises(AblyException):
            await self.ably.auth.request_token(
                key_name=key['key_name'],
                key_secret=key['key_secret'],
                token_params={'capability': {"testchannelx": ["publish"]}})

    async def test_non_empty_ops_intersection(self):
        key = self.test_vars['keys'][4]

        token_params = {"capability": {
            "channel2": ["presence", "subscribe"]
        }}
        kwargs = {
            "key_name": key["key_name"],
            "key_secret": key["key_secret"],
        }

        expected_capability = Capability({
            "channel2": ["subscribe"]
        })

        token_details = await self.ably.auth.request_token(token_params, **kwargs)

        assert token_details.token is not None, "Expected token"
        assert expected_capability == token_details.capability, "Unexpected capability"

    async def test_non_empty_paths_intersection(self):
        key = self.test_vars['keys'][4]
        token_params = {
            "capability": {
                "channel2": ["presence", "subscribe"],
                "channelx": ["presence", "subscribe"],
            }
        }
        kwargs = {
            "key_name": key["key_name"],

            "key_secret": key["key_secret"]
        }

        expected_capability = Capability({
            "channel2": ["subscribe"]
        })

        token_details = await self.ably.auth.request_token(token_params, **kwargs)

        assert token_details.token is not None, "Expected token"
        assert expected_capability == token_details.capability, "Unexpected capability"

    async def test_wildcard_ops_intersection(self):
        key = self.test_vars['keys'][4]

        token_params = {
            "capability": {
                "channel2": ["*"],
            },
        }
        kwargs = {
            "key_name": key["key_name"],
            "key_secret": key["key_secret"],
        }

        expected_capability = Capability({
            "channel2": ["subscribe", "publish"]
        })

        token_details = await self.ably.auth.request_token(token_params, **kwargs)

        assert token_details.token is not None, "Expected token"
        assert expected_capability == token_details.capability, "Unexpected capability"

    async def test_wildcard_ops_intersection_2(self):
        key = self.test_vars['keys'][4]

        token_params = {
            "capability": {
                "channel6": ["publish", "subscribe"],
            },
        }
        kwargs = {
            "key_name": key["key_name"],
            "key_secret": key["key_secret"],
        }

        expected_capability = Capability({
            "channel6": ["subscribe", "publish"]
        })

        token_details = await self.ably.auth.request_token(token_params, **kwargs)

        assert token_details.token is not None, "Expected token"
        assert expected_capability == token_details.capability, "Unexpected capability"

    async def test_wildcard_resources_intersection(self):
        key = self.test_vars['keys'][2]

        token_params = {
            "capability": {
                "cansubscribe": ["subscribe"],
            },
        }
        kwargs = {
            "key_name": key["key_name"],
            "key_secret": key["key_secret"],
        }

        expected_capability = Capability({
            "cansubscribe": ["subscribe"]
        })

        token_details = await self.ably.auth.request_token(token_params, **kwargs)

        assert token_details.token is not None, "Expected token"
        assert expected_capability == token_details.capability, "Unexpected capability"

    async def test_wildcard_resources_intersection_2(self):
        key = self.test_vars['keys'][2]

        token_params = {
            "capability": {
                "cansubscribe:check": ["subscribe"],
            },
        }
        kwargs = {
            "key_name": key["key_name"],
            "key_secret": key["key_secret"],
        }

        expected_capability = Capability({
            "cansubscribe:check": ["subscribe"]
        })

        token_details = await self.ably.auth.request_token(token_params, **kwargs)

        assert token_details.token is not None, "Expected token"
        assert expected_capability == token_details.capability, "Unexpected capability"

    async def test_wildcard_resources_intersection_3(self):
        key = self.test_vars['keys'][2]

        token_params = {
            "capability": {
                "cansubscribe:*": ["subscribe"],
            },
        }
        kwargs = {
            "key_name": key["key_name"],
            "key_secret": key["key_secret"],

        }

        expected_capability = Capability({
            "cansubscribe:*": ["subscribe"]
        })

        token_details = await self.ably.auth.request_token(token_params, **kwargs)

        assert token_details.token is not None, "Expected token"
        assert expected_capability == token_details.capability, "Unexpected capability"

    @dont_vary_protocol
    async def test_invalid_capabilities(self):
        with pytest.raises(AblyException) as excinfo:
            await self.ably.auth.request_token(
                token_params={'capability': {"channel0": ["publish_"]}})

        the_exception = excinfo.value
        assert 400 == the_exception.status_code
        assert 40000 == the_exception.code

    @dont_vary_protocol
    async def test_invalid_capabilities_2(self):
        with pytest.raises(AblyException) as excinfo:
            await self.ably.auth.request_token(
                token_params={'capability': {"channel0": ["*", "publish"]}})

        the_exception = excinfo.value
        assert 400 == the_exception.status_code
        assert 40000 == the_exception.code

    @dont_vary_protocol
    async def test_invalid_capabilities_3(self):
        with pytest.raises(AblyException) as excinfo:
            await self.ably.auth.request_token(
                token_params={'capability': {"channel0": []}})

        the_exception = excinfo.value
        assert 400 == the_exception.status_code
        assert 40000 == the_exception.code

    @dont_vary_protocol
    def test_capability_from_string(self):
        capability_from_str = Capability('{"cansubscribe":["subscribe"]}')
        capability_from_str_single_quote = Capability('{\'cansubscribe\':[\'subscribe\']}')

        capability_from_dict = Capability({
            "cansubscribe": ["subscribe"]
        })

        assert capability_from_str == capability_from_dict, "Unexpected Capability constructed from string"
        assert (
            capability_from_str_single_quote == capability_from_dict
        ), "Unexpected Capability constructed from string"
