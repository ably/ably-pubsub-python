import asyncio
import json
import urllib.parse

import httpx
import pytest

from ably.pubsub.realtime.connection import ConnectionState
from ably.pubsub.transport.websockettransport import ProtocolMessageAction
from ably.pubsub.types.channelstate import ChannelState
from ably.pubsub.types.connectionstate import ConnectionEvent
from ably.pubsub.types.tokendetails import TokenDetails
from test.ably.testapp import TestApp
from test.ably.utils import BaseAsyncTestCase, random_string

echo_url = 'https://echo.ably.io'


async def auth_callback_failure(options, expect_failure=False):
    realtime = await TestApp.get_ably_realtime(**options)

    state_change = await realtime.connection.once_async()

    if expect_failure:
        assert state_change.current == ConnectionState.FAILED
        assert state_change.reason.status_code == 403
    else:
        assert state_change.current == ConnectionState.DISCONNECTED
        assert state_change.reason.status_code == 401
    assert state_change.reason.code == 80019

    await realtime.close()


class TestRealtimeAuth(BaseAsyncTestCase):
    async def test_auth_valid_api_key(self):
        ably = await TestApp.get_ably_realtime()
        await asyncio.wait_for(ably.connection.once_async(ConnectionState.CONNECTED), timeout=5)
        assert ably.connection.error_reason is None
        response_time_ms = await ably.connection.ping()
        assert response_time_ms is not None
        await ably.close()

    async def test_auth_wrong_api_key(self):
        api_key = "js9de7r:08sdnuvfasd"
        ably = await TestApp.get_ably_realtime(key=api_key)
        state_change = await ably.connection.once_async(ConnectionState.FAILED)
        assert ably.connection.error_reason == state_change.reason
        assert state_change.reason.code == 40101
        assert state_change.reason.status_code == 401
        await ably.close()

    async def test_auth_with_token_string(self):
        rest = await TestApp.get_ably_rest()
        token_details = await rest.auth.request_token()
        ably = await TestApp.get_ably_realtime(token=token_details.token)
        await asyncio.wait_for(ably.connection.once_async(ConnectionState.CONNECTED), timeout=5)
        response_time_ms = await ably.connection.ping()
        assert response_time_ms is not None
        assert ably.connection.error_reason is None
        await ably.close()

    async def test_auth_with_invalid_token_string(self):
        invalid_token = "Sdnurv_some_invalid_token_nkds9r7"
        ably = await TestApp.get_ably_realtime(token=invalid_token)
        state_change = await ably.connection.once_async(ConnectionState.FAILED)
        assert state_change.reason.code == 40101
        assert state_change.reason.status_code == 401
        await ably.close()

    async def test_auth_with_token_details(self):
        rest = await TestApp.get_ably_rest()
        token_details = await rest.auth.request_token()
        ably = await TestApp.get_ably_realtime(token_details=token_details)
        await asyncio.wait_for(ably.connection.once_async(ConnectionState.CONNECTED), timeout=5)
        response_time_ms = await ably.connection.ping()
        assert response_time_ms is not None
        assert ably.connection.error_reason is None
        await ably.close()

    async def test_auth_with_invalid_token_details(self):
        invalid_token_details = TokenDetails(token="invalid-token")
        ably = await TestApp.get_ably_realtime(token_details=invalid_token_details)
        state_change = await ably.connection.once_async(ConnectionState.FAILED)
        assert state_change.reason.code == 40101
        assert state_change.reason.status_code == 401
        await ably.close()

    async def test_auth_with_auth_callback_with_token_request(self):
        rest = await TestApp.get_ably_rest()

        async def callback(params):
            token_details = await rest.auth.create_token_request(token_params=params)
            return token_details

        ably = await TestApp.get_ably_realtime(auth_callback=callback)
        await asyncio.wait_for(ably.connection.once_async(ConnectionState.CONNECTED), timeout=5)
        response_time_ms = await ably.connection.ping()
        assert response_time_ms is not None
        assert ably.connection.error_reason is None
        await ably.close()

    async def test_auth_with_auth_callback_token_with_details(self):
        rest = await TestApp.get_ably_rest()

        async def callback(params):
            token_details = await rest.auth.request_token(token_params=params)
            return token_details

        ably = await TestApp.get_ably_realtime(auth_callback=callback)
        await asyncio.wait_for(ably.connection.once_async(ConnectionState.CONNECTED), timeout=5)
        response_time_ms = await ably.connection.ping()
        assert response_time_ms is not None
        assert ably.connection.error_reason is None
        await ably.close()

    async def test_auth_with_auth_callback_with_token_string(self):
        rest = await TestApp.get_ably_rest()

        async def callback(params):
            token_details = await rest.auth.request_token(token_params=params)
            return token_details.token

        ably = await TestApp.get_ably_realtime(auth_callback=callback)
        await asyncio.wait_for(ably.connection.once_async(ConnectionState.CONNECTED), timeout=5)
        response_time_ms = await ably.connection.ping()
        assert response_time_ms is not None
        assert ably.connection.error_reason is None
        await ably.close()

    async def test_auth_with_auth_callback_invalid_token(self):
        async def callback(params):
            return "invalid token"

        ably = await TestApp.get_ably_realtime(auth_callback=callback)
        state_change = await ably.connection.once_async(ConnectionState.FAILED)
        assert state_change.reason.code == 40101
        assert state_change.reason.status_code == 401
        await ably.close()

    async def test_auth_with_auth_url_json(self):
        rest = await TestApp.get_ably_rest()
        token_details = await rest.auth.request_token()
        token_details_json = json.dumps(token_details.to_dict())
        url_path = f"{echo_url}/?type=json&body={urllib.parse.quote_plus(token_details_json)}"

        ably = await TestApp.get_ably_realtime(auth_url=url_path)
        await asyncio.wait_for(
            ably.connection.once_async(ConnectionState.CONNECTED),
            timeout=5,
        )
        response_time_ms = await ably.connection.ping()
        assert response_time_ms is not None
        assert ably.connection.error_reason is None
        await ably.close()

    async def test_auth_with_auth_url_text_plain(self):
        rest = await TestApp.get_ably_rest()
        token_details = await rest.auth.request_token()
        url_path = f"{echo_url}/?type=text&body={token_details.token}"

        ably = await TestApp.get_ably_realtime(auth_url=url_path)
        await asyncio.wait_for(ably.connection.once_async(ConnectionState.CONNECTED), timeout=5)
        response_time_ms = await ably.connection.ping()
        assert response_time_ms is not None
        assert ably.connection.error_reason is None
        await ably.close()

    async def test_auth_with_auth_url_post(self):
        rest = await TestApp.get_ably_rest()
        token_details = await rest.auth.request_token()
        url_path = f"{echo_url}/?type=json&"

        ably = await TestApp.get_ably_realtime(auth_url=url_path, auth_method='POST',
                                               auth_params=token_details)
        await asyncio.wait_for(ably.connection.once_async(ConnectionState.CONNECTED), timeout=5)
        response_time_ms = await ably.connection.ping()
        assert response_time_ms is not None
        assert ably.connection.error_reason is None
        await ably.close()

    async def test_reauth_while_connected(self):
        rest = await TestApp.get_ably_rest()

        async def callback(params):
            token_details = await rest.auth.request_token(token_params=params)
            return token_details.token

        ably = await TestApp.get_ably_realtime(auth_callback=callback)
        await asyncio.wait_for(ably.connection.once_async(ConnectionState.CONNECTED), timeout=5)

        assert ably.connection.connection_manager.transport
        original_access_token = ably.connection.connection_manager.transport.params.get('accessToken')
        assert original_access_token is not None

        original_send_protocol_message = ably.connection.connection_manager.send_protocol_message
        fut1 = asyncio.Future()

        async def send_protocol_message(protocol_message):
            if protocol_message.get('action') == ProtocolMessageAction.AUTH:
                fut1.set_result(protocol_message)
            await original_send_protocol_message(protocol_message)
        ably.connection.connection_manager.send_protocol_message = send_protocol_message

        fut2 = asyncio.Future()

        def on_update(state_change):
            fut2.set_result(state_change)

        ably.connection.on(ConnectionEvent.UPDATE, on_update)

        await ably.auth.authorize()
        message = await fut1
        new_access_token = message.get('auth').get('accessToken')
        assert new_access_token is not None
        assert new_access_token is not original_access_token

        state_change = await fut2
        assert state_change.current == ConnectionState.CONNECTED
        await ably.close()

    async def test_reauth_while_connecting(self):
        rest = await TestApp.get_ably_rest()

        async def callback(params):
            token_details = await rest.auth.request_token(token_params=params)
            return token_details.token

        ably = await TestApp.get_ably_realtime(auth_callback=callback)
        original_transport = await ably.connection.connection_manager.once_async('transport.pending')
        await ably.auth.authorize()
        assert ably.connection.state == ConnectionState.CONNECTED
        assert ably.connection.connection_manager.transport is not original_transport

        await ably.close()

    async def test_reauth_immediately(self):
        rest = await TestApp.get_ably_rest()

        async def callback(params):
            token_details = await rest.auth.request_token(token_params=params)
            return token_details.token

        ably = await TestApp.get_ably_realtime(auth_callback=callback)
        await ably.auth.authorize()
        assert ably.connection.state == ConnectionState.CONNECTED

        await ably.close()

    async def test_capability_change_without_loss_of_continuity(self):
        rest = await TestApp.get_ably_rest()
        channel_name = random_string(5)

        async def callback(params):
            token_details = await rest.auth.request_token(token_params=params)
            return token_details.token

        ably = await TestApp.get_ably_realtime(auth_callback=callback)

        await ably.auth.authorize({"capability": {channel_name: "*"}})

        channel = ably.channels.get(channel_name)
        await channel.attach()

        await ably.auth.authorize({"capability": {channel_name: "*", random_string(5): "*"}})
        await channel.once_async(ChannelState.ATTACHED)

        await ably.close()

    async def test_capability_downgrade(self):
        rest = await TestApp.get_ably_rest()
        channel_name = random_string(5)

        async def callback(params):
            token_details = await rest.auth.request_token(token_params=params)
            return token_details.token

        ably = await TestApp.get_ably_realtime(auth_callback=callback)

        await ably.auth.authorize({"capability": {channel_name: "*"}})

        channel = ably.channels.get(channel_name)
        await channel.attach()

        future = asyncio.Future()

        def on_channel_state_change(state_change):
            future.set_result(state_change)

        channel.on(ChannelState.FAILED, on_channel_state_change)

        await ably.auth.authorize({"capability": {random_string(5): "*"}})

        state_change = await future

        assert state_change.reason is not None
        assert state_change.reason.code == 40160
        assert state_change.reason.status_code == 401

        await ably.close()

    async def test_reauth_inbound_auth_protocol_msg(self):
        rest = await TestApp.get_ably_rest()

        async def callback(params):
            token_details = await rest.auth.request_token(token_params=params)
            return token_details.token

        ably = await TestApp.get_ably_realtime(auth_callback=callback)
        msg = {
            "action": ProtocolMessageAction.AUTH,
        }

        await asyncio.wait_for(ably.connection.once_async(ConnectionState.CONNECTED), timeout=5)
        auth_future = asyncio.Future()

        def on_update(state_change):
            auth_future.set_result(state_change)

        ably.connection.on("update", on_update)
        await ably.connection.connection_manager.transport.on_protocol_message(msg)
        await auth_future
        await ably.close()

    # RSC8a4
    async def test_jwt_reauth(self):
        test_vars = await TestApp.get_test_vars()
        key = test_vars["keys"][0]
        key_name = key["key_name"]
        key_secret = key["key_secret"]

        async def auth_callback(_):
            response = httpx.get(
                echo_url + '/createJWT',
                params={"keyName": key_name, "keySecret": key_secret, "expiresIn": 35}
            )
            return response.text

        ably = await TestApp.get_ably_realtime(auth_callback=auth_callback)

        await asyncio.wait_for(ably.connection.once_async(ConnectionState.CONNECTED), timeout=5)
        original_token_details = ably.auth.token_details
        await ably.connection.once_async(ConnectionEvent.UPDATE)
        assert ably.auth.token_details is not original_token_details

        await ably.close()

    # RTN14b
    async def test_renew_token_single_attempt(self):
        rest = await TestApp.get_ably_rest()

        async def callback(params):
            token_details = await rest.auth.request_token(token_params=params)
            return token_details.token

        ably = await TestApp.get_ably_realtime(auth_callback=callback)
        msg = {
            "action": ProtocolMessageAction.ERROR,
            "error": {
                "code": 40142,
                "statusCode": 401
            }
        }

        transport = await ably.connection.connection_manager.once_async('transport.pending')
        original_token_details = ably.auth.token_details
        await transport.on_protocol_message(msg)
        assert ably.auth.token_details is not original_token_details
        await ably.close()
        await rest.close()

    # RTN14b
    async def test_renew_token_connection_attempt_fails(self):
        rest = await TestApp.get_ably_rest()
        call_count = 0

        async def callback(params):
            nonlocal call_count
            call_count += 1
            params = {"ttl": 1}
            token_details = await rest.auth.request_token(token_params=params)
            return token_details

        ably = await TestApp.get_ably_realtime(auth_callback=callback)

        await ably.connection.once_async(ConnectionState.DISCONNECTED)
        assert call_count == 2
        assert ably.connection.error_reason.code == 40142
        assert ably.connection.error_reason.status_code == 401

        await ably.close()
        await rest.close()

    # RSA4a
    async def test_renew_token_no_renew_means_provided(self):
        rest = await TestApp.get_ably_rest()
        token_details = await rest.auth.request_token(token_params={'ttl': 1})

        ably = await TestApp.get_ably_realtime(token_details=token_details)

        state_change = await ably.connection.once_async(ConnectionState.FAILED)
        assert state_change.reason.code == 40171
        assert state_change.reason.status_code == 403
        await ably.close()
        await rest.close()

    async def test_auth_callback_error(self):
        async def auth_callback(_):
            raise Exception("An error from client code that the authCallback might return")

        await auth_callback_failure({
            'auth_callback': auth_callback
        })

    @pytest.mark.skip(reason="blocked by https://github.com/ably/ably-python/issues/461")
    async def test_auth_callback_timeout(self):
        async def auth_callback(_):
            await asyncio.sleep(10_000)

        await auth_callback_failure({
            'auth_callback': auth_callback,
            'realtime_request_timeout': 100,
        })

    async def test_auth_callback_nothing(self):
        async def auth_callback(_):
            return

        await auth_callback_failure({
            'auth_callback': auth_callback,
        })

    async def test_auth_callback_malformed(self):
        async def auth_callback(_):
            return {"horse": "ebooks"}

        await auth_callback_failure({
            'auth_callback': auth_callback,
        })

    async def test_auth_callback_empty_string(self):
        async def auth_callback(_):
            return ""

        await auth_callback_failure({
            'auth_callback': auth_callback,
        })

    @pytest.mark.skip(reason="blocked by https://github.com/ably/ably-python/issues/461")
    async def test_auth_url_timeout(self):
        await auth_callback_failure({
            "auth_url": "http://10.255.255.1/"
        })

    async def test_auth_url_404(self):
        await auth_callback_failure({
            "auth_url": "http://example.com/404"
        })

    async def test_auth_url_wrong_content_type(self):
        await auth_callback_failure({
            "auth_url": "http://example.com/"
        })

    async def test_auth_url_401(self):
        await auth_callback_failure({
            "auth_url": echo_url + '/respondwith?status=401'
        })

    async def test_auth_url_403(self):
        await auth_callback_failure({
            "auth_url": echo_url + '/respondwith?status=403'
        }, expect_failure=True)

    async def test_auth_url_403_custom_error(self):
        error = json.dumps({
            "error": {
                "some_custom": "error",
            }
        })

        await auth_callback_failure({
            "auth_url": echo_url + '/respondwith?status=403&body=' + urllib.parse.quote_plus(error)
        }, expect_failure=True)

    # RTN15h2
    async def test_renew_token_single_attempt_upon_disconnection(self):
        rest = await TestApp.get_ably_rest()

        async def callback(params):
            token_details = await rest.auth.request_token(token_params=params)
            return token_details.token

        ably = await TestApp.get_ably_realtime(auth_callback=callback)
        msg = {
            "action": ProtocolMessageAction.DISCONNECTED,
            "error": {
                "code": 40142,
                "statusCode": 401
            }
        }

        await asyncio.wait_for(ably.connection.once_async(ConnectionState.CONNECTED), timeout=5)
        original_token_details = ably.auth.token_details
        assert ably.connection.connection_manager.transport
        await ably.connection.connection_manager.transport.on_protocol_message(msg)
        assert ably.auth.token_details is not original_token_details
        await ably.close()
        await rest.close()

    # RTN15h1
    async def test_renew_token_no_renew_means_provided_upon_disconnection(self):
        rest = await TestApp.get_ably_rest()
        token_details = await rest.auth.request_token()

        ably = await TestApp.get_ably_realtime(token_details=token_details)

        state_change = await asyncio.wait_for(ably.connection.once_async(ConnectionState.CONNECTED), timeout=5)
        msg = {
            "action": ProtocolMessageAction.DISCONNECTED,
            "error": {
                "code": 40142,
                "statusCode": 401
            }
        }
        assert ably.connection.connection_manager.transport
        await ably.connection.connection_manager.transport.on_protocol_message(msg)

        state_change = await ably.connection.once_async(ConnectionState.FAILED)
        assert state_change.reason.code == 40171
        assert state_change.reason.status_code == 403
        await ably.close()
        await rest.close()

    async def test_renew_token_single_attempt_on_resume(self):
        rest = await TestApp.get_ably_rest()

        async def callback(params):
            token_details = await rest.auth.request_token(token_params=params)
            return token_details.token

        ably = await TestApp.get_ably_realtime(auth_callback=callback)
        msg = {
            "action": ProtocolMessageAction.ERROR,
            "error": {
                "code": 40142,
                "statusCode": 401
            }
        }

        await asyncio.wait_for(ably.connection.once_async(ConnectionState.CONNECTED), timeout=5)
        connection_key = ably.connection.connection_details.connection_key
        await ably.connection.connection_manager.transport.dispose()
        ably.connection.connection_manager.notify_state(ConnectionState.DISCONNECTED)

        transport = await ably.connection.connection_manager.once_async('transport.pending')
        assert ably.connection.connection_manager.transport.params["resume"] == connection_key

        original_token_details = ably.auth.token_details
        await transport.on_protocol_message(msg)
        assert ably.auth.token_details is not original_token_details
        await ably.close()
        await rest.close()

    async def test_renew_token_no_renew_means_provided_on_resume(self):
        rest = await TestApp.get_ably_rest()
        token_details = await rest.auth.request_token()

        ably = await TestApp.get_ably_realtime(token_details=token_details)

        msg = {
            "action": ProtocolMessageAction.DISCONNECTED,
            "error": {
                "code": 40142,
                "statusCode": 401
            }
        }

        await asyncio.wait_for(ably.connection.once_async(ConnectionState.CONNECTED), timeout=5)
        connection_key = ably.connection.connection_details.connection_key
        await ably.connection.connection_manager.transport.dispose()
        ably.connection.connection_manager.notify_state(ConnectionState.DISCONNECTED)

        state_change = await asyncio.wait_for(ably.connection.once_async(ConnectionState.CONNECTED), timeout=5)
        assert ably.connection.connection_manager.transport.params["resume"] == connection_key

        assert ably.connection.connection_manager.transport
        await ably.connection.connection_manager.transport.on_protocol_message(msg)

        state_change = await ably.connection.once_async(ConnectionState.FAILED)
        assert state_change.reason.code == 40171
        assert state_change.reason.status_code == 403
        await ably.close()
        await rest.close()

    # Request a token using client_id, then initialize a connection without one,
    # and check that the connection inherits the client_id from the token_details
    async def test_auth_client_id_inheritance_auth_callback(self):
        rest = await TestApp.get_ably_rest()
        client_id = 'test_client_id'

        async def auth_callback(_):
            return await rest.auth.request_token({"client_id": client_id})

        realtime = await TestApp.get_ably_realtime(auth_callback=auth_callback)

        # RTC4a
        assert realtime.auth.client_id is None

        await realtime.connection.once_async(ConnectionState.CONNECTED)

        assert realtime.auth.client_id == client_id

        await realtime.close()
        await rest.close()

    # Rest token generation with client_id, then connecting with a
    # different client_id, should fail with a library-generated message
    # (RSA15a, RSA15c)
    async def test_auth_client_id_mismatch(self):
        rest = await TestApp.get_ably_rest()
        client_id = 'test_client_id'

        token_details = await rest.auth.request_token({"client_id": client_id})

        realtime = await TestApp.get_ably_realtime(token_details=token_details, client_id="WRONG")

        assert realtime.auth.client_id is None

        state_change = await realtime.connection.once_async(ConnectionState.FAILED)

        assert state_change.reason.code == 40102

        await realtime.close()
        await rest.close()

    # Rest token generation with clientId '*', then connecting with just the
    # token string and a different clientId, should succeed (RSA15b)
    async def test_auth_client_id_wildcard_token(self):
        rest = await TestApp.get_ably_rest()
        client_id = 'test_client_id'

        token_details = await rest.auth.request_token({"client_id": "*"})

        realtime = await TestApp.get_ably_realtime(token_details=token_details, client_id=client_id)

        assert realtime.auth.client_id is None

        await realtime.connection.once_async(ConnectionState.CONNECTED)

        assert realtime.auth.client_id == client_id

        await realtime.close()
        await rest.close()

    # Request a token using clientId, then initialize a connection using just the token string,
    # and check that the connection inherits the clientId from the connectionDetails
    async def test_auth_client_id_inheritance_token(self):
        rest = await TestApp.get_ably_rest()
        client_id = 'test_client_id'

        token_details = await rest.auth.request_token({"client_id": client_id})

        realtime = await TestApp.get_ably_realtime(token_details=token_details)

        assert realtime.auth.client_id is None

        await realtime.connection.once_async(ConnectionState.CONNECTED)

        assert realtime.auth.client_id == client_id

        await realtime.close()
        await rest.close()
