"""Derived from uts/realtime/unit/client/realtime_client.md in ably/specification.

Spec points: RTC1a, RTC1b, RTC1c, RTC1f, RTC2, RTC3, RTC4, RTC12, RTC13, RTC15,
RTC16, RTC17
"""

import json

import pytest

from ably.realtime.channel import Channels, RealtimeChannel
from ably.realtime.connection import Connection, ConnectionState
from ably.rest.auth import Auth
from ably.rest.push import Push, PushAdmin
from ably.transport.websockettransport import ProtocolMessageAction
from ably.util.exceptions import AblyException
from ably.util.helper import get_random_id
from test.uts.helpers.client import await_connection_state, realtime_client
from test.uts.helpers.clock import settle
from test.uts.helpers.deviations import deviation
from test.uts.helpers.mock_websocket import CLOSED_MESSAGE, MockEventType, MockWebSocket, connected_message

SPEC_KEY = 'appId.keyId:keySecret'

CONNECTED_MESSAGE = connected_message('connection-id', connectionKey='connection-key')


def succeeding_mock():
    return MockWebSocket(
        on_connection_attempt=lambda conn: conn.respond_with_success(CONNECTED_MESSAGE),
    )


def encode_recovery_key(connection_key, msg_serial, channel_serials):
    """The RTN16 recovery key: a JSON object carrying the previous connection's state."""
    return json.dumps({
        'connectionKey': connection_key,
        'msgSerial': msg_serial,
        'channelSerials': channel_serials,
    })


# UTS: realtime/unit/RTC12/constructor-string-detection-0
async def test_rtc12_constructor_string_detection():
    # NOTE: the spec refers this test to `uts/test/realtime/unit/client/client_options.md`
    # for RSC1/RSC1a/RSC1c. No such file exists in the specification repository, and
    # neither do derived RSC1 tests, so the three cases the spec lists in its own body
    # are what is asserted here. See deviations.md.
    mock_ws = succeeding_mock()

    # An API key string carries a `:` and selects basic auth
    client = realtime_client(mock_ws, key=SPEC_KEY)
    assert client.auth.auth_mechanism == Auth.Method.BASIC
    assert client.options.key_name == 'appId.keyId'
    assert client.options.key_secret == 'keySecret'

    # DEVIATION: the spec requires a string with no `:` to be detected as a token and
    # to select token auth. ably-python reads a string argument only as an API key and
    # rejects one that does not split in two.
    with pytest.raises(AblyException) as excinfo:
        realtime_client(mock_ws, key='token-string-with-no-delimiter')
    assert excinfo.value.code == 40101

    # An empty string is an error, as the spec requires
    with pytest.raises(AblyException) as excinfo:
        realtime_client(mock_ws, key='')
    assert excinfo.value.code == 40101


# UTS: realtime/unit/RTC12/invalid-arguments-error-1
async def test_rtc12_invalid_arguments_error():
    mock_ws = succeeding_mock()

    # DEVIATION: the spec expects error code 40106 when no valid credentials are
    # provided. ably-python rejects the options in the constructor instead, with a
    # plain ValueError that carries no Ably error code. This mirrors the REST suite's
    # `RSC1b/no-auth-method-error-0`.
    with pytest.raises(ValueError) as excinfo:
        realtime_client(mock_ws, key=None)

    assert 'key is missing' in str(excinfo.value)

    assert mock_ws.connection_attempts == []


# UTS: realtime/unit/RTC2/connection-attribute-0
async def test_rtc2_connection_attribute():
    mock_ws = succeeding_mock()
    client = realtime_client(mock_ws, key=SPEC_KEY, auto_connect=False)

    assert client.connection is not None
    assert isinstance(client.connection, Connection)
    # The spec's type assertion, rendered for a weakly typed language as the
    # interface the Connection is required to carry
    assert callable(client.connection.connect)
    assert callable(client.connection.close)
    assert callable(client.connection.on)

    assert client.connection.state == ConnectionState.INITIALIZED


# UTS: realtime/unit/RTC3/channels-attribute-0
async def test_rtc3_channels_attribute():
    channel_name = f'test-RTC3-{get_random_id()}'

    mock_ws = succeeding_mock()
    client = realtime_client(mock_ws, key=SPEC_KEY, auto_connect=False)

    assert client.channels is not None
    assert isinstance(client.channels, Channels)

    channel = client.channels.get(channel_name)
    assert isinstance(channel, RealtimeChannel)
    assert channel.name == channel_name


