"""Derived from uts/rest/unit/types/options_types.md in ably/specification.

Spec points: TO1, TO2, TO3, AO1, AO2
"""

import pytest

from ably import AblyRest
from ably.types.authoptions import AuthOptions
from ably.types.options import Options
from ably.types.tokendetails import TokenDetails
from ably.util.exceptions import AblyException
from test.uts.helpers.client import rest_client
from test.uts.helpers.deviations import deviation
from test.uts.helpers.mock_http import MockHttpClient

# `ClientOptions` is spelled `Options`, its attributes are snake_case, and a key is held as the
# `key_name` / `key_secret` pair it parses into rather than as a `key` attribute.

ENDPOINT_CASES = [
    # DEVIATION: the spec leaves `endpoint` unset where none is given; `Options` resolves
    # the default eagerly to the REC1a routing policy id `main`.
    pytest.param(None, id='production', marks=deviation),
    pytest.param('test', id='test'),
    pytest.param('custom-env', id='custom-env'),
]


def mock_http_client():
    return MockHttpClient(on_connection_attempt=lambda conn: conn.respond_with_success())


# UTS: rest/unit/TO3/client-options-attributes-0
async def test_to3_client_options_attributes():
    options = Options()

    assert options.auth_method == 'GET'
    assert options.tls is True

    # DEVIATION: httpRequestTimeout and httpMaxRetryCount have no default on the options
    # object; both are left unset and the effective defaults are applied downstream, the
    # first by Http and the second by Options.__get_hosts via Defaults.http_max_retry_count.
    assert options.http_request_timeout is None
    assert options.http_max_retry_count is None

    assert options.use_binary_protocol is True
    assert options.idempotent_rest_publishing is True
    assert options.add_request_ids is False
    assert options.query_time is False

    # DEVIATION: TO3l8 `maxMessageSize` (default 65536) is not a client option here. Realtime
    # publishes read it with getattr(options, 'max_message_size', 65536), so the 64KiB default
    # holds, but it cannot be configured and passing it is rejected.
    with pytest.raises(TypeError):
        Options(max_message_size=65536)

    # The effective defaults the options leave unset: 10 seconds, and 3 hosts to try.
    client = rest_client(mock_http_client())
    assert client.http.http_request_timeout == 10
    assert len(client.options.get_hosts()) == 3

    options = Options(
        key='appId.keyId:keySecret',
        client_id='my-client',
        endpoint='test',
        tls=False,
        http_request_timeout=30000,
        use_binary_protocol=False,
        idempotent_rest_publishing=False,
        add_request_ids=True,
    )

    assert options.key_name == 'appId.keyId'
    assert options.key_secret == 'keySecret'
    assert options.client_id == 'my-client'
    assert options.endpoint == 'test'
    assert options.tls is False
    assert options.http_request_timeout == 30000
    assert options.use_binary_protocol is False
    assert options.idempotent_rest_publishing is False
    assert options.add_request_ids is True


# UTS: rest/unit/TO3/client-options-custom-hosts-1
def test_to3_client_options_custom_hosts():
    options = Options(
        key='appId.keyId:keySecret',
        rest_host='custom.ably.example.com',
        fallback_hosts=['fallback1.example.com', 'fallback2.example.com'],
    )

    # rest_host is deprecated in favour of endpoint (REC1d), which is where it is held
    assert options.endpoint == 'custom.ably.example.com'
    # The fallbacks are kept as given, in the random order RSC15a tries them in
    assert sorted(options.fallback_hosts) == ['fallback1.example.com', 'fallback2.example.com']


# UTS: rest/unit/TO3/client-options-auth-url-2
def test_to3_client_options_auth_url():
    options = Options(
        auth_url='https://auth.example.com/token',
        auth_method='POST',
        auth_headers={'X-API-Key': 'secret'},
        auth_params={'scope': 'full'},
    )

    assert options.auth_url == 'https://auth.example.com/token'
    assert options.auth_method == 'POST'
    assert options.auth_headers['X-API-Key'] == 'secret'
    assert options.auth_params['scope'] == 'full'


# UTS: rest/unit/TO3/client-options-default-token-params-3
def test_to3_client_options_default_token_params():
    # There is no TokenParams type; token params are dicts throughout the auth API
    options = Options(
        key='appId.keyId:keySecret',
        default_token_params={
            'ttl': 7200000,
            'client_id': 'default-client',
            'capability': '{"*":["subscribe"]}',
        },
    )

    assert options.default_token_params['ttl'] == 7200000
    assert options.default_token_params['client_id'] == 'default-client'
    assert options.default_token_params['capability'] == '{"*":["subscribe"]}'


# UTS: rest/unit/AO2/auth-options-attributes-0
def test_ao2_auth_options_attributes():
    auth_options = AuthOptions(
        auth_url='https://auth.example.com/token',
        auth_method='POST',
        auth_headers={'Authorization': 'Bearer api-key'},
        auth_params={'user': 'test'},
        query_time=True,
    )

    assert auth_options.auth_url == 'https://auth.example.com/token'
    assert auth_options.auth_method == 'POST'
    assert auth_options.auth_headers['Authorization'] == 'Bearer api-key'
    assert auth_options.auth_params['user'] == 'test'
    assert auth_options.query_time is True


# UTS: rest/unit/AO/auth-options-with-callback-0
async def test_ao_auth_options_with_callback():
    callback_called = False

    # Auth callbacks are awaited, so the stored callback is a coroutine function
    async def test_callback(params):
        nonlocal callback_called
        callback_called = True
        return TokenDetails(token='callback-token', expires=1234567890000 + 3600000)

    auth_options = AuthOptions(auth_callback=test_callback)

    # Verify callback is stored and callable
    result = await auth_options.auth_callback({})
    assert callback_called is True
    assert result.token == 'callback-token'


# UTS: rest/unit/TO/endpoint-affects-host-0
@pytest.mark.parametrize('endpoint', ENDPOINT_CASES)
def test_to_endpoint_affects_host(endpoint):
    if endpoint is None:
        options = Options(key='appId.keyId:keySecret')
    else:
        options = Options(key='appId.keyId:keySecret', endpoint=endpoint)

    assert options.endpoint == endpoint


# UTS: rest/unit/TO/conflicting-options-validation-1
async def test_to_conflicting_options_validation():
    # Case 1: key + authCallback is valid
    async def auth_callback(params):
        return 'a-token'

    client = rest_client(mock_http_client(), key='appId.keyId:keySecret', auth_callback=auth_callback)
    assert client.auth.auth_options.auth_callback is auth_callback

    # Case 2: restHost + endpoint conflict
    with pytest.raises(AblyException) as excinfo:
        Options(key='appId.keyId:keySecret', rest_host='custom.host.com', endpoint='test')
    assert 'rest_host' in excinfo.value.message or 'endpoint' in excinfo.value.message

    # Case 3: no auth options
    # The missing-credentials check is a constructor argument check, so it raises ValueError
    # rather than an AblyException
    with pytest.raises(ValueError) as value_error:
        AblyRest()
    assert 'key' in str(value_error.value)
