"""Construction and teardown for the clients that derived tests drive."""

from ably import AblyRest
from ably.types.testoptions import TestOptions

DEFAULT_KEY = 'app.key:secret'

CREDENTIAL_OPTIONS = ('key', 'token', 'token_details', 'auth_callback', 'auth_url', 'key_name')

__open_clients = []


def rest_client(mock_http, **kwargs):
    """A REST client whose HTTP calls `mock_http` serves.

    Stands in for the specifications' `install_mock(mock_http)` followed by
    `Rest(options: ...)`. Credentials default to a key where a specification
    does not name any. The client is closed when the test ends.
    """
    if not any(option in kwargs for option in CREDENTIAL_OPTIONS):
        kwargs['key'] = DEFAULT_KEY
    client = AblyRest(test_options=TestOptions(http_transport=mock_http.as_transport()), **kwargs)
    __open_clients.append(client)
    return client


async def close_open_clients():
    while __open_clients:
        await __open_clients.pop().close()
