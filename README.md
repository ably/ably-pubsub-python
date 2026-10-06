![Ably Pub/Sub Python Header](images/pythonSDK-github.png)
[![PyPI version](https://badge.fury.io/py/ably.svg)](https://pypi.org/project/ably/)
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
| Python | Python 3.8+ through 3.14 |

> [!NOTE]
> This SDK works across all major operating platforms (Linux, macOS, Windows) as long as Python 3.8+ is available.

> [!IMPORTANT]
> SDK versions < 2.0.0 are [deprecated](https://ably.com/docs/platform/deprecate/protocol-v1).

---

## Installation

To get started with your project, install the package:

```sh
pip install ably
```

> [!NOTE]
> Install [Python](https://www.python.org/downloads/) version 3.8 or greater.

## Usage

The following code connects to Ably's realtime messaging service, subscribes to a channel to receive messages, and publishes a test message to that same channel.

```python
# Initialize Ably Realtime client
async with AblyRealtime('your-ably-api-key', client_id='me') as realtime_client:
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

## Releases

The [CHANGELOG.md](https://github.com/ably/ably-pubsub-python/blob/main/CHANGELOG.md) contains details of the latest releases for this SDK. You can also view all Ably releases on [changelog.ably.com](https://changelog.ably.com).

---

## Contribute

Read the [CONTRIBUTING.md](./CONTRIBUTING.md) guidelines to contribute to Ably.

---

## Support, feedback, and troubleshooting

For help or technical support, visit Ably's [support page](https://ably.com/support) or [GitHub Issues](https://github.com/ably/ably-pubsub-python/issues) for community-reported bugs and discussions.

### Feature support

This SDK supports the Ably Pub/Sub REST and Realtime APIs, including connection and channel lifecycle management, publishing and subscribing, presence, message history, message annotations, channel encryption, and token authentication with in-band re-authentication.

The following features are not currently implemented:

- [Connection recovery](https://ably.com/docs/connect/states) using the `recover` client option.
- Message filtering on subscriptions, and derived channels.
- Presence history, though [channel history](https://ably.com/docs/storage-history/history) is supported.
- [Batch publish](https://ably.com/docs/messages/batch) and batch presence.
- [Token revocation](https://ably.com/docs/auth/revocation).
- [Push notification target](https://ably.com/docs/push) functionality, so a Python client cannot itself receive push notifications. The [push admin API](https://ably.com/docs/api/rest-sdk/push-admin) for registering and managing other devices is supported.
- [LiveObjects](https://ably.com/docs/liveobjects).

> [!NOTE]
> [Delta compression](https://ably.com/docs/channels/options/deltas) requires the `vcdiff` extra (`pip install "ably[vcdiff]"`) and an `AblyVCDiffDecoder` instance passed to the client as `vcdiff_decoder`.

