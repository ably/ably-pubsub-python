import pytest
import respx
from httpx import Response

from ably.pubsub.request.paginatedresult import PaginatedResult
from test.ably.testapp import TestApp
from test.ably.utils import BaseAsyncTestCase


class TestPaginatedResult(BaseAsyncTestCase):

    def get_response_callback(self, headers, body, status):
        def callback(request):
            res = request.url.params.get('page')
            if res:
                return Response(
                    status_code=status,
                    headers=headers,
                    content=f'[{{"page": {int(res)}}}]'
                )

            return Response(
                status_code=status,
                headers=headers,
                content=body
            )

        return callback

    @pytest.fixture(autouse=True)
    async def setup(self):
        self.ably = await TestApp.get_ably_rest(use_binary_protocol=False)
        # Mocked responses
        # without specific headers
        self.mocked_api = respx.mock(base_url='http://main.realtime.ably.net')
        self.ch1_route = self.mocked_api.get('/channels/channel_name/ch1')
        self.ch1_route.return_value = Response(
            headers={'content-type': 'application/json'},
            status_code=200,
            content='[{"id": 0}, {"id": 1}]',
        )
        # with headers
        self.ch2_route = self.mocked_api.get('/channels/channel_name/ch2')
        self.ch2_route.side_effect = self.get_response_callback(
            headers={
                'content-type': 'application/json',
                'link':
                    '<http://main.realtime.ably.net/channels/channel_name/ch2?page=1>; rel="first",'
                    ' <http://main.realtime.ably.net/channels/channel_name/ch2?page=2>; rel="next"'
            },
            body='[{"id": 0}, {"id": 1}]',
            status=200
        )
        # start intercepting requests
        self.mocked_api.start()

        self.paginated_result = await PaginatedResult.paginated_query(
            self.ably.http,
            url='http://main.realtime.ably.net/channels/channel_name/ch1',
            response_processor=lambda response: response.to_native())
        self.paginated_result_with_headers = await PaginatedResult.paginated_query(
            self.ably.http,
            url='http://main.realtime.ably.net/channels/channel_name/ch2',
            response_processor=lambda response: response.to_native())
        yield
        self.mocked_api.stop()
        self.mocked_api.reset()
        await self.ably.close()

    def test_items(self):
        assert len(self.paginated_result.items) == 2

    async def test_with_no_headers(self):
        assert await self.paginated_result.first() is None
        assert await self.paginated_result.next() is None
        assert self.paginated_result.is_last()

    def test_with_next(self):
        pag = self.paginated_result_with_headers
        assert pag.has_next()
        assert not pag.is_last()

    async def test_first(self):
        pag = self.paginated_result_with_headers
        pag = await pag.first()
        assert pag.items[0]['page'] == 1

    async def test_next(self):
        pag = self.paginated_result_with_headers
        pag = await pag.next()
        assert pag.items[0]['page'] == 2
