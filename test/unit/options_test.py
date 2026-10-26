import pytest

from ably.pubsub.server import create_http_client
from ably.pubsub.types.options import Options
from ably.pubsub.util.exceptions import AblyException


# TO3k1-3: the deprecated environment, rest_host and realtime_host options are omitted,
# and with them the duplicate auth_token and the unused connection_state_ttl
@pytest.mark.parametrize('option', ['environment', 'rest_host', 'realtime_host', 'auth_token',
                                    'connection_state_ttl'])
def test_options_should_reject_removed_options(option):
    with pytest.raises(TypeError):
        Options(**{option: 'foo'})


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


# RSC1b: invalid arguments are a 40106, and still a ValueError as they were in 3.x
@pytest.mark.parametrize('kwargs, status_code', [
    ({}, 401),
    ({'key': 'appId.keyId:keySecret', 'key_name': 'appId.keyId'}, 401),
    ({'token_details': 'not-token-details'}, 401),
    ({'token': 'a-token', 'use_token_auth': False}, 401),
])
def test_invalid_client_arguments_raise_40106(kwargs, status_code):
    with pytest.raises(AblyException) as exinfo:
        create_http_client(**kwargs)
    assert exinfo.value.code == 40106
    assert exinfo.value.status_code == status_code
    assert isinstance(exinfo.value, ValueError)
