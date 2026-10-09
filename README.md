![Ably Pub/Sub Python Header](images/pythonSDK-github.png)
[![PyPI version](https://badge.fury.io/py/ably-pubsub-server.svg)](https://pypi.org/project/ably-pubsub-server/)
[![License](https://img.shields.io/github/license/ably/ably-pubsub-python)](https://github.com/ably/ably-pubsub-python/blob/main/LICENSE)


# Ably Pub/Sub Python SDK

Build any realtime experience using Ably’s Pub/Sub Python SDK.

Ably Pub/Sub provides flexible APIs that deliver features such as pub-sub messaging, message history, presence, and push notifications. Utilizing Ably’s realtime messaging platform, applications benefit from its highly performant, reliable, and scalable infrastructure.

Find out more:

* [Ably Pub/Sub docs.](https://ably.com/docs/basics)
* [Ably Pub/Sub examples.](https://ably.com/examples?product=pubsub)

---

## Getting started

Everything you need to get started with Ably:

* [Getting started with Pub/Sub using Python.](https://ably.com/docs/getting-started/python)
* [SDK Setup for Python.](https://ably.com/docs/getting-started/setup?lang=python)

---

## Supported platforms

Ably aims to support a wide range of platforms. If you experience any compatibility issues, open an issue in the repository or contact [Ably support](https://ably.com/support).

The following platforms are supported:

| Platform | Support                  |
|----------|--------------------------|
| Python | Python 3.7+ through 3.14 |

> [!NOTE]
> This SDK works across all major operating platforms (Linux, macOS, Windows) as long as Python 3.7+ is available.

> [!IMPORTANT]
> SDK versions < 2.0.0 are [deprecated](https://ably.com/docs/platform/deprecate/protocol-v1).

---

## Installation

To get started with your project, install the package:

```sh
pip install ably-pubsub-server
```

The package installs into `ably.pubsub`, and the whole public API is reached
through `ably.pubsub.server`:

```python
from ably.pubsub.server import create_http_client, create_realtime_client
```

Clients are built by these factories rather than by constructing a class, so
that the package a client comes from names the side your application runs on.
Annotate against the prototypes they return, `PubSubHttpClient` and
`PubSubRealtimeClient`.

The synchronous, HTTP-only flavour lives alongside it:

```python
from ably.pubsub.server.sync import create_http_client
```

Both `ably` and `ably.pubsub` are [namespace packages](https://peps.python.org/pep-0420/)
shared with the other `ably-*` distributions, so neither exports anything
itself — always import from `ably.pubsub.server`.

> [!NOTE]
Install [Python](https://www.python.org/downloads/) version 3.8 or greater.

## Usage

The following code connects to Ably's realtime messaging service, subscribes to a channel to receive messages, and publishes a test message to that same channel.

```python
from ably.pubsub.server import create_realtime_client

# Initialize Ably Realtime client
async with create_realtime_client(key='your-ably-api-key', client_id='me') as realtime_client:
    # Wait for connection to be established
    await realtime_client.connection.once_async('connected')
    print('Connected to Ably')
    
    # Get a reference to the 'test-channel' channel
    channel = realtime_client.channels.get('test-channel')
    
    # Subscribe to all messages published to this channel
    def on_message(message):
        print(f'Received message: {message.data}')
    
    await channel.subscribe(on_message)
    
    # Publish a test message to the channel
    await channel.publish('test-event', 'hello world')
```

### LiveObjects

LiveObjects keeps shared, mutable state on a channel: maps and counters that every client
attached to it reads, updates and subscribes to. The channel needs the object modes, and
`channel.object.get()` attaches it, waits for the objects to sync, and returns the root map.
Values are read through a typed view of their path — `as_live_map()`, `as_live_counter()` or
`as_primitive()` — and reads are synchronous; writes are awaited.

```python
from ably.pubsub.server import ChannelMode, ChannelOptions, LiveCounter, LiveMap, create_realtime_client

async with create_realtime_client(key='your-ably-api-key') as realtime_client:
    channel = realtime_client.channels.get(
        'my-objects',
        ChannelOptions(modes=[ChannelMode.OBJECT_SUBSCRIBE, ChannelMode.OBJECT_PUBLISH]),
    )

    # Attach, wait for the objects to sync, and get the root map
    root = await channel.object.get()

    # Create objects by setting them on the root
    await root.set('visits', LiveCounter.create(0))
    await root.set('profile', LiveMap.create({'name': 'Alice', 'theme': 'dark'}))

    # Read through a typed view of the path
    visits = root.get('visits').as_live_counter()
    print(visits.value())                                     # 0.0
    print(root.at('profile.name').as_primitive().value(str))  # Alice

    # Subscribe to changes at a path
    def on_change(event):
        print(f'{event.object.path()} changed')

    subscription = root.get('visits').subscribe(on_change)

    # Mutate
    await visits.increment(5)

    # Batch several writes into a single message
    async with root.get('profile').as_live_map().batch() as profile:
        profile.set('name', 'Bob')
        profile.remove('theme')

    subscription.unsubscribe()
```

## Releases

The [CHANGELOG.md](https://github.com/ably/ably-pubsub-python/blob/main/CHANGELOG.md) contains details of the latest releases for this SDK. You can also view all Ably releases on [changelog.ably.com](https://changelog.ably.com).

---

## Contribute

Read the [CONTRIBUTING.md](./CONTRIBUTING.md) guidelines to contribute to Ably.

---

## Support, feedback, and troubleshooting

For help or technical support, visit Ably's [support page](https://ably.com/support) or [GitHub Issues](https://github.com/ably/ably-pubsub-python/issues) for community-reported bugs and discussions.

### Full Realtime support unavailable

This SDK currently supports only [Ably REST](https://ably.com/docs/rest) and basic realtime message subscriptions. To access full [Ably Realtime](https://ably.com/docs/realtime) features in Python, consider using the [MQTT adapter](https://ably.com/docs/mqtt).

