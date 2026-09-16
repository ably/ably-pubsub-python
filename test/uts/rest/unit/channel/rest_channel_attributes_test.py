"""Derived from uts/rest/unit/channel/rest_channel_attributes.md in ably/specification.

Spec points: RSL7, RSL8, RSL8a, RSL9, CHD2, CHD2a, CHD2b, CHS2, CHS2a, CHS2b,
CHO2, CHO2a, CHM2, CHM2a, CHM2b, CHM2c, CHM2d, CHM2e, CHM2f, CHM2g, CHM2h
"""

from ably.types.channeldetails import ChannelDetails
from ably.types.channeloptions import ChannelOptions
from test.uts.helpers.client import rest_client
from test.uts.helpers.deviations import deviation
from test.uts.helpers.mock_http import MockHttpClient


def channel_details_body(channel_id, is_active=True, metrics=None):
    """A channel status body shaped the way `ChannelDetails.from_dict` walks it.

    `ChannelDetails`, `ChannelStatus` and `ChannelOccupancy` each descend into the
    next level unguarded, so `status.occupancy.metrics` has to be present.
    """
    return {
        'channelId': channel_id,
        'status': {
            'isActive': is_active,
            'occupancy': {'metrics': metrics if metrics is not None else {
                'connections': 0,
                'publishers': 0,
                'subscribers': 0,
                'presenceConnections': 0,
                'presenceMembers': 0,
                'presenceSubscribers': 0,
            }},
        },
    }


def capture_and_respond(captured_requests, body):
    def on_request(request):
        captured_requests.append(request)
        request.respond_with(200, body)

    return on_request


# UTS: rest/unit/RSL9/channel-name-attribute-0
async def test_rsl9_channel_name_attribute():
    mock_http = MockHttpClient(
        on_connection_attempt=lambda conn: conn.respond_with_success(),
        on_request=lambda request: request.respond_with(200, []),
    )
    client = rest_client(mock_http)

    channel = client.channels.get('my-channel')
    assert channel.name == 'my-channel'

    # Also works with special characters
    channel2 = client.channels.get('namespace:channel-name')
    assert channel2.name == 'namespace:channel-name'


# UTS: rest/unit/RSL7/setoptions-updates-options-0
@deviation
async def test_rsl7_setoptions_updates_options():
    # DEVIATION: the REST channel has no `set_options`. `ably/rest/channel.py` exposes only an
    # `options` property whose setter expects the mapping of keyword arguments that
    # `Channels.get` collected, so a `ChannelOptions` raises `TypeError` from
    # `'cipher' in options`. `ably/realtime/channel.py` does implement `set_options`.
    mock_http = MockHttpClient(
        on_connection_attempt=lambda conn: conn.respond_with_success(),
        on_request=lambda request: request.respond_with(200, []),
    )
    client = rest_client(mock_http)

    channel = client.channels.get('test-RSL7')

    await channel.set_options(ChannelOptions())

    # setOptions completes without error (indicates success)


# UTS: rest/unit/RSL7/setoptions-stores-options-1
@deviation
async def test_rsl7_setoptions_stores_options():
    # DEVIATION: as above, `set_options` is absent from the REST channel.
    mock_http = MockHttpClient(
        on_connection_attempt=lambda conn: conn.respond_with_success(),
        on_request=lambda request: request.respond_with(200, []),
    )
    client = rest_client(mock_http)

    channel = client.channels.get('test-RSL7-store')

    # Set options - the effect of channel options is primarily on encryption (RSL5),
    # which is not exercised here; the call completing is what the spec checks.
    await channel.set_options(ChannelOptions())

    assert channel.options is not None


# UTS: rest/unit/RSL8/status-get-correct-endpoint-0
async def test_rsl8_status_get_correct_endpoint():
    captured_requests = []
    mock_http = MockHttpClient(
        on_connection_attempt=lambda conn: conn.respond_with_success(),
        on_request=capture_and_respond(captured_requests, channel_details_body('test-RSL8')),
    )
    client = rest_client(mock_http)

    channel = client.channels.get('test-RSL8')

    await channel.status()

    # Correct HTTP method and path
    assert len(captured_requests) == 1
    request = captured_requests[0]
    assert request.method == 'GET'
    assert request.url.path.endswith('/channels/test-RSL8')


# UTS: rest/unit/RSL8/status-special-chars-encoded-1
async def test_rsl8_status_special_chars_encoded():
    channel_name = 'namespace:my channel'
    captured_requests = []
    mock_http = MockHttpClient(
        on_connection_attempt=lambda conn: conn.respond_with_success(),
        on_request=capture_and_respond(captured_requests, channel_details_body(channel_name)),
    )
    client = rest_client(mock_http)

    channel = client.channels.get(channel_name)

    await channel.status()

    assert len(captured_requests) == 1
    request = captured_requests[0]
    assert request.method == 'GET'

    # DEVIATION: the spec asserts the path ends with "/channels/" + encode_uri_component(name).
    # `Channel.status` in `ably/rest/channel.py` interpolates the raw name into
    # `f'/channels/{self.name}'` and encodes nothing; the escaping visible below is httpx
    # normalising the URL on the way out. For this name the wire form still reaches the right
    # channel, differing from encodeURIComponent only in leaving ":" unescaped, which RFC 3986
    # permits in a path segment. Names containing "/", "?" or "#" are genuinely mis-routed --
    # see the report accompanying this suite.
    assert str(request.url).endswith('/channels/namespace:my%20channel')
    # request.url.path is the percent-decoded path, so it carries the name verbatim
    assert request.url.path == f'/channels/{channel_name}'


