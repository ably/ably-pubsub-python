import datetime
import json
import logging
from unittest.mock import patch

import pytest

from ably.pubsub.server import AblyException, Capability, create_http_client
from ably.pubsub.types.tokendetails import TokenDetails
from ably.pubsub.types.tokenrequest import TokenRequest
from test.ably.testapp import TestApp
from test.ably.utils import BaseAsyncTestCase, VaryByProtocolTestsMetaclass, dont_vary_protocol

log = logging.getLogger(__name__)


class TestHttpToken(BaseAsyncTestCase, metaclass=VaryByProtocolTestsMetaclass):

    async def server_time(self):
        return await self.ably.time()

    @pytest.fixture(autouse=True)
    async def setup(self):
        capability = {"*": ["*"]}
        self.permit_all = str(Capability(capability))
        self.ably = await TestApp.get_ably_rest()
        yield
        await self.ably.close()

    def per_protocol_setup(self, use_binary_protocol):
        self.ably.options.use_binary_protocol = use_binary_protocol
        self.use_binary_protocol = use_binary_protocol

    async def test_request_token_null_params(self):
        pre_time = await self.server_time()
        token_details = await self.ably.auth.request_token()
        post_time = await self.server_time()
        assert token_details.token is not None, "Expected token"
        assert token_details.issued + 300 >= pre_time, "Unexpected issued time"
        assert token_details.issued <= post_time + 500, "Unexpected issued time"
        assert self.permit_all == str(token_details.capability), "Unexpected capability"

    async def test_request_token_explicit_timestamp(self):
        pre_time = await self.server_time()
        token_details = await self.ably.auth.request_token(token_params={'timestamp': pre_time})
        post_time = await self.server_time()
        assert token_details.token is not None, "Expected token"
        assert token_details.issued + 300 >= pre_time, "Unexpected issued time"
        assert token_details.issued <= post_time, "Unexpected issued time"
        assert self.permit_all == str(Capability(token_details.capability)), "Unexpected Capability"

    async def test_request_token_explicit_invalid_timestamp(self):
        request_time = await self.server_time()
        explicit_timestamp = request_time - 30 * 60 * 1000

        with pytest.raises(AblyException):
            await self.ably.auth.request_token(token_params={'timestamp': explicit_timestamp})

    async def test_request_token_with_system_timestamp(self):
        pre_time = await self.server_time()
        token_details = await self.ably.auth.request_token(query_time=True)
        post_time = await self.server_time()
        assert token_details.token is not None, "Expected token"
        assert token_details.issued >= pre_time, "Unexpected issued time"
        assert token_details.issued <= post_time, "Unexpected issued time"
        assert self.permit_all == str(Capability(token_details.capability)), "Unexpected Capability"

    async def test_request_token_with_duplicate_nonce(self):
        request_time = await self.server_time()
        token_params = {
            'timestamp': request_time,
            'nonce': '1234567890123456'
        }
        token_details = await self.ably.auth.request_token(token_params)
        assert token_details.token is not None, "Expected token"

        with pytest.raises(AblyException):
            await self.ably.auth.request_token(token_params)

    async def test_request_token_with_capability_that_subsets_key_capability(self):
        capability = Capability({
            "onlythischannel": ["subscribe"]
        })

        token_details = await self.ably.auth.request_token(
            token_params={'capability': capability})

        assert token_details is not None
        assert token_details.token is not None
        assert capability == token_details.capability, "Unexpected capability"

    async def test_request_token_with_specified_key(self):
        test_vars = await TestApp.get_test_vars()
        key = test_vars["keys"][1]
        token_details = await self.ably.auth.request_token(
            key_name=key["key_name"], key_secret=key["key_secret"])
        assert token_details.token is not None, "Expected token"
        assert key.get("capability") == token_details.capability, "Unexpected capability"

    @dont_vary_protocol
    async def test_request_token_with_invalid_mac(self):
        with pytest.raises(AblyException):
            await self.ably.auth.request_token(token_params={'mac': "thisisnotavalidmac"})

    async def test_request_token_with_specified_ttl(self):
        token_details = await self.ably.auth.request_token(token_params={'ttl': 100})
        assert token_details.token is not None, "Expected token"
        assert token_details.issued + 100 == token_details.expires, "Unexpected expires"

    @dont_vary_protocol
    async def test_token_with_excessive_ttl(self):
        excessive_ttl = 365 * 24 * 60 * 60 * 1000
        with pytest.raises(AblyException):
            await self.ably.auth.request_token(token_params={'ttl': excessive_ttl})

    @dont_vary_protocol
    async def test_token_generation_with_invalid_ttl(self):
        with pytest.raises(AblyException):
            await self.ably.auth.request_token(token_params={'ttl': -1})

    async def test_token_generation_with_local_time(self):
        timestamp = self.ably.auth._timestamp
        with patch('ably.pubsub.http.http.AblyHttp.time', wraps=self.ably.time) as server_time,\
                patch('ably.pubsub.http.auth.Auth._timestamp', wraps=timestamp) as local_time:
            await self.ably.auth.request_token()
            assert local_time.called
            assert not server_time.called

    # RSA10k
    async def test_token_generation_with_server_time(self):
        timestamp = self.ably.auth._timestamp
        with patch('ably.pubsub.http.http.AblyHttp.time', wraps=self.ably.time) as server_time,\
                patch('ably.pubsub.http.auth.Auth._timestamp', wraps=timestamp) as local_time:
            await self.ably.auth.request_token(query_time=True)
            assert local_time.call_count == 1
            assert server_time.call_count == 1
            await self.ably.auth.request_token(query_time=True)
            assert local_time.call_count == 2
            assert server_time.call_count == 1

    # TD7
    async def test_toke_details_from_json(self):
        token_details = await self.ably.auth.request_token()
        token_details_dict = token_details.to_dict()
        token_details_str = json.dumps(token_details_dict)

        assert token_details == TokenDetails.from_json(token_details_dict)
        assert token_details == TokenDetails.from_json(token_details_str)

    # Issue #71
    @dont_vary_protocol
    async def test_request_token_float_and_timedelta(self):
        lifetime = datetime.timedelta(hours=4)
        await self.ably.auth.request_token({'ttl': lifetime.total_seconds() * 1000})
        await self.ably.auth.request_token({'ttl': lifetime})


