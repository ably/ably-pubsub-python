import httpx
import pytest

from ably import AblyRest
from ably.types.testoptions import TestOptions
from ably.util.exceptions import AblyException


class RecordingTransport(httpx.AsyncBaseTransport):
    def __init__(self):
        self.requests = []

    async def handle_async_request(self, request):
        self.requests.append(request)
        return httpx.Response(200, json={})


# RSH1e1a: the recipient must name exactly one of channels and deviceId,
# and is rejected before any request is made
@pytest.mark.parametrize('recipient', [
    {},
    {'channels': []},
    {'channels': ['a'], 'deviceId': 'device-1'},
])
async def test_live_activity_start_rejects_invalid_recipient(recipient):
    transport = RecordingTransport()
    ably = AblyRest(key='appId.keyId:keySecret', _test_options=TestOptions(http_transport=transport))
    try:
        with pytest.raises(AblyException) as excinfo:
            await ably.push.admin.live_activity.start(
                recipient=recipient,
                apns_broadcast='broadcast-1',
                apns={'aps': {'event': 'start'}},
            )
    finally:
        await ably.close()

    assert excinfo.value.code == 40000
    assert excinfo.value.status_code == 400
    assert transport.requests == []
