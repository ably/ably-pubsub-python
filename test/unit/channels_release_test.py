import asyncio
import logging

import pytest

from ably.realtime.connection import ConnectionState
from ably.transport.websockettransport import ProtocolMessageAction
from ably.types.channelstate import ChannelState
from test.uts.helpers.client import await_connection_state, close_open_clients, realtime_client
from test.uts.helpers.mock_websocket import CONNECTED_MESSAGE, MockWebSocket, attached_message, detached_message

OPERATION_TIMEOUT = 1.0


@pytest.fixture(autouse=True)
async def close_clients():
    yield
    await close_open_clients()


async def attached_channel(channel_name):
    mock_ws = MockWebSocket(
        on_connection_attempt=lambda conn: conn.respond_with_success(CONNECTED_MESSAGE),
    )

    def on_message_from_client(msg):
        if msg.get('action') == ProtocolMessageAction.ATTACH:
            mock_ws.send_to_client(attached_message(msg['channel']))
        elif msg.get('action') == ProtocolMessageAction.DETACH:
            mock_ws.send_to_client(detached_message(msg['channel']))

    mock_ws.on_message_from_client = on_message_from_client
    client = realtime_client(mock_ws)
    client.connect()
    await await_connection_state(client, ConnectionState.CONNECTED)
    channel = client.channels.get(channel_name)
    await asyncio.wait_for(channel.attach(), OPERATION_TIMEOUT)
    return client, channel


def deprecation_warnings(caplog):
    return [record for record in caplog.records
            if record.levelno == logging.WARNING and 'deprecated' in record.getMessage()]


# RTS4b
async def test_releasing_an_attached_channel_logs_a_deprecation_warning(caplog):
    client, channel = await attached_channel('attached')

    with caplog.at_level(logging.WARNING, logger='ably'):
        client.channels.release('attached')

    warnings = deprecation_warnings(caplog)
    assert len(warnings) == 1
    assert 'attached state' in warnings[0].getMessage()
    assert 'attached' not in client.channels


# RTS4b
async def test_releasing_a_detached_channel_logs_no_deprecation_warning(caplog):
    client, channel = await attached_channel('detached')
    await asyncio.wait_for(channel.detach(), OPERATION_TIMEOUT)
    assert channel.state == ChannelState.DETACHED

    with caplog.at_level(logging.WARNING, logger='ably'):
        client.channels.release('detached')

    assert deprecation_warnings(caplog) == []
    assert 'detached' not in client.channels
