"""Derived from uts/realtime/unit/auth/token_expiry_non_renewable_test.md in ably/specification.

Spec points: RSA4a, RSA4a1, RSA4a2
"""

import logging

from ably.realtime.connection import ConnectionState
from test.uts.helpers.client import await_connection_state, realtime_client
from test.uts.helpers.deviations import deviation
from test.uts.helpers.mock_websocket import ERROR_MESSAGE, MockWebSocket, connected_message

CONNECTED = connected_message('connection-id', connectionKey='connection-key')


# UTS: realtime/unit/RSA4a1/non-renewable-token-logs-warning-0
@deviation
async def test_rsa4a1_non_renewable_token_logs_warning(caplog):
    mock_ws = MockWebSocket(on_connection_attempt=lambda conn: conn.respond_with_success(CONNECTED))

    # The specification collects the library's log through a `logHandler` client
    # option. ably-python logs through the standard `logging` module and has no
    # such option, so the records are captured from the `ably` logger instead.
    with caplog.at_level(logging.INFO, logger='ably'):
        realtime_client(mock_ws, token='non-renewable-token', use_binary_protocol=False)

    info_messages = [record.getMessage() for record in caplog.records
                     if record.levelno == logging.INFO]

    assert any('40171' in message
               or ('no means' in message and 'renew' in message)
               for message in info_messages)

    # TI5: the log entry carries the help URL for the error
    assert any('https://help.ably.io/error/40171' in message for message in info_messages)


# UTS: realtime/unit/RSA4a2/token-error-non-renewable-failed-0
async def test_rsa4a2_token_error_non_renewable_failed():
    def on_connection_attempt(conn):
        conn.respond_with_success()
        conn.send_to_client_and_close(ERROR_MESSAGE(40142, 'Token expired'))

    mock_ws = MockWebSocket(on_connection_attempt=on_connection_attempt)
    client = realtime_client(mock_ws, token='expired-token', use_binary_protocol=False)

    state_changes = []
    client.connection.on(lambda change: state_changes.append(change))

    client.connect()
    await await_connection_state(client, ConnectionState.FAILED)

    assert client.connection.state == ConnectionState.FAILED

    assert client.connection.error_reason is not None
    assert client.connection.error_reason.code == 40171

    failed_changes = [c for c in state_changes if c.current == ConnectionState.FAILED]
    assert len(failed_changes) == 1
    assert failed_changes[0].reason is not None
    assert failed_changes[0].reason.code == 40171


# UTS: realtime/unit/RSA4a2/token-error-non-renewable-no-retry-1
async def test_rsa4a2_token_error_non_renewable_no_retry():
    connection_attempt_count = 0

    def on_connection_attempt(conn):
        nonlocal connection_attempt_count
        connection_attempt_count += 1
        conn.respond_with_success()
        conn.send_to_client_and_close(ERROR_MESSAGE(40140, 'Token error'))

    mock_ws = MockWebSocket(on_connection_attempt=on_connection_attempt)
    client = realtime_client(mock_ws, token='non-renewable-token', use_binary_protocol=False)

    client.connect()
    await await_connection_state(client, ConnectionState.FAILED)

    assert connection_attempt_count == 1
    assert client.connection.state == ConnectionState.FAILED
    assert client.connection.error_reason is not None
    assert client.connection.error_reason.code == 40171
