from datetime import timedelta

import pytest

from ably.pubsub.server import create_http_client, create_realtime_client
from ably.pubsub.types.options import Options, seconds_to_ms
from ably.pubsub.util.exceptions import AblyException, InvalidArgumentException


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


# TO3l1, TO3l2, TO3l7, TO3l10, TO3l11: the realtime timing options are seconds where the
# specification counts milliseconds, and named for it
REALTIME_TIMING_DEFAULTS = {
    'realtime_request_timeout_seconds': 10,
    'disconnected_retry_timeout_seconds': 15,
    'suspended_retry_timeout_seconds': 30,
    'channel_retry_timeout_seconds': 15,
    'fallback_retry_timeout_seconds': 600,
}


@pytest.mark.parametrize('option, default', REALTIME_TIMING_DEFAULTS.items())
def test_realtime_timing_options_read_back_their_defaults_in_seconds(option, default):
    opts = Options()
    assert getattr(opts, option) == default
    assert getattr(opts, '_' + option.replace('_seconds', '_ms')) == default * 1000


@pytest.mark.parametrize('option', REALTIME_TIMING_DEFAULTS)
def test_realtime_timing_options_read_back_what_was_given(option):
    opts = Options(**{option: 0.25})
    assert getattr(opts, option) == 0.25
    assert getattr(opts, '_' + option.replace('_seconds', '_ms')) == 250


# TO3l3, TO3l4, TO3l6: the HTTP timing options were always seconds, and are now named for it
HTTP_TIMING_DEFAULTS = {
    'http_open_timeout_seconds': 4,
    'http_request_timeout_seconds': 10,
    'http_max_retry_duration_seconds': 15,
}


@pytest.mark.parametrize('option, default', HTTP_TIMING_DEFAULTS.items())
def test_http_timing_options_read_back_their_defaults_in_seconds(option, default):
    assert getattr(Options(), option) == default
    assert getattr(Options(**{option: 2.5}), option) == 2.5


def test_the_http_layer_reads_the_timing_options_in_seconds():
    ably = create_http_client(token='foo', http_open_timeout_seconds=2.5, http_request_timeout_seconds=7)
    assert ably.http.http_open_timeout_seconds == 2.5
    assert ably.http.http_request_timeout_seconds == 7


@pytest.mark.parametrize('option', ['realtime_request_timeout', 'disconnected_retry_timeout',
                                    'suspended_retry_timeout', 'channel_retry_timeout',
                                    'fallback_retry_timeout'])
def test_a_millisecond_name_raises_naming_its_replacement_and_the_value_in_seconds(option):
    with pytest.raises(TypeError) as excinfo:
        Options(**{option: 15000})
    assert str(excinfo.value) == (f'`{option}` was renamed to `{option}_seconds` in 4.0 and is now '
                                  'in seconds (15000 ms → 15)')


@pytest.mark.parametrize('option', ['http_open_timeout', 'http_request_timeout', 'http_max_retry_duration'])
def test_an_http_name_raises_naming_its_replacement(option):
    with pytest.raises(TypeError) as excinfo:
        Options(**{option: 4})
    assert str(excinfo.value) == f'`{option}` was renamed to `{option}_seconds` in 4.0; it is still in seconds'


@pytest.mark.parametrize('value, seconds', [(2500, '2.5'), (100, '0.1'), (1234, '1.234'), (0, '0')])
def test_the_rename_hint_converts_the_value_given(value, seconds):
    with pytest.raises(TypeError, match=f'[(]{value} ms → {seconds}[)]$'):
        Options(disconnected_retry_timeout=value)


@pytest.mark.parametrize('value', ['15000', None, True, float('nan'), float('inf'), timedelta(seconds=15)])
def test_the_rename_hint_falls_back_to_the_default_for_a_value_it_cannot_convert(value):
    with pytest.raises(TypeError, match='[(]15000 ms → 15[)]$'):
        Options(disconnected_retry_timeout=value)


def test_the_factories_raise_the_rename_hint():
    with pytest.raises(TypeError, match='`realtime_request_timeout_seconds`'):
        create_http_client(key='appId.keyId:keySecret', realtime_request_timeout=10000)
    with pytest.raises(TypeError, match='`suspended_retry_timeout_seconds`'):
        create_realtime_client(key='appId.keyId:keySecret', auto_connect=False, suspended_retry_timeout=30000)


@pytest.mark.parametrize('seconds, ms', [
    (15, 15000),
    (0.1, 100),
    (0.3, 300),
    (0.7, 700),
    (2.3, 2300),
    (0.0015, 1.5),
    (0.0005, 0.5),
    (600, 600000),
    (0, 0),
])
def test_seconds_convert_to_milliseconds_exactly(seconds, ms):
    assert seconds_to_ms(seconds) == ms


def test_a_whole_number_of_milliseconds_is_an_int():
    assert type(seconds_to_ms(0.1)) is int
    assert type(seconds_to_ms(15)) is int
    assert type(seconds_to_ms(0.0015)) is float


TIMING_OPTIONS = list(REALTIME_TIMING_DEFAULTS) + list(HTTP_TIMING_DEFAULTS)


@pytest.mark.parametrize('option', TIMING_OPTIONS)
@pytest.mark.parametrize('value', [0, 1, 0.0015, 2.5, 600])
def test_timing_options_accept_finite_non_negative_ints_and_floats(option, value):
    assert getattr(Options(**{option: value}), option) == value


@pytest.mark.parametrize('option', TIMING_OPTIONS)
@pytest.mark.parametrize('value', [True, False, '15', b'15', [15], -1, -0.001, float('nan'), float('inf'),
                                   float('-inf'), timedelta(seconds=15)])
def test_timing_options_reject_anything_else_with_a_40000(option, value):
    with pytest.raises(InvalidArgumentException) as excinfo:
        Options(**{option: value})
    assert excinfo.value.code == 40000
    assert excinfo.value.status_code == 400
    assert isinstance(excinfo.value, ValueError)
    assert option in excinfo.value.message


def test_a_timedelta_is_rejected_with_a_hint():
    # 3.x accepted a timedelta and then failed inside the timer task, so the retry never fired
    with pytest.raises(InvalidArgumentException, match=r'total_seconds\(\)'):
        Options(disconnected_retry_timeout_seconds=timedelta(seconds=15))


def test_none_takes_the_default_rather_than_failing_validation():
    opts = Options(**dict.fromkeys(TIMING_OPTIONS))
    for option, default in {**REALTIME_TIMING_DEFAULTS, **HTTP_TIMING_DEFAULTS}.items():
        assert getattr(opts, option) == default


@pytest.mark.parametrize('option', list(HTTP_TIMING_DEFAULTS))
def test_the_http_timing_setters_validate_too(option):
    opts = Options()
    setattr(opts, option, 0.5)
    assert getattr(opts, option) == 0.5
    with pytest.raises(InvalidArgumentException):
        setattr(opts, option, -1)


def test_the_factories_raise_the_validation_error():
    with pytest.raises(InvalidArgumentException, match='http_request_timeout_seconds'):
        create_http_client(key='appId.keyId:keySecret', http_request_timeout_seconds='10')
    with pytest.raises(InvalidArgumentException, match='channel_retry_timeout_seconds'):
        create_realtime_client(key='appId.keyId:keySecret', auto_connect=False, channel_retry_timeout_seconds=-15)
