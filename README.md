![Ably Pub/Sub Python Header](https://raw.githubusercontent.com/ably/ably-pubsub-python/main/images/pythonSDK-github.png)

[![PyPI: ably-pubsub-server](https://img.shields.io/pypi/v/ably-pubsub-server?label=ably-pubsub-server)](https://pypi.org/project/ably-pubsub-server/)
[![License](https://badgen.net/github/license/ably/ably-pubsub-python)](https://github.com/ably/ably-pubsub-python/blob/main/LICENSE)

# Ably Pub/Sub Python SDK

The Python SDK for [Ably Pub/Sub](https://ably.com/docs/basics): publish and subscribe to channels,
and use message history, presence and LiveObjects, from servers.

## Overview

This SDK provides the server package only, for trusted backends authenticating with an API key.
There is no device package; for end-user devices, use a device SDK such as
[JavaScript](https://github.com/ably/ably-pubsub-js), [Swift/Objective-C](https://github.com/ably/ably-pubsub-cocoa),
[Java/Android](https://github.com/ably/ably-pubsub-java), [.NET](https://github.com/ably/ably-pubsub-dotnet)
or [Flutter](https://github.com/ably/ably-pubsub-flutter).

| Package | Use it for | Entry point |
|---------|-----------|-------------|
| `ably-pubsub-server` | Servers and other trusted backend environments | `create_realtime_client`, `create_http_client` |

## Requirements

Python 3.8 or later (Linux, macOS and Windows).

## Installation

```bash
pip install ably-pubsub-server
```

For channel encryption or delta compression, install the `crypto` or `vcdiff` extra, for example
`pip install "ably-pubsub-server[crypto]"`.

## Quick start

Use an API key on a server. The samples read it from the `ABLY_API_KEY` environment variable; set it
to an API key from your [Ably dashboard](https://ably.com/accounts/any/apps/any/app_keys). The
following code connects, subscribes to a channel, publishes a message to it and waits for the
message to arrive.

```python
import asyncio
import os

from ably.pubsub.server import create_realtime_client


async def main():
    ably_api_key = os.environ['ABLY_API_KEY']
    async with create_realtime_client(key=ably_api_key) as realtime:
        channel = realtime.channels.get('test-channel')
        received = asyncio.get_running_loop().create_future()

        def on_message(message):
            if not received.done():
                received.set_result(message)

        # subscribe() attaches the channel and returns once it is attached.
        await channel.subscribe(on_message)
        await channel.publish('test-event', 'hello world')

        message = await received
        print(f'Received: {message.data}')


asyncio.run(main())
```

Create the realtime client inside a running event loop. Close every client with `async with` or
`await client.close()`.

To publish over HTTP without a realtime connection, create an HTTP client instead:

```python
import asyncio
import os

from ably.pubsub.server import create_http_client


async def main():
    ably_api_key = os.environ['ABLY_API_KEY']
    async with create_http_client(key=ably_api_key) as client:
        await client.channels.get('test-channel').publish('test-event', 'hello world')


asyncio.run(main())
```

For code without an event loop, `ably.pubsub.server.sync.create_http_client` creates a synchronous
HTTP client. There is no synchronous realtime client.

The following endpoint issues token requests. Devices using a device SDK set `authUrl` to its URL,
for example `https://your-server.example.com/ably-auth`:

```python
import os
from contextlib import asynccontextmanager

from ably.pubsub.server import create_http_client
from fastapi import FastAPI

ably_api_key = os.environ['ABLY_API_KEY']
client = create_http_client(key=ably_api_key)


@asynccontextmanager
async def lifespan(app):
    async with client:  # closes the client when the app shuts down
        yield


app = FastAPI(lifespan=lifespan)


@app.get('/ably-auth')
async def ably_auth():
    # Authenticate the caller first. Grant only the operations this user needs.
    user_id = 'me'  # the signed-in user's ID, from your session
    token_request = await client.auth.create_token_request({
        'client_id': user_id,
        'capability': {'test-channel': ['publish', 'subscribe', 'history']},
    })
    return token_request.to_dict()
```

See [token authentication](https://ably.com/docs/auth/token) for how devices use it.

## Migrating from 3.x

Version 4.0 renames the package and creates clients with factory functions.

| | 3.x | 4.0 |
|---|---|---|
| Package | `ably` | `ably-pubsub-server` |
| Import | `from ably import AblyRealtime, AblyRest` | `from ably.pubsub.server import create_realtime_client, create_http_client` |
| Realtime client | `AblyRealtime('key')` | `create_realtime_client(key='key')` |
| HTTP client | `AblyRest('key')` | `create_http_client(key='key')` |

See [UPDATING.md](https://github.com/ably/ably-pubsub-python/blob/main/UPDATING.md#version-3x-to-400) for all other changes.

## Common configuration

Pass options to both factories as keyword arguments.

### Endpoint

`endpoint` selects the Ably host for HTTP requests and the realtime connection. It replaces the
3.x `environment`, `rest_host` and `realtime_host` options.

```python
ably_api_key = os.environ['ABLY_API_KEY']
realtime = create_realtime_client(key=ably_api_key, endpoint='nonprod:sandbox')
```

- Never put a port in `endpoint`: `localhost:8080` is not a hostname and does not resolve.
- Set the port with `tls_port`, or with `port` when TLS is off.
- With TLS off (`tls=False`), use token authentication.

See [UPDATING.md](https://github.com/ably/ably-pubsub-python/blob/main/UPDATING.md#deprecated-and-duplicate-options-are-removed) for how the old
options map to `endpoint`.

### Logging

The SDK logs through Python's standard [`logging`](https://docs.python.org/3/library/logging.html)
module, to the `ably.pubsub` logger. Set the level and add a handler on that logger:

```python
import logging

logger = logging.getLogger('ably.pubsub')
logger.setLevel(logging.DEBUG)
logger.addHandler(logging.StreamHandler())
```

The 3.x `log_level` option is [removed](https://github.com/ably/ably-pubsub-python/blob/main/UPDATING.md#the-log_level-option-is-removed).

### Delta compression

To receive [delta-compressed](https://ably.com/docs/channels/options/deltas) messages:

- Install the `vcdiff` extra.
- Pass an `AblyVCDiffDecoder` to the realtime client as `vcdiff_decoder`.
- Set the `delta` channel parameter to `vcdiff`.

```python
import os

from ably.pubsub.server import AblyVCDiffDecoder, ChannelOptions, create_realtime_client

ably_api_key = os.environ['ABLY_API_KEY']
realtime = create_realtime_client(key=ably_api_key, vcdiff_decoder=AblyVCDiffDecoder())
channel = realtime.channels.get('test-channel', ChannelOptions(params={'delta': 'vcdiff'}))
```

## Live Objects

Use [LiveObjects](https://ably.com/docs/liveobjects) through `channel.object`. Get the channel with
the `OBJECT_SUBSCRIBE` and `OBJECT_PUBLISH` modes. `channel.object.get()` waits for the objects to
sync and returns the root map.

```python
import asyncio
import os

from ably.pubsub.server import ChannelMode, ChannelOptions, create_realtime_client
from ably.pubsub.server.liveobjects import LiveCounter


async def main():
    ably_api_key = os.environ['ABLY_API_KEY']
    async with create_realtime_client(key=ably_api_key) as realtime:
        channel = realtime.channels.get(
            'test-channel',
            ChannelOptions(modes=[ChannelMode.OBJECT_SUBSCRIBE, ChannelMode.OBJECT_PUBLISH]),
        )
        root = await channel.object.get()

        await root.set('visits', LiveCounter.create(0))
        visits = root.get('visits').as_live_counter()
        await visits.increment(5)
        print(f'Visits: {visits.value()}')


asyncio.run(main())
```

## Known limitations

- Connection recovery (the 3.x `recover` option) is not supported.
- Subscription filters and derived channels are not supported.
- Realtime presence has no `history()`. Use `channel.presence.history()` on an HTTP client.
- [Token revocation](https://ably.com/docs/auth/revocation) is not supported.
- A Python client cannot be a [push notification](https://ably.com/docs/push) target. The push
  admin API is supported.

## Further reading

- [Getting started with Pub/Sub using Python](https://ably.com/docs/getting-started/python)
- [Ably Pub/Sub documentation](https://ably.com/docs/basics) and [examples](https://ably.com/examples?product=pubsub)
- [Token authentication](https://ably.com/docs/auth/token)
- [UPDATING.md](https://github.com/ably/ably-pubsub-python/blob/main/UPDATING.md): migrating from 3.x
- [CHANGELOG.md](https://github.com/ably/ably-pubsub-python/blob/main/CHANGELOG.md): release notes; all Ably releases are listed on [changelog.ably.com](https://changelog.ably.com)

## Contributing

Read [CONTRIBUTING.md](https://github.com/ably/ably-pubsub-python/blob/main/CONTRIBUTING.md) before contributing; it also describes the release
process.

## Support, feedback and troubleshooting

For help, visit Ably's [support page](https://ably.com/support). Report bugs and compatibility
problems on [GitHub Issues](https://github.com/ably/ably-pubsub-python/issues).

## License

Licensed under the Apache License, Version 2.0. See [LICENSE](https://github.com/ably/ably-pubsub-python/blob/main/LICENSE).
