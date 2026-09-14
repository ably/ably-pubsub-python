class Defaults:
    protocol_version = "5"

    connectivity_check_url = "https://internet-up.ably-realtime.com/is-the-internet-up.txt"
    endpoint = 'main'

    port = 80
    tls_port = 443
    connect_timeout = 15000
    disconnect_timeout = 10000
    suspended_timeout = 60000
    comet_recv_timeout = 90000
    comet_send_timeout = 10000
    realtime_request_timeout = 10000
    channel_retry_timeout = 15000
    disconnected_retry_timeout = 15000
    connection_state_ttl = 120000
    suspended_retry_timeout = 30000

    transports = []  # ["web_socket", "comet"]

    http_max_retry_count = 3

    fallback_retry_timeout = 600000  # 10min

    @staticmethod
    def get_port(options):
        if options.tls:
            if options.tls_port:
                return options.tls_port
            else:
                return Defaults.tls_port
        else:
            if options.port:
                return options.port
            else:
                return Defaults.port

    @staticmethod
    def get_scheme(options):
        if options.tls:
            return "https"
        else:
            return "http"

    @staticmethod
    def get_hostname(endpoint):
        if "." in endpoint or "::" in endpoint or "localhost" in endpoint:
            return endpoint

        if endpoint.startswith("nonprod:"):
            return endpoint[len("nonprod:"):] + ".realtime.ably-nonprod.net"

        return endpoint + ".realtime.ably.net"

    @staticmethod
    def get_fallback_hosts(endpoint="main"):
        if "." in endpoint or "::" in endpoint or "localhost" in endpoint:
            return []

        if endpoint.startswith("nonprod:"):
            root = endpoint.replace("nonprod:", "")
            return [
                root + ".a.fallback.ably-realtime-nonprod.com",
                root + ".b.fallback.ably-realtime-nonprod.com",
                root + ".c.fallback.ably-realtime-nonprod.com",
                root + ".d.fallback.ably-realtime-nonprod.com",
                root + ".e.fallback.ably-realtime-nonprod.com",
            ]

        return [
            endpoint + ".a.fallback.ably-realtime.com",
            endpoint + ".b.fallback.ably-realtime.com",
            endpoint + ".c.fallback.ably-realtime.com",
            endpoint + ".d.fallback.ably-realtime.com",
            endpoint + ".e.fallback.ably-realtime.com",
        ]
