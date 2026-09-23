import httpx
import pytest
import respx

from ably import AblyRest
from ably.http.paginatedresult import HttpPaginatedResponse
from ably.transport.defaults import Defaults
from test.ably.testapp import TestApp
from test.ably.utils import BaseAsyncTestCase, VaryByProtocolTestsMetaclass, dont_vary_protocol


# RSC19
class TestRestRequest(BaseAsyncTestCase, metaclass=VaryByProtocolTestsMetaclass):

    @pytest.fixture(autouse=True)
    async def setup(self):
        self.ably = await TestApp.get_ably_rest()
        self.test_vars = await TestApp.get_test_vars()

        self.channel = self.get_channel_name()
        self.path = f'/channels/{self.channel}/messages'
        yield
        await self.ably.close()

    async def publish_messages(self, count):
        for i in range(count):
            body = {'name': f'event{i}', 'data': f'lorem ipsum {i}'}
            await self.ably.request('POST', self.path, body=body, version=Defaults.protocol_version)

    def per_protocol_setup(self, use_binary_protocol):
        self.ably.options.use_binary_protocol = use_binary_protocol
        self.use_binary_protocol = use_binary_protocol

    async def test_post(self):
        body = {'name': 'test-post', 'data': 'lorem ipsum'}
        result = await self.ably.request('POST', self.path, body=body, version=Defaults.protocol_version)

        assert isinstance(result, HttpPaginatedResponse)  # RSC19d
        # HP3
        assert type(result.items) is list
        assert len(result.items) == 1
        assert result.items[0]['channel'] == self.channel
        assert 'messageId' in result.items[0]

    async def test_get(self):
        # Paging is exercised below, so the channel needs more messages than one page holds
        await self.publish_messages(20)

        params = {'limit': 10, 'direction': 'forwards'}
        result = await self.ably.request('GET', self.path, params=params, version=Defaults.protocol_version)

        assert isinstance(result, HttpPaginatedResponse)  # RSC19d

        # HP2
        assert isinstance(await result.next(), HttpPaginatedResponse)
        assert isinstance(await result.first(), HttpPaginatedResponse)

        # HP3
        assert isinstance(result.items, list)
        item = result.items[0]
        assert isinstance(item, dict)
        assert 'timestamp' in item
        assert 'id' in item
        assert item['name'] == 'event0'
        assert item['data'] == 'lorem ipsum 0'

        assert result.status_code == 200     # HP4
        assert result.success is True        # HP5
        assert result.error_code is None     # HP6
        assert result.error_message is None  # HP7
        assert isinstance(result.headers, list)   # HP7

    @dont_vary_protocol
    async def test_not_found(self):
        result = await self.ably.request('GET', '/not-found', version=Defaults.protocol_version)
        assert isinstance(result, HttpPaginatedResponse)  # RSC19d
        assert result.status_code == 404             # HP4
        assert result.success is False               # HP5

    @dont_vary_protocol
    async def test_error(self):
        params = {'limit': 'abc'}
        result = await self.ably.request('GET', self.path, params=params, version=Defaults.protocol_version)
        assert isinstance(result, HttpPaginatedResponse)  # RSC19d
        assert result.status_code == 400  # HP4
        assert not result.success
        assert result.error_code
        assert result.error_message

    async def test_headers(self):
        key = 'X-Test'
        value = 'lorem ipsum'
        result = await self.ably.request('GET', '/time', headers={key: value}, version=Defaults.protocol_version)
        assert result.response.request.headers[key] == value

    # RSC19e
    @dont_vary_protocol
    async def test_timeout(self):
        # Timeout
        timeout = 0.000001
        ably = AblyRest(token="foo", http_request_timeout=timeout)
        assert ably.http.http_request_timeout == timeout
        with pytest.raises(httpx.ReadTimeout):
            await ably.request('GET', '/time', version=Defaults.protocol_version)
        await ably.close()

        default_endpoint = 'https://sandbox.realtime.ably-nonprod.net/time'
        fallback_host = 'sandbox.a.fallback.ably-realtime-nonprod.com'
        fallback_endpoint = f'https://{fallback_host}/time'
        ably = await TestApp.get_ably_rest(fallback_hosts=[fallback_host])
        with respx.mock:
            default_route = respx.get(default_endpoint)
            fallback_route = respx.get(fallback_endpoint)
            headers = {
                "Content-Type": "application/json"
            }
            default_route.side_effect = httpx.ConnectError('')
            fallback_route.return_value = httpx.Response(200, headers=headers, text='[123]')
            await ably.request('GET', '/time', version=Defaults.protocol_version)
        await ably.close()

        # Bad host, no Fallback
        ably = AblyRest(key=self.test_vars["keys"][0]["key_str"],
                        endpoint='some.other.host',
                        port=self.test_vars["port"],
                        tls_port=self.test_vars["tls_port"],
                        tls=self.test_vars["tls"])
        with pytest.raises(httpx.ConnectError):
            await ably.request('GET', '/time', version=Defaults.protocol_version)
        await ably.close()

    # RSC15l3
    @dont_vary_protocol
    async def test_503_status_fallback(self):
        default_endpoint = 'https://sandbox.realtime.ably-nonprod.net/time'
        fallback_host = 'sandbox.a.fallback.ably-realtime-nonprod.com'
        fallback_endpoint = f'https://{fallback_host}/time'
        ably = await TestApp.get_ably_rest(fallback_hosts=[fallback_host])
        with respx.mock:
            default_route = respx.get(default_endpoint)
            fallback_route = respx.get(fallback_endpoint)
            headers = {
                "Content-Type": "application/json"
            }
            default_route.return_value = httpx.Response(503, headers=headers)
            fallback_route.return_value = httpx.Response(200, headers=headers, text='[123]')
            result = await ably.request('GET', '/time', version=Defaults.protocol_version)
            assert default_route.called
            assert result.status_code == 200
            assert result.items[0] == 123
        await ably.close()

    # RSC15l2
    @dont_vary_protocol
    async def test_httpx_timeout_fallback(self):
        default_endpoint = 'https://sandbox.realtime.ably-nonprod.net/time'
        fallback_host = 'sandbox.a.fallback.ably-realtime-nonprod.com'
        fallback_endpoint = f'https://{fallback_host}/time'
        ably = await TestApp.get_ably_rest(fallback_hosts=[fallback_host])
        with respx.mock:
            default_route = respx.get(default_endpoint)
            fallback_route = respx.get(fallback_endpoint)
            headers = {
                "Content-Type": "application/json"
            }
            default_route.side_effect = httpx.ReadTimeout
            fallback_route.return_value = httpx.Response(200, headers=headers, text='[123]')
            result = await ably.request('GET', '/time', version=Defaults.protocol_version)
            assert default_route.called
            assert result.status_code == 200
            assert result.items[0] == 123
        await ably.close()

    # RSC15l3
    @dont_vary_protocol
    async def test_503_status_fallback_on_publish(self):
        default_endpoint = 'https://sandbox.realtime.ably-nonprod.net/channels/test/messages'
        fallback_host = 'sandbox.a.fallback.ably-realtime-nonprod.com'
        fallback_endpoint = f'https://{fallback_host}/channels/test/messages'

        fallback_response_text = (
            '{"id": "unique_id:0", "channel": "test", "name": "test", "data": "data", '
            '"clientId": null, "connectionId": "connection_id", "timestamp": 1696944145000, '
            '"encoding": null}'
        )

        ably = await TestApp.get_ably_rest(fallback_hosts=[fallback_host])
        with respx.mock:
            default_route = respx.post(default_endpoint)
            fallback_route = respx.post(fallback_endpoint)
            headers = {
                "Content-Type": "application/json"
            }
            default_route.return_value = httpx.Response(503, headers=headers)
            fallback_route.return_value = httpx.Response(
                200,
                headers=headers,
                text=fallback_response_text,
            )
            await ably.channels['test'].publish('test', 'data')
            assert default_route.called
        await ably.close()

    # RSC15l4
    @dont_vary_protocol
    async def test_400_cloudfront_fallback(self):
        default_endpoint = 'https://sandbox.realtime.ably-nonprod.net/time'
        fallback_host = 'sandbox.a.fallback.ably-realtime-nonprod.com'
        fallback_endpoint = f'https://{fallback_host}/time'
        ably = await TestApp.get_ably_rest(fallback_hosts=[fallback_host])
        with respx.mock:
            default_route = respx.get(default_endpoint)
            fallback_route = respx.get(fallback_endpoint)
            headers = {
                "Server": "CloudFront",
                "Content-Type": "application/json",
            }
            default_route.return_value = httpx.Response(400, headers=headers, text='[456]')
            fallback_route.return_value = httpx.Response(200, headers=headers, text='[123]')
            result = await ably.request('GET', '/time', version=Defaults.protocol_version)
            assert default_route.called
            assert result.status_code == 200
            assert result.items[0] == 123
        await ably.close()

    async def test_version(self):
        version = "150"  # chosen arbitrarily
        result = await self.ably.request('GET', '/time', "150")
        assert result.response.request.headers["X-Ably-Version"] == version