class TestCreateTokenRequest(BaseAsyncTestCase, metaclass=VaryByProtocolTestsMetaclass):

    @pytest.fixture(autouse=True)
    async def setup(self):
        self.ably = await TestApp.get_ably_rest()
        self.key_name = self.ably.options.key_name
        self.key_secret = self.ably.options.key_secret
        yield
        await self.ably.close()

    def per_protocol_setup(self, use_binary_protocol):
        self.ably.options.use_binary_protocol = use_binary_protocol
        self.use_binary_protocol = use_binary_protocol

    @dont_vary_protocol
    async def test_key_name_and_secret_are_required(self):
        ably = await TestApp.get_ably_rest(key=None, token='not a real token')
        with pytest.raises(AblyException, match="40101 401 No key specified"):
            await ably.auth.create_token_request()
        with pytest.raises(AblyException, match="40101 401 No key specified"):
            await ably.auth.create_token_request(key_name=self.key_name)
        with pytest.raises(AblyException, match="40101 401 No key specified"):
            await ably.auth.create_token_request(key_secret=self.key_secret)

    @dont_vary_protocol
    async def test_with_local_time(self):
        timestamp = self.ably.auth._timestamp
        with patch('ably.pubsub.http.http.AblyHttp.time', wraps=self.ably.time) as server_time,\
                patch('ably.pubsub.http.auth.Auth._timestamp', wraps=timestamp) as local_time:
            await self.ably.auth.create_token_request(
                key_name=self.key_name, key_secret=self.key_secret, query_time=False)
            assert local_time.called
            assert not server_time.called

    # RSA10k
    @dont_vary_protocol
    async def test_with_server_time(self):
        timestamp = self.ably.auth._timestamp
        with patch('ably.pubsub.http.http.AblyHttp.time', wraps=self.ably.time) as server_time,\
                patch('ably.pubsub.http.auth.Auth._timestamp', wraps=timestamp) as local_time:
            await self.ably.auth.create_token_request(
                key_name=self.key_name, key_secret=self.key_secret, query_time=True)
            assert local_time.call_count == 1
            assert server_time.call_count == 1
            await self.ably.auth.create_token_request(
                key_name=self.key_name, key_secret=self.key_secret, query_time=True)
            assert local_time.call_count == 2
            assert server_time.call_count == 1

    async def test_token_request_can_be_used_to_get_a_token(self):
        token_request = await self.ably.auth.create_token_request(
            key_name=self.key_name, key_secret=self.key_secret)
        assert isinstance(token_request, TokenRequest)

        async def auth_callback(token_params):
            return token_request

        ably = await TestApp.get_ably_rest(key=None,
                                           auth_callback=auth_callback,
                                           use_binary_protocol=self.use_binary_protocol)

        token = await ably.auth.authorize()
        assert isinstance(token, TokenDetails)
        await ably.close()

    async def test_token_request_dict_can_be_used_to_get_a_token(self):
        token_request = await self.ably.auth.create_token_request(
            key_name=self.key_name, key_secret=self.key_secret)
        assert isinstance(token_request, TokenRequest)

        async def auth_callback(token_params):
            return token_request.to_dict()

        ably = await TestApp.get_ably_rest(key=None,
                                           auth_callback=auth_callback,
                                           use_binary_protocol=self.use_binary_protocol)

        token = await ably.auth.authorize()
        assert isinstance(token, TokenDetails)
        await ably.close()

    # TE6
    @dont_vary_protocol
    async def test_token_request_from_json(self):
        token_request = await self.ably.auth.create_token_request(
            key_name=self.key_name, key_secret=self.key_secret)
        assert isinstance(token_request, TokenRequest)

        token_request_dict = token_request.to_dict()
        assert token_request == TokenRequest.from_json(token_request_dict)

        token_request_str = json.dumps(token_request_dict)
        assert token_request == TokenRequest.from_json(token_request_str)

    @dont_vary_protocol
    async def test_nonce_is_random_and_longer_than_15_characters(self):
        token_request = await self.ably.auth.create_token_request(
            key_name=self.key_name, key_secret=self.key_secret)
        assert len(token_request.nonce) > 15

        another_token_request = await self.ably.auth.create_token_request(
            key_name=self.key_name, key_secret=self.key_secret)
        assert len(another_token_request.nonce) > 15

        assert token_request.nonce != another_token_request.nonce

    # RSA5
    @dont_vary_protocol
    async def test_ttl_is_optional_and_specified_in_ms(self):
        token_request = await self.ably.auth.create_token_request(
            key_name=self.key_name, key_secret=self.key_secret)
        assert token_request.ttl is None

    # RSA6
    @dont_vary_protocol
    async def test_capability_is_optional(self):
        token_request = await self.ably.auth.create_token_request(
            key_name=self.key_name, key_secret=self.key_secret)
        assert token_request.capability is None

    @dont_vary_protocol
    async def test_accept_all_token_params(self):
        token_params = {
            'ttl': 1000,
            'capability': Capability({'channel': ['publish']}),
            'client_id': 'a_id',
            'timestamp': 1000,
            'nonce': 'a_nonce',
        }
        token_request = await self.ably.auth.create_token_request(
            token_params,
            key_name=self.key_name, key_secret=self.key_secret,
        )
        assert token_request.ttl == token_params['ttl']
        assert token_request.capability == str(token_params['capability'])
        assert token_request.client_id == token_params['client_id']
        assert token_request.timestamp == token_params['timestamp']
        assert token_request.nonce == token_params['nonce']

    async def test_capability(self):
        capability = Capability({'channel': ['publish']})
        token_request = await self.ably.auth.create_token_request(
            key_name=self.key_name, key_secret=self.key_secret,
            token_params={'capability': capability})
        assert token_request.capability == str(capability)

        async def auth_callback(token_params):
            return token_request

        ably = await TestApp.get_ably_rest(key=None, auth_callback=auth_callback,
                                           use_binary_protocol=self.use_binary_protocol)

        token = await ably.auth.authorize()

        assert str(token.capability) == str(capability)
        await ably.close()

    @dont_vary_protocol
    async def test_hmac(self):
        ably = create_http_client(key_name='a_key_name', key_secret='a_secret')
        token_params = {
            'ttl': 1000,
            'nonce': 'abcde100',
            'client_id': 'a_id',
            'timestamp': 1000,
        }
        token_request = await ably.auth.create_token_request(
            token_params, key_secret='a_secret', key_name='a_key_name')
        assert token_request.mac == 'sYkCH0Un+WgzI7/Nhy0BoQIKq9HmjKynCRs4E3qAbGQ='
        await ably.close()

    # AO2g
    @dont_vary_protocol
    async def test_query_server_time(self):
        with patch('ably.pubsub.http.http.AblyHttp.time', wraps=self.ably.time) as server_time:
            await self.ably.auth.create_token_request(
                key_name=self.key_name, key_secret=self.key_secret, query_time=True)
            assert server_time.call_count == 1

            await self.ably.auth.create_token_request(
                key_name=self.key_name, key_secret=self.key_secret, query_time=False)
            assert server_time.call_count == 1
