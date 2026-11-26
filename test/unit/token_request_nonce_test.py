import json

import pytest

from ably.pubsub.util.exceptions import AblyException
from test.uts.helpers.client import rest_client
from test.uts.helpers.mock_http import MockHttpClient

KEY = 'appId.keyId:keySecret'
REPLAYED_BODY = {'error': {'code': 40105, 'statusCode': 401, 'message': 'Nonce value replayed'}}
TOKEN_BODY = {'token': 'obtained-token', 'expires': 9999999999999, 'keyName': 'appId.keyId'}


def nonce_server():
    """A requestToken endpoint that uses each nonce one time only and loses the first response."""
    used_nonces = []

    def on_request(request):
        nonce = json.loads(request.body)['nonce']
        if nonce in used_nonces:
            request.respond_with(401, REPLAYED_BODY)
            return
        used_nonces.append(nonce)
        if len(used_nonces) == 1:
            # The server used the nonce, but the response does not reach the client
            request.respond_with_timeout()
        else:
            request.respond_with(200, TOKEN_BODY)

    mock_http = MockHttpClient(
        on_connection_attempt=lambda conn: conn.respond_with_success(),
        on_request=on_request,
    )
    return mock_http, used_nonces


async def test_request_token_signs_a_new_nonce_after_a_replayed_retry():
    mock_http, used_nonces = nonce_server()
    client = rest_client(mock_http, key=KEY, use_binary_protocol=False,
                         fallback_hosts=['a.example.com', 'b.example.com'])

    token_details = await client.auth.request_token()

    assert token_details.token == 'obtained-token'
    assert len(used_nonces) == 2


async def test_request_token_keeps_a_nonce_the_caller_gives():
    mock_http, used_nonces = nonce_server()
    client = rest_client(mock_http, key=KEY, use_binary_protocol=False,
                         fallback_hosts=['a.example.com', 'b.example.com'])

    with pytest.raises(AblyException) as excinfo:
        await client.auth.request_token({'nonce': 'fixed-nonce-value'})

    assert excinfo.value.code == 40105
    assert used_nonces == ['fixed-nonce-value']
