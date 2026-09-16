import logging
import random
from abc import ABC, abstractmethod

from ably.transport.defaults import Defaults
from ably.types.authoptions import AuthOptions
from ably.util.exceptions import AblyException

log = logging.getLogger(__name__)


class VCDiffDecoder(ABC):
    """
    The VCDiffDecoder class defines the interface for delta decoding operations.

    This class serves as an abstract base class for implementing delta decoding
    algorithms, which are used to generate target bytes from compressed delta
    bytes and base bytes. Subclasses of this class should implement the decode
    method to handle the specifics of delta decoding. The decode method typically
    takes a delta bytes and base bytes as input and returns the decoded output.

    """
    @abstractmethod
    def decode(self, delta: bytes, base: bytes) -> bytes:
        pass


class Options(AuthOptions):
    def __init__(self, client_id=None, log_level=0, tls=True, rest_host=None, realtime_host=None, port=0,
                 tls_port=0, use_binary_protocol=True, queue_messages=True, recover=False, endpoint=None,
                 environment=None, http_open_timeout=None, http_request_timeout=None,
                 realtime_request_timeout=None, http_max_retry_count=None, http_max_retry_duration=None,
                 fallback_hosts=None, fallback_retry_timeout=None, disconnected_retry_timeout=None,
                 idempotent_rest_publishing=None, loop=None, auto_connect=True,
                 suspended_retry_timeout=None, connectivity_check_url=None,
                 channel_retry_timeout=Defaults.channel_retry_timeout, add_request_ids=False,
                 vcdiff_decoder: VCDiffDecoder = None, transport_params=None, test_options=None,
                 **kwargs):

        super().__init__(**kwargs)

        # REC1b1: endpoint is incompatible with deprecated options
        if endpoint is not None:
            if environment is not None or rest_host is not None or realtime_host is not None:
                raise AblyException(
                    message='endpoint is incompatible with any of environment, rest_host or realtime_host',
                    status_code=400,
                    code=40106,
                )

        # TODO check these defaults
        if fallback_retry_timeout is None:
            fallback_retry_timeout = Defaults.fallback_retry_timeout

        if realtime_request_timeout is None:
            realtime_request_timeout = Defaults.realtime_request_timeout

        if disconnected_retry_timeout is None:
            disconnected_retry_timeout = Defaults.disconnected_retry_timeout

        if connectivity_check_url is None:
            connectivity_check_url = Defaults.connectivity_check_url

        connection_state_ttl = Defaults.connection_state_ttl

        if suspended_retry_timeout is None:
            suspended_retry_timeout = Defaults.suspended_retry_timeout

        if environment is not None and rest_host is not None:
            raise AblyException(
                message='specify rest_host or environment, not both',
                status_code=400,
                code=40106,
            )

        if environment is not None and realtime_host is not None:
            raise AblyException(
                message='specify realtime_host or environment, not both',
                status_code=400,
                code=40106,
            )

        if idempotent_rest_publishing is None:
            from ably import api_version
            idempotent_rest_publishing = api_version >= '1.2'

        if environment is not None and endpoint is None:
            log.warning("environment client option is deprecated, please use endpoint instead")
            endpoint = environment

        # REC1d: restHost or realtimeHost option
        # REC1d1: restHost takes precedence over realtimeHost
        if rest_host is not None and endpoint is None:
            log.warning("rest_host client option is deprecated, please use endpoint instead")
            endpoint = rest_host
        elif realtime_host is not None and endpoint is None:
            # REC1d2: realtimeHost if restHost not specified
            log.warning("realtime_host client option is deprecated, please use endpoint instead")
            endpoint = realtime_host

        if endpoint is None:
            endpoint = Defaults.endpoint

        self.__client_id = client_id
        self.__log_level = log_level
        self.__tls = tls
        self.__port = port
        self.__tls_port = tls_port
        self.__use_binary_protocol = use_binary_protocol
        self.__queue_messages = queue_messages
        self.__recover = recover
        self.__endpoint = endpoint
        self.__http_open_timeout = http_open_timeout
        self.__http_request_timeout = http_request_timeout
        self.__realtime_request_timeout = realtime_request_timeout
        self.__http_max_retry_count = http_max_retry_count
        self.__http_max_retry_duration = http_max_retry_duration
        # Field for internal use only
        self.__fallback_host = None
        self.__fallback_hosts = fallback_hosts
        self.__fallback_retry_timeout = fallback_retry_timeout
        self.__disconnected_retry_timeout = disconnected_retry_timeout
        self.__channel_retry_timeout = channel_retry_timeout
        self.__idempotent_rest_publishing = idempotent_rest_publishing
        self.__loop = loop
        self.__auto_connect = auto_connect
        self.__connection_state_ttl = connection_state_ttl
        self.__suspended_retry_timeout = suspended_retry_timeout
        self.__connectivity_check_url = connectivity_check_url
        self.__add_request_ids = add_request_ids
        self.__vcdiff_decoder = vcdiff_decoder
        self.__transport_params = transport_params or {}
        self.__test_options = test_options
        self.__hosts = self.__get_hosts()

    @property
    def client_id(self):
        return self.__client_id

    @client_id.setter
    def client_id(self, value):
        self.__client_id = value

    @property
    def log_level(self):
        return self.__log_level

    @log_level.setter
    def log_level(self, value):
        self.__log_level = value

    @property
    def tls(self):
        return self.__tls

    @tls.setter
    def tls(self, value):
        self.__tls = value

    @property
    def port(self):
        return self.__port

    @port.setter
    def port(self, value):
        self.__port = value

    @property
    def tls_port(self):
        return self.__tls_port

    @tls_port.setter
    def tls_port(self, value):
        self.__tls_port = value

    @property
    def use_binary_protocol(self):
        return self.__use_binary_protocol

    @use_binary_protocol.setter
    def use_binary_protocol(self, value):
        self.__use_binary_protocol = value

    @property
    def queue_messages(self):
        return self.__queue_messages

    @queue_messages.setter
    def queue_messages(self, value):
        self.__queue_messages = value

    @property
    def recover(self):
        return self.__recover

    @recover.setter
    def recover(self, value):
        self.__recover = value

    @property
    def endpoint(self):
        return self.__endpoint

    @property
    def http_open_timeout(self):
        return self.__http_open_timeout

    @http_open_timeout.setter
    def http_open_timeout(self, value):
        self.__http_open_timeout = value

    @property
    def http_request_timeout(self):
        return self.__http_request_timeout

    @property
    def realtime_request_timeout(self):
        return self.__realtime_request_timeout

    @http_request_timeout.setter
    def http_request_timeout(self, value):
        self.__http_request_timeout = value

    @property
    def http_max_retry_count(self):
        return self.__http_max_retry_count

    @http_max_retry_count.setter
    def http_max_retry_count(self, value):
        self.__http_max_retry_count = value

    @property
    def http_max_retry_duration(self):
        return self.__http_max_retry_duration

    @http_max_retry_duration.setter
    def http_max_retry_duration(self, value):
        self.__http_max_retry_duration = value

    @property
    def fallback_hosts(self):
        return self.__fallback_hosts

    @property
    def fallback_retry_timeout(self):
        return self.__fallback_retry_timeout

    @property
    def disconnected_retry_timeout(self):
        return self.__disconnected_retry_timeout

    @property
    def channel_retry_timeout(self):
        return self.__channel_retry_timeout

    @property
    def idempotent_rest_publishing(self):
        return self.__idempotent_rest_publishing

    @property
    def loop(self):
        return self.__loop

    # RTC1b
    @property
    def auto_connect(self):
        return self.__auto_connect

    @property
    def connection_state_ttl(self):
        return self.__connection_state_ttl

    @connection_state_ttl.setter
    def connection_state_ttl(self, value):
        self.__connection_state_ttl = value

    @property
    def suspended_retry_timeout(self):
        return self.__suspended_retry_timeout

    @property
    def connectivity_check_url(self):
        return self.__connectivity_check_url

    @property
    def fallback_host(self):
        """
        For internal use only, can be deleted in future
        """
        return self.__fallback_host

    @fallback_host.setter
    def fallback_host(self, value):
        """
        For internal use only, can be deleted in future
        """
        self.__fallback_host = value

    @property
    def add_request_ids(self):
        return self.__add_request_ids

    @property
    def vcdiff_decoder(self):
        return self.__vcdiff_decoder

    @property
    def transport_params(self):
        return self.__transport_params

    @property
    def test_options(self):
        return self.__test_options

    def __get_hosts(self):
        """
        Return the list of hosts as they should be tried. First comes the main
        host. Then the fallback hosts in random order.
        The returned list will have a length of up to http_max_retry_count.
        """
        host = Defaults.get_hostname(self.endpoint)
        # REC2: Determine fallback hosts
        fallback_hosts = self.get_fallback_hosts()

        http_max_retry_count = self.http_max_retry_count
        if http_max_retry_count is None:
            http_max_retry_count = Defaults.http_max_retry_count

        # Shuffle
        fallback_hosts = list(fallback_hosts)
        random.shuffle(fallback_hosts)
        self.__fallback_hosts = fallback_hosts

        # First main host
        hosts = [host] + fallback_hosts
        hosts = hosts[:http_max_retry_count]
        return hosts

    def get_hosts(self):
        return self.__hosts

    def get_host(self):
        return self.__hosts[0]

    # REC2: Various client options collectively determine a set of fallback domains
    def get_fallback_hosts(self):
        # REC2a: If the fallbackHosts client option is specified
        if self.__fallback_hosts is not None:
            # REC2a2: the set of fallback domains is given by the value of the fallbackHosts option
            return self.__fallback_hosts

        # REC2c: Otherwise, the set of fallback domains is defined implicitly by the options
        # used to define the primary domain as specified in (REC1)
        return Defaults.get_fallback_hosts(self.endpoint)
