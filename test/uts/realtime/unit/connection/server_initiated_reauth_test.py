"""Derived from uts/realtime/unit/connection/server_initiated_reauth_test.md in ably/specification.

Spec points: RTN22, RTN22a
"""

import time

from ably.realtime.connection import ConnectionEvent, ConnectionState
from ably.transport.websockettransport import ProtocolMessageAction
from ably.types.tokendetails import TokenDetails
from test.uts.helpers.client import await_connection_state, realtime_client
from test.uts.helpers.clock import settle
from test.uts.helpers.mock_websocket import MockWebSocket, connected_message

AUTH_ACTION = int(ProtocolMessageAction.AUTH)
DISCONNECTED_ACTION = int(ProtocolMessageAction.DISCONNECTED)

# How many settling passes a reauth is given: the server's AUTH, the token the auth
# callback returns, the client's AUTH and the CONNECTED that answers it
REAUTH_PASSES = 20


def token_details(token):
    return TokenDetails(token=token, expires=int(time.time() * 1000) + 3600000)


async def settle_until(predicate, message, passes=REAUTH_PASSES):
    """Settles until `predicate` holds, as the specifications' `AWAIT UNTIL` does."""
    for _ in range(passes):
        if predicate():
            return
        await settle()
    raise AssertionError(f'Timed out waiting for {message}')


# UTS: realtime/unit/RTN22/server-auth-triggers-reauth-0
async def test_rtn22_server_auth_triggers_reauth():
    auth_callback_calls = []
    captured_auth_messages = []

    async def auth_callback(token_params):
        auth_callback_calls.append(token_params)
        return token_details(f'token-{len(auth_callback_calls)}')

    mock_ws = MockWebSocket(
        on_connection_attempt=lambda conn: conn.respond_with_success(
            connected_message('connection-id', connectionKey='connection-key')),
    )
    client = realtime_client(mock_ws, auth_callback=auth_callback)

    client.connect()
    await await_connection_state(client, ConnectionState.CONNECTED)

    state_changes = []
    client.connection.on(lambda change: state_changes.append(change))

    def on_message_from_client(message):
        if message.get('action') == AUTH_ACTION:
            captured_auth_messages.append(message)
            mock_ws.send_to_client(
                connected_message('connection-id', connectionKey='connection-key-2'))

    mock_ws.on_message_from_client = on_message_from_client

    mock_ws.send_to_client({'action': AUTH_ACTION})

    await settle_until(
        lambda: any(change.event == ConnectionEvent.UPDATE for change in state_changes),
        'the UPDATE event that signals reauth completion')

    assert len(auth_callback_calls) == 2

    assert len(captured_auth_messages) == 1
    assert captured_auth_messages[0].get('auth') is not None
    assert captured_auth_messages[0]['auth']['accessToken'] == 'token-2'

    assert [change for change in state_changes
            if change.current != ConnectionState.CONNECTED] == []

    update_events = [change for change in state_changes
                     if change.event == ConnectionEvent.UPDATE]
    assert len(update_events) == 1


# UTS: realtime/unit/RTN22/stays-connected-during-reauth-1
async def test_rtn22_stays_connected_during_reauth():
    auth_callback_calls = []

    async def auth_callback(token_params):
        auth_callback_calls.append(token_params)
        return token_details(f'reauth-token-{len(auth_callback_calls)}')

    mock_ws = MockWebSocket(
        on_connection_attempt=lambda conn: conn.respond_with_success(
            connected_message('conn-1', connectionKey='key-1')),
    )

    def on_message_from_client(message):
        if message.get('action') == AUTH_ACTION:
            mock_ws.send_to_client(connected_message('conn-1', connectionKey='key-1-updated'))

    mock_ws.on_message_from_client = on_message_from_client
    client = realtime_client(mock_ws, auth_callback=auth_callback)

    client.connect()
    await await_connection_state(client, ConnectionState.CONNECTED)

    state_changes = []
    client.connection.on(lambda change: state_changes.append(change))

    mock_ws.send_to_client({'action': AUTH_ACTION})

    await settle_until(lambda: len(state_changes) >= 1, 'the UPDATE event')

    assert client.connection.state == ConnectionState.CONNECTED

    assert len(state_changes) == 1
    assert state_changes[0].event == ConnectionEvent.UPDATE
    assert state_changes[0].current == ConnectionState.CONNECTED
    assert state_changes[0].previous == ConnectionState.CONNECTED


# UTS: realtime/unit/RTN22a/forced-disconnect-reauth-failure-0
async def test_rtn22a_forced_disconnect_reauth_failure():
    auth_callback_calls = []

    async def auth_callback(token_params):
        auth_callback_calls.append(token_params)
        return token_details(f'recovery-token-{len(auth_callback_calls)}')

    mock_ws = MockWebSocket(
        on_connection_attempt=lambda conn: conn.respond_with_success(
            connected_message('conn-1', connectionKey='key-1')),
    )
    client = realtime_client(mock_ws, auth_callback=auth_callback)

    # RTN15h recovery leaves DISCONNECTED again immediately, so the state changes
    # are recorded and asserted on rather than waited for
    state_changes = []
    client.connection.on(lambda change: state_changes.append(change))

    client.connect()
    await await_connection_state(client, ConnectionState.CONNECTED)

    mock_ws.send_to_client({
        'action': DISCONNECTED_ACTION,
        'error': {'message': 'Token expired', 'code': 40142, 'statusCode': 401},
    })

    await await_connection_state(client, ConnectionState.CONNECTING)

    disconnected = [change for change in state_changes
                    if change.current == ConnectionState.DISCONNECTED]
    assert len(disconnected) == 1
    assert disconnected[0].reason is not None
    assert disconnected[0].reason.code == 40142

    # The recovery obtains a new token before reconnecting
    assert len(auth_callback_calls) == 2
