from ably.pubsub.server import AblyRest


def test_http_get_rest_hosts_works_when_fallback_realtime_host_is_set():
    ably = AblyRest(token="foo")
    ably.options.fallback_host = ably.options.get_hosts()[0]
    # Should not raise TypeError
    hosts = ably.http.get_hosts()
    assert isinstance(hosts, list)
    assert all(isinstance(host, str) for host in hosts)


def test_http_get_rest_hosts_works_when_fallback_realtime_host_is_not_set():
    ably = AblyRest(token="foo")
    ably.options.fallback_host = None
    # Should not raise TypeError
    hosts = ably.http.get_hosts()
    assert isinstance(hosts, list)
    assert all(isinstance(host, str) for host in hosts)