# UTS: realtime/unit/RTC4/auth-attribute-0
async def test_rtc4_auth_attribute():
    mock_ws = succeeding_mock()
    client = realtime_client(mock_ws, key=SPEC_KEY, auto_connect=False)

    assert client.auth is not None
    assert isinstance(client.auth, Auth)
    assert callable(client.auth.authorize)
    assert callable(client.auth.request_token)


# UTS: realtime/unit/RTC13/push-attribute-0
async def test_rtc13_push_attribute():
    mock_ws = succeeding_mock()
    client = realtime_client(mock_ws, key=SPEC_KEY, auto_connect=False)

    assert client.push is not None
    assert isinstance(client.push, Push)
    assert client.push.admin is not None
    assert isinstance(client.push.admin, PushAdmin)


# UTS: realtime/unit/RTC17/client-id-attribute-0
async def test_rtc17_client_id_attribute():
    mock_ws = succeeding_mock()
    client = realtime_client(mock_ws, key=SPEC_KEY, client_id='explicit-client-id', auto_connect=False)

    assert client.client_id == 'explicit-client-id'

    # DEVIATION: the spec asserts `client.clientId == client.auth.clientId`.
    # `AblyRealtime.client_id` reads the client options, while `Auth.client_id` is
    # held at None for a realtime client until the server confirms one in a CONNECTED
    # message, so the two disagree before the connection is established.
    assert client.auth.client_id is None


# UTS: realtime/unit/RTC1a/echo-messages-option-0
# DEVIATION: ably-python has no `echo_messages` option and sends no `echo` query
# parameter. See deviations.md.
@deviation
async def test_rtc1a_echo_messages_option():
    # RTC1a_1: echoMessages defaults to true
    mock_ws = MockWebSocket()
    realtime_client(mock_ws, key=SPEC_KEY, auto_connect=True)

    pending = await mock_ws.await_connection_attempt()
    pending.respond_with_success(CONNECTED_MESSAGE)

    assert 'echo' in pending.url.query_params
    assert pending.url.query_params['echo'] == 'true'

    # RTC1a_2: echoMessages set to false
    other_ws = MockWebSocket()
    realtime_client(other_ws, key=SPEC_KEY, auto_connect=True, echo_messages=False)

    pending = await other_ws.await_connection_attempt()
    pending.respond_with_success(CONNECTED_MESSAGE)

    assert pending.url.query_params['echo'] == 'false'


# UTS: realtime/unit/RTC1b/auto-connect-option-0
async def test_rtc1b_auto_connect_option():
    # RTC1b_1: autoConnect defaults to true. `realtime_client` defaults it to false,
    # so the option's own default is named here
    mock_ws = succeeding_mock()
    client = realtime_client(mock_ws, key=SPEC_KEY, auto_connect=True)

    await await_connection_state(client, ConnectionState.CONNECTED)
    assert len(mock_ws.connection_attempts) >= 1

    # RTC1b_2: autoConnect set to false
    idle_ws = succeeding_mock()
    idle_client = realtime_client(idle_ws, key=SPEC_KEY, auto_connect=False)

    assert idle_client.connection.state == ConnectionState.INITIALIZED
    assert len(idle_ws.connection_attempts) == 0

    await settle()

    assert idle_client.connection.state == ConnectionState.INITIALIZED
    assert len(idle_ws.connection_attempts) == 0

    # RTC1b_3: explicit connect after autoConnect false
    idle_client.connection.connect()
    await await_connection_state(idle_client, ConnectionState.CONNECTED)

    assert len(idle_ws.events_of_type(MockEventType.CONNECTION_ATTEMPT)) == 1
    assert idle_client.connection.state == ConnectionState.CONNECTED