# UTS: rest/unit/RSL8a/status-returns-channel-details-0
async def test_rsl8a_status_returns_channel_details():
    mock_http = MockHttpClient(
        on_connection_attempt=lambda conn: conn.respond_with_success(),
        on_request=lambda request: request.respond_with(200, channel_details_body(
            'test-RSL8a',
            metrics={
                'connections': 5,
                'publishers': 2,
                'subscribers': 3,
                'presenceConnections': 1,
                'presenceMembers': 1,
                'presenceSubscribers': 0,
            },
        )),
    )
    client = rest_client(mock_http)

    channel = client.channels.get('test-RSL8a')

    result = await channel.status()

    # Result is a ChannelDetails object (CHD1)
    assert isinstance(result, ChannelDetails)

    # CHD2a: channelId attribute
    assert result.channel_id == 'test-RSL8a'

    # CHD2b: status attribute is a ChannelStatus (CHS1)
    assert result.status is not None
    assert result.status.is_active is True

    # CHS2b: occupancy metrics
    assert result.status.occupancy is not None
    assert result.status.occupancy.metrics.connections == 5
    assert result.status.occupancy.metrics.publishers == 2
    assert result.status.occupancy.metrics.subscribers == 3


# UTS: rest/unit/CHM2/parses-all-metrics-fields-0
async def test_chm2_parses_all_metrics_fields():
    mock_http = MockHttpClient(
        on_connection_attempt=lambda conn: conn.respond_with_success(),
        on_request=lambda request: request.respond_with(200, channel_details_body(
            'test-CHM2-all-fields',
            metrics={
                'connections': 10,
                'presenceConnections': 7,
                'presenceMembers': 4,
                'presenceSubscribers': 3,
                'publishers': 6,
                'subscribers': 8,
                'objectPublishers': 2,
                'objectSubscribers': 5,
            },
        )),
    )
    client = rest_client(mock_http)

    channel = client.channels.get('test-CHM2-all-fields')

    result = await channel.status()

    # CHD2a: channelId
    assert result.channel_id == 'test-CHM2-all-fields'

    # CHD2b + CHS2a: status.isActive
    assert result.status is not None
    assert result.status.is_active is True

    # CHS2b + CHO2a: occupancy.metrics
    assert result.status.occupancy is not None
    assert result.status.occupancy.metrics is not None

    metrics = result.status.occupancy.metrics

    # CHM2a: connections
    assert metrics.connections == 10

    # CHM2b: presenceConnections
    assert metrics.presence_connections == 7

    # CHM2c: presenceMembers
    assert metrics.presence_members == 4

    # CHM2d: presenceSubscribers
    assert metrics.presence_subscribers == 3

    # CHM2e: publishers
    assert metrics.publishers == 6

    # CHM2f: subscribers
    assert metrics.subscribers == 8

    # DEVIATION: CHM2g asserts metrics.objectPublishers == 2 and CHM2h
    # metrics.objectSubscribers == 5. `ChannelMetrics` in `ably/types/channeldetails.py`
    # models only the six fields above, so both are dropped on parsing and no accessor
    # exists. Asserting their absence so the test turns red once they are added.
    assert not hasattr(metrics, 'object_publishers')
    assert not hasattr(metrics, 'object_subscribers')


# UTS: rest/unit/CHM2/zero-and-missing-metrics-1
async def test_chm2_zero_and_missing_metrics():
    # The response omits objectPublishers and objectSubscribers (CHM2g, CHM2h) to simulate
    # an older server that does not include these fields. All other metrics are explicitly zero.
    mock_http = MockHttpClient(
        on_connection_attempt=lambda conn: conn.respond_with_success(),
        on_request=lambda request: request.respond_with(200, channel_details_body(
            'test-CHM2-defaults',
            is_active=False,
            metrics={
                'connections': 0,
                'presenceConnections': 0,
                'presenceMembers': 0,
                'presenceSubscribers': 0,
                'publishers': 0,
                'subscribers': 0,
            },
        )),
    )
    client = rest_client(mock_http)

    channel = client.channels.get('test-CHM2-defaults')

    result = await channel.status()

    # CHD2a: channelId
    assert result.channel_id == 'test-CHM2-defaults'

    # CHS2a: isActive can be false
    assert result.status.is_active is False

    metrics = result.status.occupancy.metrics

    # CHM2a-f: explicit zero values are parsed correctly
    assert metrics.connections == 0
    assert metrics.presence_connections == 0
    assert metrics.presence_members == 0
    assert metrics.presence_subscribers == 0
    assert metrics.publishers == 0
    assert metrics.subscribers == 0

    # DEVIATION: CHM2g-h asserts the missing fields default to 0. `ChannelMetrics` models
    # neither field, so neither accessor exists. `ChannelMetrics.from_dict` also reads every
    # field with a bare `obj.get(name)`, so any metric the response omits parses as None
    # rather than 0.
    assert not hasattr(metrics, 'object_publishers')
    assert not hasattr(metrics, 'object_subscribers')
