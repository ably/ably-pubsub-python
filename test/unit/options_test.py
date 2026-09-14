import pytest

from ably.pubsub.types.options import Options
from ably.pubsub.util.exceptions import AblyException


# REC1b1: endpoint is incompatible with deprecated options
def test_options_should_fail_early_with_incompatible_client_options():
    # REC1b1: endpoint with environment
    with pytest.raises(AblyException) as exinfo:
        Options(endpoint="foo", environment="foo")
    assert exinfo.value.code == 40106

    # REC1b1: endpoint with rest_host
    with pytest.raises(AblyException) as exinfo:
        Options(endpoint="foo", rest_host="foo")
    assert exinfo.value.code == 40106

    # REC1b1: endpoint with realtime_host
    with pytest.raises(AblyException) as exinfo:
        Options(endpoint="foo", realtime_host="foo")
    assert exinfo.value.code == 40106


# REC1a
def test_options_should_return_the_default_hostnames():
    opts = Options()
    assert opts.get_host() == "main.realtime.ably.net"
    assert "main.a.fallback.ably-realtime.com" in opts.get_fallback_hosts()


# REC1b4
def test_options_should_return_the_correct_routing_policy_hostnames():
    opts = Options(endpoint="foo")
    assert opts.get_host() == "foo.realtime.ably.net"
    assert "foo.a.fallback.ably-realtime.com" in opts.get_fallback_hosts()


# REC1b3
def test_options_should_return_the_correct_nonprod_routing_policy_hostnames():
    opts = Options(endpoint="nonprod:foo")
    assert opts.get_host() == "foo.realtime.ably-nonprod.net"
    assert "foo.a.fallback.ably-realtime-nonprod.com" in opts.get_fallback_hosts()


# REC1b2
def test_options_should_return_the_correct_fqdn_hostnames():
    opts = Options(endpoint="foo.com")
    assert opts.get_host() == "foo.com"
    assert not opts.get_fallback_hosts()


# REC1b2
def test_options_should_return_an_ipv4_address():
    opts = Options(endpoint="127.0.0.1")
    assert opts.get_host() == "127.0.0.1"
    assert not opts.get_fallback_hosts()


# REC1b2
def test_options_should_return_an_ipv6_address():
    opts = Options(endpoint="::1")
    assert opts.get_host() == "::1"


# REC1b2
def test_options_should_return_localhost():
    opts = Options(endpoint="localhost")
    assert opts.get_host() == "localhost"
    assert not opts.get_fallback_hosts()


# REC1c1: environment with rest_host or realtime_host is invalid
def test_options_should_fail_with_environment_and_rest_or_realtime_host():
    # REC1c1: environment with rest_host
    with pytest.raises(AblyException) as exinfo:
        Options(environment="foo", rest_host="bar")
    assert exinfo.value.code == 40106

    # REC1c1: environment with realtime_host
    with pytest.raises(AblyException) as exinfo:
        Options(environment="foo", realtime_host="bar")
    assert exinfo.value.code == 40106


# REC1c2: environment defines production routing policy ID
def test_options_with_environment_should_return_routing_policy_hostnames():
    opts = Options(environment="foo")
    # REC1c2: primary domain is [id].realtime.ably.net
    assert opts.get_host() == "foo.realtime.ably.net"
    # REC2c5: fallback domains for production routing policy ID via environment
    assert "foo.a.fallback.ably-realtime.com" in opts.get_fallback_hosts()
    assert "foo.e.fallback.ably-realtime.com" in opts.get_fallback_hosts()


# REC1d1: rest_host takes precedence for primary domain
def test_options_with_rest_host_should_return_rest_host():
    opts = Options(rest_host="custom.example.com")
    # REC1d1: primary domain is the value of the restHost option
    assert opts.get_host() == "custom.example.com"
    # REC2c6: fallback domains for restHost is empty
    assert not opts.get_fallback_hosts()


# REC1d2: realtime_host if rest_host not specified
def test_options_with_realtime_host_should_return_realtime_host():
    opts = Options(realtime_host="custom.example.com")
    # REC1d2: primary domain is the value of the realtimeHost option
    assert opts.get_host() == "custom.example.com"
    # REC2c6: fallback domains for realtimeHost is empty
    assert not opts.get_fallback_hosts()


