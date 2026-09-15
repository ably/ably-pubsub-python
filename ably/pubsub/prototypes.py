"""The shapes of the Pub/Sub clients, as callers see them.

The client classes themselves are internal: they are reachable only through the
factory functions in :mod:`ably.pubsub.server` and :mod:`ably.pubsub.server.sync`,
so that the package a client comes from names the side the application runs on.
These protocols are what those factories are declared to return, and what
application code should annotate against.

They are named "prototypes" rather than "protocols" because this codebase
already uses "protocol" for the Ably wire protocol.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from ably.pubsub.http.http import Http
    from ably.pubsub.http.paginatedresult import HttpPaginatedResponse, PaginatedResult
    from ably.pubsub.realtime.channel import Channels as RealtimeChannels
    from ably.pubsub.realtime.connection import Connection
    from ably.pubsub.rest.auth import Auth
    from ably.pubsub.rest.channel import Channels as RestChannels
    from ably.pubsub.rest.push import Push
    from ably.pubsub.types.options import Options


class RestClient(Protocol):
    """A Pub/Sub client that operates entirely over HTTP.

    Build one with ``create_http_client``, from :mod:`ably.pubsub.server` for the
    asynchronous flavour or :mod:`ably.pubsub.server.sync` for the synchronous one.
    """

    @property
    def auth(self) -> Auth:
        """The authentication object for this client."""
        ...

    @property
    def channels(self) -> RestChannels:
        """The channels container object."""
        ...

    @property
    def client_id(self) -> str | None:
        """The client ID this client authenticates as, if any."""
        ...

    @property
    def http(self) -> Http:
        """The HTTP transport this client sends requests over."""
        ...

    @property
    def options(self) -> Options:
        """The client options this client was built with."""
        ...

    @property
    def push(self) -> Push:
        """The push notification admin object."""
        ...

    async def stats(self, direction: str | None = None, start=None, end=None, params: dict | None = None,
                    limit: int | None = None, paginated=None, unit=None, timeout=None) -> PaginatedResult:
        """Return the stats for this application."""
        ...

    async def time(self, timeout: float | None = None) -> float:
        """Return the current server time in ms since the unix epoch."""
        ...

    async def request(self, method: str, path: str, version: str, params: dict | None = None,
                      body=None, headers=None) -> HttpPaginatedResponse:
        """Make an arbitrary request against the Ably REST API."""
        ...

    async def close(self) -> None:
        """Release the resources this client holds."""
        ...

    async def __aenter__(self) -> RestClient:
        ...

    async def __aexit__(self, *excinfo) -> None:
        ...


class RealtimeClient(RestClient, Protocol):
    """A Pub/Sub client with a persistent realtime connection.

    Everything :class:`RestClient` does, plus subscribing to channels and
    entering presence. Build one with
    :func:`ably.pubsub.server.create_realtime_client`.
    """

    @property
    def channels(self) -> RealtimeChannels:
        """The realtime channels container object."""
        ...

    @property
    def connection(self) -> Connection:
        """The realtime connection object."""
        ...

    def connect(self) -> None:
        """Establish the realtime connection.

        Unnecessary unless the client was built with ``auto_connect=False``.
        """
        ...

    async def close(self) -> None:
        """Close the realtime connection and release the client's resources."""
        ...

    async def __aenter__(self) -> RealtimeClient:
        ...
