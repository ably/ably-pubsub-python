# Upgrade / Migration Guide

## Version 3.x to 4.0.0

The package is now published to PyPI as `ably-pubsub-server` rather than `ably`, and
it installs into `ably.pubsub` rather than `ably`. Both `ably` and `ably.pubsub` are
[namespace packages](https://peps.python.org/pep-0420/) shared with the other
`ably-*` distributions, so neither exports anything of its own — the whole public
API is reached through `ably.pubsub.server`.

### Installation

Example 3.x:
```sh
pip install ably
```

Example 4.0.0:
```sh
pip install ably-pubsub-server
```

### Imports

Example 3.x code:
```python
from ably import AblyRealtime, AblyRest
```

Example 4.0.0 code:
```python
from ably.pubsub.server import create_http_client, create_realtime_client
```

The synchronous, HTTP-only flavour moves the same way:

Example 3.x code:
```python
from ably.sync import AblyRestSync
```

Example 4.0.0 code:
```python
from ably.pubsub.server.sync import create_http_client
```

Anything imported from a submodule gains the same `pubsub` segment — for
instance `ably.types.message` becomes `ably.pubsub.types.message`, and
`ably.sync.types.message` becomes `ably.pubsub.sync.types.message`.

`api_version` and `lib_version` are still re-exported from
`ably.pubsub.server`, and now also live in `ably.pubsub.version`.

### Clients are built by factories

`AblyRest` and `AblyRealtime` are internal in 4.0.0 and raise `TypeError` if
constructed directly (`AblyRest` is also renamed to `AblyHttp`, to match the
factory that builds it). Build clients through the factories instead, which
take the same arguments:

Example 3.x code:
```python
rest = AblyRest(key='xxx')
realtime = AblyRealtime(key='xxx')
```

Example 4.0.0 code:
```python
rest = create_http_client(key='xxx')
realtime = create_realtime_client(key='xxx')
```

Where you previously annotated against `AblyRest` or `AblyRealtime`, use the
prototypes the factories return — `ably.pubsub.server.PubSubHttpClient` and
`ably.pubsub.server.PubSubRealtimeClient`. These are `typing.Protocol` definitions
describing the client surface, so `Protocol` support raises the minimum
supported Python to 3.8 (which the CI matrix and README already assumed).

## Version 2.x to 3.0.0

The 3.0.0 version of ably-python introduces several breaking changes to improve the realtime experience and align the API with the Ably specification. These include:

  - The realtime channel publish method now uses WebSocket connection instead of REST
  - `ably.realtime.realtime_channel` module renamed to `ably.realtime.channel`
  - `ChannelOptions` moved to `ably.types.channeloptions`
  - REST publish returns publish result with message serials instead of Response object

### The realtime channel publish method now uses WebSocket

In previous versions, publishing messages on a realtime channel would use the REST API. In version 3.0.0, realtime channels now publish messages over the WebSocket connection, which is more efficient and provides better consistency.

This change is mostly transparent to users, but you should be aware that:
- Messages are now published through the realtime connection
- You will receive publish results containing message serials
- The behavior is now consistent with other Ably SDKs

### Module rename: `ably.realtime.realtime_channel` to `ably.realtime.channel`

If you were importing from `ably.realtime.realtime_channel`, you will need to update your imports:

Example 2.x code:
```python
from ably.realtime.realtime_channel import RealtimeChannel
```

Example 3.0.0 code:
```python
from ably.realtime.channel import RealtimeChannel
```

### `ChannelOptions` moved to `ably.types.channeloptions`

The `ChannelOptions` class has been moved to a new location for better organization.

Example 2.x code:
```python
from ably.realtime.realtime_channel import ChannelOptions
```

Example 3.0.0 code:
```python
from ably.types.channeloptions import ChannelOptions
```

### REST publish returns publish result with serials

The REST `publish` method now returns a publish result object containing the message serial(s) instead of a raw Response object with `status_code`.

Example 2.x code:
```python
response = await channel.publish('event', 'message')
print(response.status_code)  # 201
```

Example 3.0.0 code:
```python
result = await channel.publish('event', 'message')
print(result.serials)  # message serials
```

### Client options: `endpoint` replaces `environment`, `rest_host`, and `realtime_host`

The `environment`, `rest_host`, and `realtime_host` client options have been deprecated in favor of a single `endpoint` option for better consistency and simplicity.

Example 2.x code:
```python
# Using environment
rest_client = AblyRest(key='api:key', environment='custom')

# Or using rest_host
rest_client = AblyRest(key='api:key', rest_host='custom.ably.net')

# For realtime
realtime_client = AblyRealtime(key='api:key', realtime_host='custom.ably.net')
```

Example 3.0.0 code:
```python
# Using environment
rest_client = AblyRest(key='api:key', endpoint='custom')

# Using endpoint for REST
rest_client = AblyRest(key='api:key', endpoint='custom.ably.net')

# Using endpoint for Realtime
realtime_client = AblyRealtime(key='api:key', endpoint='custom.ably.net')
```

## Version 1.2.x to 2.x

The 2.0 version of ably-python introduces our first Python realtime client. For guidance on how to use the realtime client, refer to the usage examples in the [README](./README.md).

In addition to this, we have also made some minor breaking changes, these include:

  - Added mandatory version param to `AblyRest.request`
  - Changed return type of `AblyRest.stats`
  - Removed `Auth.authorise` (in favour of `Auth.authorize`)
  - Removed `Options.fallback_hosts_use_default`
  - Removed `Crypto.get_default_params(key)` signature.
  - Removed the `client_id` and `extras` kwargs from `Channel.publish`
  - Calling `channels.release()` no longer raises a `KeyError` if the channel does not yet exist

### Added mandatory version param to `AblyRest.request`

If you were using the generic `request` method to query the Ably REST API, you will now need to pass a version string as the third parameter. The version string represents the version of the Ably REST API to use, allowing you to upgrade to newer versions of REST endpoints as soon as they are released.

```python
await rest.request("GET", "/time", "1.2")
```

### Changed return type of `AblyRest.stats`

The return type of the `stats` method has changed so that all statistics are now contained in a single `dict[string, int]` and the json schema for the entries is included in the response:

```python
stats_pages = rest.stats(params)
stat = stats_pages.items[0]
print(stat.schema) # contains the canonical url for the statistics json schema
print(stat.entries["messages.inbound.realtime.all.count"]) # all statistics are now included as fields in the Stats.entries dict
```

### Deprecation of `Auth.authorise`

If you were using `Auth.authorise` before, all you need to do to migrate is switch over to `Auth.authorize` (with a 'z')

### Deprecation of `Options.fallback_hosts_use_default`

This option is no longer required since the correct fallback hosts are inferred from the `environment` option. If you are still using it then you can safely remove it.

### Deprecation of `Crypto.get_default_params(key)` signature

This method now requires a params argument and will raise an error if it is called with just a key. If you were using this signature, you can still call the method using `{'key': key}` as the params argument.

### Deprecation of `client_id` and `extras` kwargs for `Channel.publish`

In order to use these options when publishing a message, you will now need to create an instance of the `Message` class.

Example 1.2.x code:

```python
await channel.publish(name='name', data='data', client_id='client_id', extras={'some': 'extras'})
```

Example 2.x code:
```python
from ably.types.message import Message
message = Message(name='name', data='data', client_id='client_id', extras={'some': 'extras'})
await channel.publish(message)
```

## Version 1.1.1 to 1.2.0

We have made **breaking changes** in the version 1.2 release of this SDK.

In this guide we aim to highlight the main differences you will encounter when migrating your code from the interfaces we were offering prior to the version 1.2.0 release.

These include:

 - Deprecation of support for Python versions 3.4, 3.5 and 3.6
 - New, asynchronous API
 - Deprecated synchronous API

### Deprecation of Python 3.4, 3.5 and 3.6

The minimum version of Python has increased to 3.7.
You may need to upgrade your environment in order to use this newer version of this SDK.
To see which versions of Python we test the SDK against, please look at our
[GitHub workflows](.github/workflows).

### Asynchronous API

The 1.2.0 version introduces a breaking change, which changes the way of interacting with the SDK from synchronous to asynchronous, using [the `asyncio` foundational library](https://docs.python.org/3.7/library/asyncio.html) to provide support for `async`/`await` syntax.
Because of this breaking change, every call that interacts with the Ably REST API must be refactored to this asynchronous way.

For backwards compatibility, in ably-python 2.0.2 we have added a backwards compatible REST client so that you can still use the synchronous version of the REST interface if you are migrating forwards from version 1.1.
In order to use the synchronous variant, you can import the `AblyRestSync` constructor from `ably.sync`:

```python
from ably.sync import AblyRestSync

def main():
    ably = AblyRestSync('api:key')
    channel = ably.channels.get("channel_name")
    channel.publish('event', 'message')

if __name__ == "__main__":
    main()
```

#### Publishing Messages

This old style, synchronous example:

```python
from ably import AblyRest

def main():
    ably = AblyRest('api:key')
    channel = ably.channels.get("channel_name")
    channel.publish('event', 'message')

if __name__ == "__main__":
    main()
```

Must now be replaced with this new style, asynchronous form:

```python
import asyncio
from ably import AblyRest

async def main():
    async with AblyRest('api:key') as ably:
        channel = ably.channels.get("channel_name")
        await channel.publish('event', 'message')

if __name__ == "__main__":
    asyncio.run(main())
```

#### Querying History

This old style, synchronous example:

```python
message_page = channel.history() # Returns a PaginatedResult
message_page.items # List with messages from this page
message_page.has_next() # => True, indicates there is another page
message_page.next().items # List with messages from the second page
```

Must now be replaced with this new style, asynchronous form:

```python
message_page = await channel.history() # Returns a PaginatedResult
message_page.items # List with messages from this page
message_page.has_next() # => True, indicates there is another page
next_page = await message_page.next() # Returns a next page
next_page.items # List with messages from the second page
```

#### Querying Presence Members on a Channel

This old style, synchronous example:

```python
members_page = channel.presence.get() # Returns a PaginatedResult
members_page.items
members_page.items[0].client_id # client_id of first member present
```

Must now be replaced with this new style, asynchronous form:

```python
members_page = await channel.presence.get() # Returns a PaginatedResult
members_page.items
members_page.items[0].client_id # client_id of first member present
```

#### Querying Channel Presence History

This old style, synchronous example:

```python
presence_page = channel.presence.history() # Returns a PaginatedResult
presence_page.items
presence_page.items[0].client_id # client_id of first member
```

Must now be replaced with this new style, asynchronous form:

```python
presence_page = await channel.presence.history() # Returns a PaginatedResult
presence_page.items
presence_page.items[0].client_id # client_id of first member
```

#### Generating a Token

This old style, synchronous example:

```python
token_details = client.auth.request_token()
token_details.token # => "xVLyHw.CLchevH3hF....MDh9ZC_Q"
new_client = AblyRest(token=token_details)
```

Must now be replaced with this new style, asynchronous form:

```python
token_details = await client.auth.request_token()
token_details.token # => "xVLyHw.CLchevH3hF....MDh9ZC_Q"
new_client = AblyRest(token=token_details)
await new_client.close()
```

#### Generating a TokenRequest

This old style, synchronous example:

```python
token_request = client.auth.create_token_request(
    {
        'client_id': 'jim',
        'capability': {'channel1': '"*"'},
        'ttl': 3600 * 1000, # ms
    }
)

new_client = AblyRest(token=token_request)
```

Must now be replaced with this new style, asynchronous form:

```python
token_request = await client.auth.create_token_request(
    {
        'client_id': 'jim',
        'capability': {'channel1': '"*"'},
        'ttl': 3600 * 1000, # ms
    }
)

new_client = AblyRest(token=token_request)
await new_client.close()
```

#### Fetching Application Statistics

This old style, synchronous example:

```python
stats = client.stats() # Returns a PaginatedResult
stats.items
```

Must now be replaced with this new style, asynchronous form:

```python
stats = await client.stats() # Returns a PaginatedResult
stats.items
await client.close()
```

#### Fetching the Ably Service Time

This old style, synchronous example:

```python
client.time()
```

Must now be replaced with this new style, asynchronous form:

```python
await client.time()
await client.close()
```
