"""Derived from uts/realtime/unit/client/realtime_request.md in ably/specification.

Spec points: RTC9
"""

from test.uts.helpers.client import realtime_client
from test.uts.helpers.mock_http import MockHttpClient

SPEC_KEY = 'appId.keyId:keySecret'

ITEMS = [
    {'id': 'msg1', 'name': 'event1', 'data': 'data1'},
    {'id': 'msg2', 'name': 'event2', 'data': 'data2'},
]


# UTS: realtime/unit/RTC9/request-proxies-rest-0
async def test_rtc9_request_proxies_rest():
    # The specification directs uts/rest/unit/request.md (RSC19) at a realtime client
    # in place of a REST one. `AblyRealtime` subclasses `AblyRest`, so the same HTTP
    # mock serves it, and this mirrors that suite's `RSC19f/supports-http-methods-0`
    # and `RSC19d/response-items-decoded-5`.
    captured_requests = []

    def on_request(request):
        captured_requests.append(request)
        request.respond_with(200, ITEMS)

    mock_http = MockHttpClient(
        on_connection_attempt=lambda conn: conn.respond_with_success(),
        on_request=on_request,
    )
    # `auto_connect` is left at `realtime_client`'s false, so no websocket is opened
    client = realtime_client(mock_http=mock_http, key=SPEC_KEY)

    # NOTE: request() takes version as a string in ably-python; the spec writes `version: 3`
    response = await client.request('GET', '/channels/test/messages', version='3')

    assert response.status_code == 200
    assert response.success is True

    items = response.items
    assert len(items) == 2
    assert items[0]['id'] == 'msg1'
    assert items[1]['id'] == 'msg2'

    assert len(captured_requests) == 1
    request = captured_requests[0]
    assert request.method == 'GET'
    assert request.url.path == '/channels/test/messages'
