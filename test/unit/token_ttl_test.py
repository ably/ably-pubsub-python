from datetime import timedelta

import pytest

from ably.pubsub.http.auth import Auth, ttl_ms
from ably.pubsub.server import create_http_client


# TK2a: a ttl given as a timedelta is sent as its exact count of milliseconds
@pytest.mark.parametrize('ms', [1, 999, 1001, 1003, 59_999, 3_600_000])
def test_ttl_ms_converts_a_timedelta_exactly(ms):
    assert ttl_ms(timedelta(milliseconds=ms)) == ms


def test_ttl_ms_keeps_milliseconds_given_as_a_number():
    assert ttl_ms(3_600_000) == 3_600_000
    assert ttl_ms('1001') == 1001


def test_ttl_ms_is_exact_for_every_millisecond_up_to_200_seconds():
    assert [ms for ms in range(200_001) if ttl_ms(timedelta(milliseconds=ms)) != ms] == []


async def test_create_token_request_sends_a_timedelta_ttl_exactly():
    client = create_http_client(key='app.key:secret')
    try:
        token_request = await client.auth.create_token_request({'ttl': timedelta(milliseconds=1001)})
        assert token_request.ttl == 1001
    finally:
        await client.close()


def test_auth_url_params_send_a_timedelta_ttl_exactly():
    params = Auth._auth_url_token_params({'ttl': timedelta(milliseconds=1001)})
    assert params['ttl'] == 1001
