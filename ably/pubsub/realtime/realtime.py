import asyncio
import logging
from typing import Optional

from ably.pubsub.http.http import DefaultPubSubHttpClient
from ably.pubsub.prototypes import PubSubRealtimeClient
from ably.pubsub.realtime.channel import Channels
from ably.pubsub.realtime.connection import Connection, ConnectionState
from ably.pubsub.util.construction import reject_direct_construction

log = logging.getLogger(__name__)


class DefaultPubSubRealtimeClient(DefaultPubSubHttpClient, PubSubRealtimeClient):
    """
    The default :class:`~ably.pubsub.prototypes.PubSubRealtimeClient` implementation.

    Built by :func:`ably.pubsub.server.create_realtime_client`, which is the
    only way to construct one.

    Attributes
    ----------
    loop: AbstractEventLoop
        asyncio running event loop
    auth: Auth
        authentication object
    options: Options
        auth options object
    connection: Connection
        realtime connection object
    channels: Channels
        realtime channel object

    Methods
    -------
    connect()
        Establishes the realtime connection
    close()
        Closes the realtime connection
    """

    def __init__(self, key: Optional[str] = None, loop: Optional[asyncio.AbstractEventLoop] = None, **kwargs):
        """Constructs a PubSubRealtimeClient object using an Ably API key.

        Parameters
        ----------
        key: str
            A valid ably API key string
        loop: AbstractEventLoop, optional
            asyncio running event loop
        auto_connect: bool
            When true, the client connects to Ably as soon as it is instantiated.
            You can set this to false and explicitly connect to Ably using the
            connect() method. The default is true.
        **kwargs: client options
            endpoint: str
                Endpoint specifies either a routing policy name or fully qualified domain name to connect to Ably.
            realtime_host: str
                Deprecated: this property is deprecated and will be removed in a future version.
                Enables a non-default Ably host to be specified for realtime connections.
                For development environments only. The default value is realtime.ably.io.
            environment: str
                Deprecated: this property is deprecated and will be removed in a future version.
                Enables a custom environment to be used with the Ably service. Defaults to `production`
            realtime_request_timeout: float
                Timeout (in milliseconds) for the wait of acknowledgement for operations performed via a realtime
                connection. Operations include establishing a connection with Ably, or sending a HEARTBEAT,
                CONNECT, ATTACH, DETACH or CLOSE request. The default is 10 seconds(10000 milliseconds).
            disconnected_retry_timeout: float
                If the connection is still in the DISCONNECTED state after this delay, the client library will
                attempt to reconnect automatically. The default is 15 seconds.
            channel_retry_timeout: float
                When a channel becomes SUSPENDED following a server initiated DETACHED, after this delay, if the
                channel is still SUSPENDED and the connection is in CONNECTED, the client library will attempt to
                re-attach the channel automatically. The default is 15 seconds.
            fallback_hosts: list[str]
                An array of fallback hosts to be used in the case of an error necessitating the use of an
                alternative host. If you have been provided a set of custom fallback hosts by Ably, please specify
                them here.
            connection_state_ttl: float
                The duration that Ably will persist the connection state for when a Realtime client is abruptly
                disconnected.
            suspended_retry_timeout: float
                When the connection enters the SUSPENDED state, after this delay, if the state is still SUSPENDED,
                the client library attempts to reconnect automatically. The default is 30 seconds.
            connectivity_check_url: string
                Override the URL used by the realtime client to check if the internet is available.
                In the event of a failure to connect to the primary endpoint, the client will send a
                GET request to this URL to check if the internet is available. If this request returns
                a success response the client will attempt to connect to a fallback host.
        Raises
        ------
        ValueError
            If no authentication key is not provided
        """
        reject_direct_construction(type(self), 'ably.pubsub.server.create_realtime_client')

        if loop is None:
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                log.warning('Realtime client created outside event loop')

        self._is_realtime: bool = True

        # RTC1
        super().__init__(key, loop=loop, **kwargs)

        self.key = key
        self.__connection = Connection(self)
        self.__channels = Channels(self)

        # RTN3
        if self.options.auto_connect:
            self.connection.connection_manager.request_state(ConnectionState.CONNECTING, force=True)

    # RTC15
    def connect(self) -> None:
        """Establishes a realtime connection.

        Explicitly calling connect() is unnecessary unless the autoConnect attribute of the ClientOptions object
        is false. Unless already connected or connecting, this method causes the connection to open, entering the
        CONNECTING state.
        """
        log.info('Realtime.connect() called')
        # RTC15a
        self.connection.connect()

    # RTC16
    async def close(self) -> None:
        """Causes the connection to close, entering the closing state.
        Once closed, the library will not attempt to re-establish the
        connection without an explicit call to connect()
        """
        log.info('Realtime.close() called')
        # RTC16a
        await self.connection.close()
        await super().close()

    # RTC2
    @property
    def connection(self) -> Connection:
        """Returns the realtime connection object"""
        return self.__connection

    # RTC3, RTS1
    @property
    def channels(self) -> Channels:
        """Returns the realtime channel object"""
        return self.__channels