# REC1d1: rest_host takes precedence over realtime_host
def test_options_with_rest_host_takes_precedence_over_realtime_host():
    opts = Options(rest_host="rest.example.com", realtime_host="realtime.example.com")
    # REC1d1: restHost takes precedence
    assert opts.get_host() == "rest.example.com"
    # REC2c6: fallback domains is empty
    assert not opts.get_fallback_hosts()


# REC2a2: fallback_hosts value is used when specified
def test_options_with_fallback_hosts_should_use_specified_hosts():
    custom_fallbacks = ["fallback1.example.com", "fallback2.example.com"]
    opts = Options(fallback_hosts=custom_fallbacks)
    # REC2a2: the set of fallback domains is given by the value of the fallbackHosts option
    fallbacks = opts.get_fallback_hosts()
    assert len(fallbacks) == 2
    assert "fallback1.example.com" in fallbacks
    assert "fallback2.example.com" in fallbacks



# REC2a2: empty fallback_hosts array is respected
def test_options_with_empty_fallback_hosts_should_have_no_fallbacks():
    opts = Options(fallback_hosts=[])
    # REC2a2: empty array means no fallbacks
    assert opts.get_fallback_hosts() == []


# REC2c1: Default fallback hosts for main endpoint
def test_options_default_fallback_hosts():
    opts = Options()
    fallbacks = opts.get_fallback_hosts()
    # REC2c1: default fallback hosts
    assert len(fallbacks) == 5
    assert "main.a.fallback.ably-realtime.com" in fallbacks
    assert "main.b.fallback.ably-realtime.com" in fallbacks
    assert "main.c.fallback.ably-realtime.com" in fallbacks
    assert "main.d.fallback.ably-realtime.com" in fallbacks
    assert "main.e.fallback.ably-realtime.com" in fallbacks


# REC2c3: Non-production routing policy fallback hosts
def test_options_nonprod_fallback_hosts():
    opts = Options(endpoint="nonprod:test")
    fallbacks = opts.get_fallback_hosts()
    # REC2c3: nonprod fallback hosts
    assert len(fallbacks) == 5
    assert "test.a.fallback.ably-realtime-nonprod.com" in fallbacks
    assert "test.b.fallback.ably-realtime-nonprod.com" in fallbacks
    assert "test.c.fallback.ably-realtime-nonprod.com" in fallbacks
    assert "test.d.fallback.ably-realtime-nonprod.com" in fallbacks
    assert "test.e.fallback.ably-realtime-nonprod.com" in fallbacks


# REC2c4: Production routing policy fallback hosts
def test_options_prod_routing_policy_fallback_hosts():
    opts = Options(endpoint="custom")
    fallbacks = opts.get_fallback_hosts()
    # REC2c4: production routing policy fallback hosts
    assert len(fallbacks) == 5
    assert "custom.a.fallback.ably-realtime.com" in fallbacks
    assert "custom.b.fallback.ably-realtime.com" in fallbacks
    assert "custom.c.fallback.ably-realtime.com" in fallbacks
    assert "custom.d.fallback.ably-realtime.com" in fallbacks
    assert "custom.e.fallback.ably-realtime.com" in fallbacks


# REC2c2: Explicit hostname (FQDN) has empty fallback hosts
def test_options_fqdn_no_fallback_hosts():
    opts = Options(endpoint="custom.example.com")
    # REC2c2: explicit hostname has empty fallback
    assert opts.get_fallback_hosts() == []


# REC2c2: IPv6 address has empty fallback hosts
def test_options_ipv6_no_fallback_hosts():
    opts = Options(endpoint="::1")
    # REC2c2: explicit hostname has empty fallback
    assert opts.get_fallback_hosts() == []


# REC2c2: localhost has empty fallback hosts
def test_options_localhost_no_fallback_hosts():
    opts = Options(endpoint="localhost")
    # REC2c2: explicit hostname has empty fallback
    assert opts.get_fallback_hosts() == []