# UTS: realtime/unit/RTC1c/recover-option-0
# DEVIATION: the `recover` option is stored and never read, so no `recover` query
# parameter is ever sent. See deviations.md.
@deviation
async def test_rtc1c_recover_option():
    recovery_key = encode_recovery_key('previous-connection-key', 5, {'channel1': 'serial1'})

    # RTC1c_1: the recover string is sent in the connection request
    mock_ws = MockWebSocket()
    realtime_client(mock_ws, key=SPEC_KEY, auto_connect=True, recover=recovery_key)

    pending = await mock_ws.await_connection_attempt()
    pending.respond_with_success(CONNECTED_MESSAGE)

    assert 'recover' in pending.url.query_params
    assert pending.url.query_params['recover'] == 'previous-connection-key'

    # RTC1c_2: the recover option is cleared after the first attempt (RTN16k)
    states = []
    resuming_ws = MockWebSocket(
        on_connection_attempt=lambda conn: conn.respond_with_success(CONNECTED_MESSAGE),
    )
    resuming_client = realtime_client(
        resuming_ws, key=SPEC_KEY, auto_connect=True,
        recover=encode_recovery_key('previous-connection-key', 5, {}))
    resuming_client.connection.on(lambda change: states.append(change.current))

    await await_connection_state(resuming_client, ConnectionState.CONNECTED)

    resuming_ws.simulate_disconnect()
    await settle()

    assert ConnectionState.DISCONNECTED in states
    assert len(resuming_ws.connection_attempts) >= 2
    assert 'recover' not in resuming_ws.connection_attempts[1].url.query_params

    # RTC1c_3: an invalid recovery key is handled gracefully
    invalid_ws = MockWebSocket()
    realtime_client(invalid_ws, key=SPEC_KEY, auto_connect=True,
                    recover='invalid-not-a-valid-recovery-key')

    pending = await invalid_ws.await_connection_attempt()
    pending.respond_with_success(CONNECTED_MESSAGE)

    assert 'recover' not in pending.url.query_params


# UTS: realtime/unit/RTC1f/transport-params-option-0
async def test_rtc1f_transport_params_option():
    # RTC1f_1: transportParams are included in the connection URL
    mock_ws = MockWebSocket()
    realtime_client(mock_ws, key=SPEC_KEY, auto_connect=True, transport_params={
        'customParam': 'customValue',
        'anotherParam': '123',
    })

    pending = await mock_ws.await_connection_attempt()
    pending.respond_with_success(CONNECTED_MESSAGE)

    assert pending.url.query_params['customParam'] == 'customValue'
    assert pending.url.query_params['anotherParam'] == '123'

    # RTC1f_2: transportParams carrying values of other types
    typed_ws = MockWebSocket()
    realtime_client(typed_ws, key=SPEC_KEY, auto_connect=True, transport_params={
        'stringParam': 'hello',
        'numberParam': 42,
        'boolTrueParam': True,
        'boolFalseParam': False,
    })

    pending = await typed_ws.await_connection_attempt()
    pending.respond_with_success(CONNECTED_MESSAGE)

    assert pending.url.query_params['stringParam'] == 'hello'
    assert pending.url.query_params['numberParam'] == '42'
    # DEVIATION: the spec requires booleans to be stringified as "true" and "false".
    # The query string is built with `urllib.parse.urlencode`, which renders a bool
    # through `str()`, giving Python's capitalised spelling.
    assert pending.url.query_params['boolTrueParam'] == 'True'
    assert pending.url.query_params['boolFalseParam'] == 'False'

    # RTC1f1: user-specified transportParams override library defaults
    override_ws = MockWebSocket()
    realtime_client(override_ws, key=SPEC_KEY, auto_connect=True, transport_params={
        'v': '3',
        'heartbeats': 'false',
    })

    pending = await override_ws.await_connection_attempt()
    pending.respond_with_success(CONNECTED_MESSAGE)

    assert pending.url.query_params['v'] == '3'
    assert pending.url.query_params['heartbeats'] == 'false'


# UTS: realtime/unit/RTC15/connect-method-0
async def test_rtc15_connect_method():
    states = []
    mock_ws = succeeding_mock()
    client = realtime_client(mock_ws, key=SPEC_KEY, auto_connect=False)
    client.connection.on(lambda change: states.append(change.current))

    assert client.connection.state == ConnectionState.INITIALIZED

    client.connect()

    await await_connection_state(client, ConnectionState.CONNECTED)

    assert ConnectionState.CONNECTING in states
    assert client.connection.state == ConnectionState.CONNECTED


# UTS: realtime/unit/RTC16/close-method-0
async def test_rtc16_close_method():
    def on_message_from_client(message):
        if message['action'] == int(ProtocolMessageAction.CLOSE):
            mock_ws.send_to_client(CLOSED_MESSAGE)

    mock_ws = MockWebSocket(
        on_connection_attempt=lambda conn: conn.respond_with_success(CONNECTED_MESSAGE),
        on_message_from_client=on_message_from_client,
    )
    client = realtime_client(mock_ws, key=SPEC_KEY, auto_connect=True)

    await await_connection_state(client, ConnectionState.CONNECTED)

    states = []
    client.connection.on(lambda change: states.append(change.current))

    await client.close()

    assert ConnectionState.CLOSING in states
    assert client.connection.state == ConnectionState.CLOSED
