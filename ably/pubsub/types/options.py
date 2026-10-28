import logging
import random
from abc import ABC, abstractmethod

from ably.pubsub.transport.defaults import Defaults
from ably.pubsub.types.authoptions import AuthOptions

log = logging.getLogger(__name__)


def seconds_to_ms(seconds):
    """Converts a timing option from seconds to the milliseconds the clock counts in.

    This is the one place a timing option is converted. It rounds to the microsecond
    rather than truncating, so 0.0015 is 1.5 ms rather than 1, and float error cannot
    leave 0.1 a hair over 100 ms, where a timer would miss a deadline the clock is
    advanced to exactly. A whole number of milliseconds comes back as an int.
    """
    ms = round(seconds * 1000, 3)
    return int(ms) if ms == int(ms) else ms


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
    """The client options, as the factories in `ably.pubsub.server` document them.

    The timing options are in seconds, where the Ably specification counts
    milliseconds, and each name ends in `_seconds` to say so. Each reads back the value
    in effect, its default if it was not given:

    - `http_open_timeout_seconds`: TO3l3 httpOpenTimeout, default 4
    - `http_request_timeout_seconds`: TO3l4 httpRequestTimeout, default 10
    - `http_max_retry_duration_seconds`: TO3l6 httpMaxRetryDuration, default 15
    - `realtime_request_timeout_seconds`: TO3l11 realtimeRequestTimeout, default 10
    - `disconnected_retry_timeout_seconds`: TO3l1 disconnectedRetryTimeout, default 15
    - `suspended_retry_timeout_seconds`: TO3l2 suspendedRetryTimeout, default 30
    - `channel_retry_timeout_seconds`: TO3l7 channelRetryTimeout, default 15
    - `fallback_retry_timeout_seconds`: TO3l10 fallbackRetryTimeout, default 600
    """

    def __init__(self, client_id=None, tls=True, port=0,
                 tls_port=0, use_binary_protocol=True, queue_messages=True, endpoint=None,
                 http_open_timeout_seconds=None, http_request_timeout_seconds=None,
                 realtime_request_timeout_seconds=None, http_max_retry_count=None,
                 http_max_retry_duration_seconds=None,
                 fallback_hosts=None, fallback_retry_timeout_seconds=None, disconnected_retry_timeout_seconds=None,
                 idempotent_rest_publishing=None, loop=None, auto_connect=True,
                 suspended_retry_timeout_seconds=None, connectivity_check_url=None,
                 channel_retry_timeout_seconds=None, add_request_ids=False,
                 vcdiff_decoder: VCDiffDecoder = None, transport_params=None, echo_messages=True,
                 max_message_size=None, _test_options=None, **kwargs):

        super().__init__(**kwargs)

        # TO3l10, TO3l11, TO3l1, TO3l2 and TO3l7 count milliseconds, and these options take
        # seconds. The clock counts milliseconds, which the _ms properties convert to
        if fallback_retry_timeout_seconds is None:
            fallback_retry_timeout_seconds = Defaults.fallback_retry_timeout_seconds

        if realtime_request_timeout_seconds is None:
            realtime_request_timeout_seconds = Defaults.realtime_request_timeout_seconds

        # RTC7: the HTTP defaults are resolved here too, so they read back from the options
        if http_open_timeout_seconds is None:
            http_open_timeout_seconds = Defaults.http_open_timeout_seconds

        if http_request_timeout_seconds is None:
            http_request_timeout_seconds = Defaults.http_request_timeout_seconds

        if http_max_retry_count is None:
            http_max_retry_count = Defaults.http_max_retry_count

        if http_max_retry_duration_seconds is None:
            http_max_retry_duration_seconds = Defaults.http_max_retry_duration_seconds

        if disconnected_retry_timeout_seconds is None:
            disconnected_retry_timeout_seconds = Defaults.disconnected_retry_timeout_seconds

        if connectivity_check_url is None:
            connectivity_check_url = Defaults.connectivity_check_url

        if suspended_retry_timeout_seconds is None:
            suspended_retry_timeout_seconds = Defaults.suspended_retry_timeout_seconds

        if channel_retry_timeout_seconds is None:
            channel_retry_timeout_seconds = Defaults.channel_retry_timeout_seconds

        # TO3l8
        if max_message_size is None:
            max_message_size = Defaults.max_message_size

        if idempotent_rest_publishing is None:
            from ably.pubsub.version import api_version
            idempotent_rest_publishing = api_version >= '1.2'

        # REC1a: the default routing policy. ably-python omits the deprecated environment,
        # rest_host and realtime_host options (TO3k1-3), so REC1c and REC1d do not apply
        if endpoint is None:
            endpoint = Defaults.endpoint

        self.__client_id = client_id
        self.__tls = tls
        self.__port = port
        self.__tls_port = tls_port
        self.__use_binary_protocol = use_binary_protocol
        self.__queue_messages = queue_messages
        self.__echo_messages = echo_messages
        self.__endpoint = endpoint
        self.__http_open_timeout_seconds = http_open_timeout_seconds
        self.__http_request_timeout_seconds = http_request_timeout_seconds
        self.__realtime_request_timeout_seconds = realtime_request_timeout_seconds
        self.__http_max_retry_count = http_max_retry_count
        self.__http_max_retry_duration_seconds = http_max_retry_duration_seconds
        # Field for internal use only
        self.__fallback_host = None
        self.__fallback_hosts = fallback_hosts
        self.__fallback_retry_timeout_seconds = fallback_retry_timeout_seconds
        self.__disconnected_retry_timeout_seconds = disconnected_retry_timeout_seconds
        self.__channel_retry_timeout_seconds = channel_retry_timeout_seconds
        self.__idempotent_rest_publishing = idempotent_rest_publishing
        self.__loop = loop
        self.__auto_connect = auto_connect
        self.__suspended_retry_timeout_seconds = suspended_retry_timeout_seconds
        self.__connectivity_check_url = connectivity_check_url
        self.__add_request_ids = add_request_ids
        self.__vcdiff_decoder = vcdiff_decoder
        self.__transport_params = transport_params or {}
        self.__max_message_size = max_message_size
        self.__test_options = _test_options
        self.__hosts = self.__get_hosts()

    @property
    def client_id(self):
        return self.__client_id

    @client_id.setter
    def client_id(self, value):
        self.__client_id = value

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

    # TO3h
    @property
    def echo_messages(self):
        return self.__echo_messages

    @property
    def endpoint(self):
        return self.__endpoint

    @property
    def http_open_timeout_seconds(self):
        return self.__http_open_timeout_seconds

    @http_open_timeout_seconds.setter
    def http_open_timeout_seconds(self, value):
        self.__http_open_timeout_seconds = value

    @property
    def http_request_timeout_seconds(self):
        return self.__http_request_timeout_seconds

    @property
    def realtime_request_timeout_seconds(self):
        return self.__realtime_request_timeout_seconds

    @property
    def _realtime_request_timeout_ms(self):
        return seconds_to_ms(self.__realtime_request_timeout_seconds)

    @http_request_timeout_seconds.setter
    def http_request_timeout_seconds(self, value):
        self.__http_request_timeout_seconds = value

    @property
    def http_max_retry_count(self):
        return self.__http_max_retry_count

    @http_max_retry_count.setter
    def http_max_retry_count(self, value):
        self.__http_max_retry_count = value

    @property
    def http_max_retry_duration_seconds(self):
        return self.__http_max_retry_duration_seconds

    @http_max_retry_duration_seconds.setter
    def http_max_retry_duration_seconds(self, value):
        self.__http_max_retry_duration_seconds = value

    @property
    def fallback_hosts(self):
        return self.__fallback_hosts

    @property
    def fallback_retry_timeout_seconds(self):
        return self.__fallback_retry_timeout_seconds

    @property
    def _fallback_retry_timeout_ms(self):
        return seconds_to_ms(self.__fallback_retry_timeout_seconds)

    @property
    def disconnected_retry_timeout_seconds(self):
        return self.__disconnected_retry_timeout_seconds

    @property
    def _disconnected_retry_timeout_ms(self):
        return seconds_to_ms(self.__disconnected_retry_timeout_seconds)

    @property
    def channel_retry_timeout_seconds(self):
        return self.__channel_retry_timeout_seconds

    @property
    def _channel_retry_timeout_ms(self):
        return seconds_to_ms(self.__channel_retry_timeout_seconds)

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
    def suspended_retry_timeout_seconds(self):
        return self.__suspended_retry_timeout_seconds

    @property
    def _suspended_retry_timeout_ms(self):
        return seconds_to_ms(self.__suspended_retry_timeout_seconds)

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
    def max_message_size(self):
        return self.__max_message_size

    @property
    def _test_options(self):
        return self.__test_options

    def __get_hosts(self):
        """
        Return the list of hosts as they should be tried. First comes the main
        host. Then the fallback hosts in random order.
        The returned list will hold up to http_max_retry_count fallback hosts.
        """
        host = Defaults.get_hostname(self.endpoint)
        # REC2: Determine fallback hosts
        fallback_hosts = self.get_fallback_hosts()

        # Shuffle
        fallback_hosts = list(fallback_hosts)
        random.shuffle(fallback_hosts)
        self.__fallback_hosts = fallback_hosts

        # First main host, then TO3l5: http_max_retry_count counts the fallback hosts only
        return [host] + fallback_hosts[:self.http_max_retry_count]

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
