# Upgrade / Migration Guide

## Version 3.x to 4.0.0

The package is now published to PyPI as `ably-pubsub-server` rather than `ably`, and
it installs into `ably.pubsub` rather than `ably`. Both `ably` and `ably.pubsub` are
[namespace packages](https://peps.python.org/pep-0420/) shared with the other
`ably-*` distributions, so neither exports anything of its own. The whole public
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

Where 3.x left you reaching into submodules such as `ably.types.message` or
`ably.http.paginatedresult`, import from `ably.pubsub.server` instead. It is
the whole public API, and `ably.pubsub.server.sync` is its synchronous
counterpart. The packages beneath them are internal and free to move.

For example, the encryption helpers move from `ably.util.crypto`:

Example 3.x code:
```python
from ably.util.crypto import generate_random_key, get_default_params
```

Example 4.0.0 code:
```python
from ably.pubsub.server import generate_random_key, get_default_params
```

### Clients are built by factories

`AblyRest` and `AblyRealtime` are internal in 4.0.0 and raise `TypeError` if
constructed directly. Build clients through the factories instead, which take the same options
as keyword arguments. The API key is no longer accepted positionally, so pass it as `key=`:

Example 3.x code:
```python
rest = AblyRest(key='xxx')
realtime = AblyRealtime(key='xxx')
```

Example 4.0.0 code:
```python
pubsub_http_client = create_http_client(key='xxx')
pubsub_realtime_client = create_realtime_client(key='xxx')
```

### Type annotations

The client classes are internal, so annotate against the prototypes the
factories are declared to return. Each is exported from the same module as the
factory that returns it.

Example 3.x code:
```python
from ably import AblyRealtime, AblyRest
from ably.sync import AblyRestSync

async def publish(client: AblyRest, name: str) -> None: ...
async def subscribe(client: AblyRealtime, name: str) -> None: ...
def publish_blocking(client: AblyRestSync, name: str) -> None: ...
```

Example 4.0.0 code:
```python
from ably.pubsub.server import PubSubHttpClient, PubSubRealtimeClient
from ably.pubsub.server.sync import PubSubHttpClient as PubSubHttpClientSync

async def publish(client: PubSubHttpClient, name: str) -> None: ...
async def subscribe(client: PubSubRealtimeClient, name: str) -> None: ...
def publish_blocking(client: PubSubHttpClientSync, name: str) -> None: ...
```

### Releasing a realtime channel requires it to be detached

`channels.release(name)` on a realtime client now raises an `AblyException` with code 90011
if the channel is in any state other than `INITIALIZED`, `DETACHED` or `FAILED`, and leaves the
channel as it was. 3.x removed the channel from the collection whatever its state, which could
leave it attached in the Ably service, and later 3.x releases log a deprecation warning when
they do so. Detach the channel, and wait for that to complete, before releasing it:

Example 3.x code:
```python
realtime.channels.release('my-channel')
```

Example 4.0.0 code:
```python
await pubsub_realtime_client.channels.get('my-channel').detach()
pubsub_realtime_client.channels.release('my-channel')
```

### Some errors had their `code` and `status_code` the wrong way round

Ten errors the library raised itself carried the Ably error code in `status_code` and the
HTTP status in `code`. They now carry them the right way round:

| Error | 3.x `status_code`, `code` | 4.0.0 `status_code`, `code` |
|---|---|---|
| Detaching a `FAILED` realtime channel | 90001, 400 | 400, 90001 |
| A detach superseded by an attach | 90000, 409 | 409, 90000 |
| A queued message failed with no reason given | 80000, 500 | 500, 80000 |
| A NACK with no error | 50001, 500 | 500, 50001 |
| A vcdiff delta with no decoder configured | 40019, 40019 | 400, 40019 |
| A vcdiff delta that cannot be decoded | 40018, 40018 | 400, 40018 |
| `ChannelOptions` given params or options that are not a dict | 40000, 400 | 400, 40000 |

If you branch on `code` or `status_code` for any of these, compare against the 4.0.0 values.

### Network errors and timeouts are raised as `AblyException`

In 3.x a request that got no response, because the host could not be reached or did not
answer in time, raised the `httpx` exception itself from most methods, such as `request`,
`publish`, `history` and `auth.authorize`. In 4.0.0 every method raises an `AblyException`:
code 50003 and status 504 for a timeout, and code 80000 and status 500 for any other
network error. The `httpx` exception is its `cause`. A timeout or network error reaching
an `auth_url` is an `AblyException` with code 40170 and status 401, as for any other
`auth_url` failure.

Example 3.x code:
```python
try:
    await rest.channels.get('my-channel').publish('event', 'data')
except httpx.TimeoutException:
    ...
```

Example 4.0.0 code:
```python
try:
    await pubsub_http_client.channels.get('my-channel').publish('event', 'data')
except AblyException as e:
    if e.code == 50003:
        ...
```

### An `AblyException` raised by an `auth_callback` is no longer rewritten

In 3.x any exception an `auth_callback` raised reached the caller as an `AblyException` with
code 40170 and status 401, the original only in its `cause`. In 4.0.0 an `AblyException` the
callback raises reaches the caller unchanged; any other exception is still wrapped as 40170.
On a realtime client, a callback error with status 403 now fails the connection, with an
80019 whose status is 403 and whose `cause` is the callback's error, whether it happens while
connecting, on a reauth or in an explicit `authorize()` call. 3.x went `DISCONNECTED` and
retried. Every 80019 the connection reports now carries the auth provider's error as its
`cause`.

If you check for 40170 after `request_token` or `authorize` to find a failure in your own
callback, check the code your callback raised instead. Raise a status 403 only for a client
that should stop connecting:

Example 4.0.0 code:
```python
async def auth_callback(token_params):
    if not await user_may_connect():
        raise AblyException('Access revoked', 403, 40300)
    return await fetch_token(token_params)
```

### Invalid arguments raise `AblyException`

The factories raised a bare `ValueError` in 3.x when given no means of authenticating, a
`key` together with `key_name` or `key_secret`, a `token_details` that is not a
`TokenDetails`, or `use_token_auth=False` without a key. In 4.0.0 each raises an
`AblyException` with code 40106 and status 401. `push.admin.publish` raised `TypeError`
for a `recipient` or `data` that is not a dict and `ValueError` for an empty one, and now
raises an `AblyException` with code 40000 and status 400 for all four.

These exceptions are also a `ValueError`, so `except ValueError` still catches them, but
`except TypeError` no longer catches the `push.admin.publish` ones:

Example 3.x code:
```python
try:
    await rest.push.admin.publish(recipient, data)
except TypeError:
    ...
```

Example 4.0.0 code:
```python
try:
    await pubsub_http_client.push.admin.publish(recipient, data)
except AblyException as e:
    if e.code == 40000:
        ...
```

### A key no longer overrides `auth_callback`, `auth_url` or a token

A client given a `key` together with an `auth_callback`, `auth_url`, `token` or `token_details`
now uses token auth, and keeps the key only as a means of renewing the token. 3.x used basic
auth with the key whenever one was present, never called the `auth_callback` or `auth_url`,
and discarded a `token` or `token_details` given alongside the key. So a client configured this
way now makes requests to your auth server, or presents the token you gave it, where 3.x did
neither.

To keep using basic auth with the key, pass `use_token_auth=False`:

Example 3.x code:
```python
rest = AblyRest(key='xxx', auth_callback=callback)
```

Example 4.0.0 code:
```python
pubsub_http_client = create_http_client(key='xxx', auth_callback=callback, use_token_auth=False)
```

Or drop the `auth_callback`, `auth_url` or token, which 3.x never used.

### Token params reach an `auth_url` under their wire names

A client with an `auth_url` now sends the token params to it under the names and in the forms
the other Ably SDKs use, in the query string for `GET` and in the form body for `POST`:

- the client ID as `clientId`, where 3.x sent `client_id`
- a `capability` given as a dict or `Capability` as JSON, where 3.x sent its Python repr
- a `ttl` given as a `timedelta` as an integer count of milliseconds, where 3.x sent `1:00:00`

Unset params are left out rather than sent empty. This changes what your auth server receives.
An auth server written for 3.x clients that reads `client_id` must read `clientId` instead, as it
already does for clients built with the other SDKs. There is no transition period in which both
are sent, so update the auth server before, or together with, the clients. The token params
passed to `create_token_request`, `request_token` and `authorize` keep their snake_case names.

Example 3.x auth server code:
```python
client_id = request.args.get('client_id')
```

Example 4.0.0 auth server code:
```python
client_id = request.args.get('clientId')
```

### A realtime client knows its configured `client_id` before it connects

A realtime client built with a `client_id` now reports it from `auth.client_id` as soon as it is
created, as an HTTP client always has. 3.x held `auth.client_id` at `None` until the connection
reached `CONNECTED`. A realtime client built with a `token_details` that carries a client ID
likewise reports that ID straight away.

Because the client ID is known when the first token is requested, a realtime client now passes
it to its `auth_callback` as `client_id` in the token params, and to its `auth_url` as
`clientId`, which 3.x did not do. An auth server or callback that issues tokens from those params
now issues them for that client ID. Check that it does not reject or override a client ID it was
not expecting.

Code that read `auth.client_id` before connecting to tell whether the client was connected
should check `connection.state` instead.

### `authorize()` keeps an explicit `client_id`

A `client_id` passed in the token params to `auth.authorize()` now reaches the token request, the
`auth_callback` or the `auth_url` as given. The client's own client ID is only filled in when the
params name none. 3.x replaced an explicit `client_id` with the client's own whenever the client
had one, and wrote it into the dict the caller passed. The caller's dict is no longer modified.

So a client configured with one client ID that authorizes for another now receives a token for
the one it asked for, and then fails with an `IncompatibleClientIdException` (code 40102), as the
client ID of a client cannot change once configured. 3.x silently issued a token for the
configured client ID instead. Drop the explicit `client_id`, or pass the configured one:

Example 3.x code:
```python
await rest.auth.authorize({'client_id': 'someone-else', 'ttl': 3600000})
```

Example 4.0.0 code:
```python
await pubsub_http_client.auth.authorize({'ttl': 3600000})
```

### A `token_details` whose client ID conflicts with `client_id` is rejected

Creating a client with both a `client_id` and a `token_details` whose own client ID is a different
one, and is not the wildcard `*`, now raises an `IncompatibleClientIdException` (code 40102) from
the factory. 3.x built the client: an HTTP client then sent requests under a token for the other
client ID, and a realtime client failed only once it connected. Make the two agree, or leave
`client_id` out and let the client take the token's.

Example 3.x code:
```python
rest = AblyRest(token_details=token_details_for_bob, client_id='alice')
```

Example 4.0.0 code:
```python
pubsub_http_client = create_http_client(token_details=token_details_for_bob)
```

A bare `token` string carries no client ID the client can read, so it cannot be checked when the
client is created. A realtime client still checks it against the client ID the server reports
when the connection opens, and fails the connection with 40102 if they conflict.

### `TokenDetails.capability` is a JSON string

`TokenDetails.capability` now holds the capability as the JSON string the Ably service returned,
exactly as it was sent, or `None` where none is known. 3.x parsed it into a `Capability`. Wrap
the string in `Capability` where you indexed or compared it:

Example 3.x code:
```python
token_details = await rest.auth.request_token()
operations = token_details.capability['my-channel']
```

Example 4.0.0 code:
```python
from ably.pubsub.server import Capability

token_details = await pubsub_http_client.auth.request_token()
operations = Capability(token_details.capability)['my-channel']
```

`Capability` is unchanged as the way to build a `capability` token param, and its
`add_operation_to_resource` method now works where 3.x raised `AttributeError`. A `TokenDetails`
you construct yourself with a dict or `Capability` stores it as canonical JSON, and
`TokenDetails.to_dict()` now gives the capability as that string rather than as a dict. So an
auth server that returns `to_dict()` to its clients from an `auth_url` now sends the capability
as a JSON string, the form the Ably service itself returns, rather than as a JSON object.

### A `TokenDetails` known only by its token string no longer invents its details

A `TokenDetails` built from a token string alone, whether you construct it yourself, pass a
`token`, or have an `auth_callback` or `auth_url` return a bare token string or JWT, now has
`expires`, `issued` and `capability` set to `None`. 3.x invented an expiry an hour after the
`TokenDetails` was created, an `issued` of `0` and an empty capability. Code that read those
values must handle `None`; the client itself does, and leaves it to the Ably service to report
when such a token has expired.

Example 3.x code:
```python
seconds_left = (rest.auth.token_details.expires - now_ms) / 1000
```

Example 4.0.0 code:
```python
expires = pubsub_http_client.auth.token_details.expires
seconds_left = None if expires is None else (expires - now_ms) / 1000
```

### `default_token_params` apply to `create_token_request()`, and given params replace them

`auth.create_token_request()` called without token params now applies the client's
`default_token_params`, as `request_token()` and `authorize()` already did. 3.x ignored them. So
an auth server whose client is configured with `default_token_params` and which signs token
requests with `create_token_request()` now issues tokens with those defaults, typically a shorter
`ttl` or a narrower `capability` than before. Check that the defaults are what you want your
clients' tokens to carry, or remove them.

Token params passed to `create_token_request()` or `request_token()` now replace the defaults
entirely, as they already did for `authorize()` and as every other Ably SDK does. 3.x merged them
over the defaults key by key in `request_token()`. Take care where a default `capability` or
`ttl` restricted the tokens: a `request_token()` call that names other params no longer carries
them, so its token gets the key's full capability and the service's default `ttl`. Pass every
param you want, including the defaults you still want:

Example 3.x code:
```python
rest = AblyRest(key='xxx', default_token_params={'capability': capability})
await rest.auth.request_token({'ttl': 600000})  # carried the default capability
```

Example 4.0.0 code:
```python
pubsub_http_client = create_http_client(key='xxx', default_token_params={'capability': capability})
await pubsub_http_client.auth.request_token({'ttl': 600000, 'capability': capability})
```

### The HTTP options read back their defaults

`http_open_timeout`, `http_request_timeout`, `http_max_retry_count` and
`http_max_retry_duration` on `client.options` used to read `None` unless you set them, while
the client applied defaults of its own. They now read back the values in effect: 4, 10, 3 and
15 by default. The timeouts and the retry duration are still in seconds, and are renamed
`http_open_timeout_seconds`, `http_request_timeout_seconds` and
`http_max_retry_duration_seconds`, as described below. Code that tested an
option for `None`, to tell whether it had been set, will no longer find it so.

### Requests no longer take a `timeout` argument

`time()`, `stats()`, a REST channel's `publish()`, `publish_message()`, `publish_messages()`
and `publish_name_data()`, `get_message()` on REST and realtime channels, and
`push.admin.publish()` accepted a `timeout` keyword argument that was never applied: every
request used the client's `http_open_timeout` and `http_request_timeout` whatever was passed.
The argument is gone, and passing it raises `TypeError`. `stats()` also loses its unused
`paginated` argument. Set the timeouts on the client instead:

Example 3.x code:
```python
await rest.time(timeout=5)
```

Example 4.0.0 code:
```python
pubsub_http_client = create_http_client(key='xxx', http_request_timeout_seconds=5)
await pubsub_http_client.time()
```

### `http_request_timeout_seconds` bounds writes and connection-pool waits

In 3.x, `http_open_timeout` bounded connecting and `http_request_timeout` bounded each read
of a response, while writing a request body and waiting for a free pooled connection had no
timeout at all. `http_request_timeout_seconds` now bounds those too, so a request stuck writing to,
or waiting for, a wedged connection raises `httpx.TimeoutException` and is retried against a
fallback host instead of hanging. If you publish large bodies over a slow link, raise
`http_request_timeout_seconds` to fit:

```python
pubsub_http_client = create_http_client(key='xxx', http_request_timeout_seconds=30)
```

### `http_max_retry_count` counts fallback hosts only

In 3.x, `http_max_retry_count` capped the total number of hosts a request was tried
against, the primary endpoint included, so the default of 3 meant the primary and two
fallbacks. It now counts fallback hosts only, as in the Ably specification and the other
Ably SDKs: a request goes to the primary endpoint and then to at most
`http_max_retry_count` fallback hosts. The default of 3 therefore tries one more host than
before, and `http_max_retry_count=0`, which used to fail every request, now tries the
primary endpoint alone. To keep the 3.x number of attempts, subtract one:

Example 3.x code:
```python
rest = AblyRest(key='xxx', http_max_retry_count=3)
```

Example 4.0.0 code:
```python
pubsub_http_client = create_http_client(key='xxx', http_max_retry_count=2)
```

### The `log_level` option is removed

`log_level` was stored on the client options and never read, so it changed nothing. It is
gone, and passing it raises `TypeError`. The library logs through Python's standard
`logging` module, to the `ably.pubsub` logger and the loggers beneath it, so configure that
logger instead to set the level or to choose where records go:

Example 3.x code:
```python
rest = AblyRest(key='xxx', log_level=logging.DEBUG)
```

Example 4.0.0 code:
```python
import logging

logger = logging.getLogger('ably.pubsub')
logger.setLevel(logging.DEBUG)
logger.addHandler(logging.StreamHandler())

pubsub_http_client = create_http_client(key='xxx')
```

### Deprecated and duplicate options are removed

These options were deprecated in 3.x, or duplicated another option, and are gone in 4.0.0.
Passing any of them raises `TypeError`:

- `environment`: pass the same value as `endpoint`, so `environment='sandbox'` becomes
  `endpoint='sandbox'`.
- `rest_host` and `realtime_host`: pass the host as `endpoint`, which one host now serves
  for both REST and realtime.
- `auth_token`: pass the token as `token`, the name the factories document. The token is now
  read back as `client.options.token` rather than `client.options.auth_token`.
- `connection_state_ttl`: this was never accepted as an option, and the
  `client.options.connection_state_ttl` property, which nothing read, is removed. The value
  the server sends is on `connection.connection_details.connection_state_ttl`.

Example 3.x code:
```python
rest = AblyRest(key='xxx', environment='sandbox')
realtime = AblyRealtime(key='xxx', realtime_host='custom.ably.example.com')
rest = AblyRest(auth_token='xxx')
```

Example 4.0.0 code:
```python
pubsub_http_client = create_http_client(key='xxx', endpoint='sandbox')
pubsub_realtime_client = create_realtime_client(key='xxx', endpoint='custom.ably.example.com')
pubsub_http_client = create_http_client(token='xxx')
```

### REST publishes are checked against `max_message_size`

`max_message_size` is now a client option, defaulting to 65536 bytes (64 KiB). A publish
whose messages exceed it between them raises an `AblyException` with code 40009 and is not
sent. In 3.x the realtime client checked a fixed 64 KiB limit and REST publishes were not
checked at all, so an oversized REST publish now fails before it reaches Ably rather than
being rejected by the server.

Both clients now measure a message the way the Ably specification does: the length of its
name, client ID and string data, the byte length of binary data, and the length of the JSON
of object data and of extras. 3.x measured the realtime publish as the whole encoded
message, so some realtime publishes that 3.x refused are now sent. Raise the limit only if
your Ably account allows larger messages:

```python
pubsub_http_client = create_http_client(key='xxx', max_message_size=131072)
```

### The `recover` option is removed

The realtime client accepted a `recover` option, documented as resuming an earlier
connection from its recovery key, but connection recovery is not implemented: the option was
stored and never sent, so a client given one always started a fresh connection. It is gone,
and passing it raises `TypeError`. Remove it, and rely on the client's own resumption of a
dropped connection, which is implemented. Connection recovery may return in a minor release,
along with the `recover` option.

Example 3.x code:
```python
realtime = AblyRealtime(key='xxx', recover=recovery_key)
```

Example 4.0.0 code:
```python
pubsub_realtime_client = create_realtime_client(key='xxx')
```

### `PresenceMessage.timestamp` is milliseconds since the epoch

**This change is silent: comparing a timestamp with `==` against a `datetime` now returns
`False` rather than raising.** `PresenceMessage.timestamp` is an `int` of milliseconds since
the unix epoch, as `Message.timestamp` already is. 3.x returned a naive UTC `datetime` for a
presence message received from Ably, and an aware one for a LEAVE the library synthesized.
An ordering comparison such as `<` against a `datetime` raises `TypeError`. Convert the
timestamp where you need a `datetime`:

Example 3.x code:
```python
received_at = member.timestamp
```

Example 4.0.0 code:
```python
from datetime import datetime, timezone

received_at = datetime.fromtimestamp(member.timestamp / 1000, tz=timezone.utc)
```

### `Stats.interval_time` is timezone-aware

`Stats.interval_time` is now an aware `datetime` in UTC, where 3.x returned a naive one. An
ordering comparison such as `<` against a naive `datetime` now raises `TypeError`, and `==`
against one quietly returns `False`. Compare it with aware datetimes:

Example 3.x code:
```python
if stat.interval_time >= datetime(2024, 1, 1):
    ...
```

Example 4.0.0 code:
```python
if stat.interval_time >= datetime(2024, 1, 1, tzinfo=timezone.utc):
    ...
```

### `HttpPaginatedResponse.error_code` is an `int`

**This change is silent: comparing `error_code` with a string, as in `== '40101'`, now
returns `False` rather than raising.** The `error_code` of the response that `request()`
returns is now the `int` parsed from the `X-Ably-Errorcode` header, where 3.x returned the
header's string. It is still `None` when the header is absent. Compare it with an `int`:

Example 3.x code:
```python
if response.error_code == '40101':
    ...
```

Example 4.0.0 code:
```python
if response.error_code == 40101:
    ...
```

### `HttpPaginatedResponse.headers` is a read-only mapping

The `headers` of the response that `request()` returns is now a read-only mapping from header
name to value, looked up case-insensitively, where 3.x returned a list of `(name, value)`
pairs. As before, names are lower-cased and a header sent more than once has its values
joined with `', '`. Iterating over the mapping itself now yields only the names, so look a
header up by name, or iterate over `.items()`:

Example 3.x code:
```python
for name, value in response.headers:
    ...
```

Example 4.0.0 code:
```python
request_id = response.headers.get('X-Request-Id')

for name, value in response.headers.items():
    ...
```

### Push removals return nothing, and results no longer expose the HTTP response

`remove` and `remove_where` on `push.admin.device_registrations` and
`push.admin.channel_subscriptions` now return `None`, where 3.x returned the underlying HTTP
response. A removal that fails raises an `AblyException`, so there is no status code to check:

Example 3.x code:
```python
response = await rest.push.admin.device_registrations.remove(device_id)
assert response.status_code == 204
```

Example 4.0.0 code:
```python
await pubsub_http_client.push.admin.device_registrations.remove(device_id)
```

For the same reason a `PaginatedResult` no longer has a `response` attribute. The
`HttpPaginatedResponse` that `request()` returns keeps `status_code`, `success`,
`error_code`, `error_message` and `headers`, so read those instead of `response`.

### `DeviceDetails.push` is a `DevicePushDetails`

`DeviceDetails.push` is now a `DevicePushDetails`, with `recipient`, `state` and
`error_reason` attributes, where 3.x returned the dict the server sent. `error_reason` is an
`AblyException`. Indexing it, as in `device.push['recipient']`, now raises `TypeError`.
Read the attributes instead. A device can still be built or saved with `push` given as a
dict:

Example 3.x code:
```python
token = device.push['recipient']['deviceToken']
```

Example 4.0.0 code:
```python
token = device.push.recipient['deviceToken']
```

`DeviceDetails` and `PushChannelSubscription` now also ignore fields they do not know when
decoding a dict, where 3.x raised `TypeError` on any field the server added. A misspelled key
in a dict you pass to `save()` is therefore ignored rather than rejected.

### Setting channel options replaces them, cipher included

**`set_options(ChannelOptions(params=...))` on an encrypted channel now turns encryption off.**
`channel.set_options(options)`, and `channels.get(name, options)` on a channel that already
exists, replace the channel's options whole rather than merging them, so options without a
`cipher` leave the channel unencrypted. 3.x kept the old cipher whenever the new options left
it out, and on a realtime channel even when they gave `cipher=None`. Pass the cipher again
whenever you set the options of an encrypted channel:

Example 3.x code:
```python
channel = realtime.channels.get('my-channel', ChannelOptions(cipher=cipher_params))
await channel.set_options(ChannelOptions(params={'rewind': '1'}))
```

Example 4.0.0 code:
```python
channel = pubsub_realtime_client.channels.get('my-channel', ChannelOptions(cipher=cipher_params))
await channel.set_options(ChannelOptions(cipher=cipher_params, params={'rewind': '1'}))
```

`channel.options` is now the `ChannelOptions` that was last set, rather than a dict, so read
its attributes rather than its keys:

Example 3.x code:
```python
rewind = channel.options['params']['rewind']
```

Example 4.0.0 code:
```python
rewind = channel.options.params['rewind']
```

HTTP channels now take a `ChannelOptions` too, through `channels.get(name, options)` or
`await channel.set_options(options)`. `channels.get` raises when given options that would make
an attaching or attached realtime channel reattach, which only a change to `params` or `modes`
does; a change to the cipher alone no longer raises.

### Channels are no longer attributes of the channels collection

`client.channels.my_channel` used to get or create the channel called `my_channel`, because the
collection answered any attribute it did not define with a channel of that name. That made a
typo, or even `hasattr(client.channels, ...)`, create a channel. In 4.0.0 an unknown attribute
raises `AttributeError`, so get the channel by name instead:

Example 3.x code:
```python
channel = rest.channels.my_channel
```

Example 4.0.0 code:
```python
channel = pubsub_http_client.channels.get('my_channel')
```

### A space in a channel name reaches the channel it names over HTTP

3.x wrote a space in a channel name as `+` in HTTP request paths, which the Ably service reads
as a literal plus, so HTTP publishes, history, presence, annotations, message reads and
`status()` for `my channel` all went to a different channel, `my+channel`, from the one
realtime clients attach to. 4.0.0 writes the space as `%20`, so they reach `my channel`.
Messages that 3.x stored over HTTP for such a name are in the `+` channel, and stay reachable
by that name:

Example 4.0.0 code:
```python
stored_by_3x = pubsub_http_client.channels.get('my+channel')
history = await stored_by_3x.history()
```

`status()` now escapes the channel name too, so a name containing `/`, `?` or `#` no longer
addresses the wrong resource.

### `attach()` raises when the channel does not attach

`await channel.attach()` raised only when the channel became `SUSPENDED` or `FAILED`. When the
connection closed while the channel was attaching, the channel became `DETACHED` and `attach()`
returned as if it had succeeded; so did an `attach()` overtaken by a `detach()`. In 4.0.0 it
raises an `AblyException` whenever the channel moves to any state but `ATTACHED`, carrying the
reason for that state, or code 90001 when there is none. `subscribe()`, which attaches, raises
in the same cases. Code that closes the client, or detaches, while an attach may be pending
should expect the exception:

Example 4.0.0 code:
```python
try:
    await channel.attach()
except AblyException:
    # the channel did not attach, for instance because the client was closed meanwhile
    ...
```

### `connection.ping()` waits for a disconnected connection

`await connection.ping()` raised an `AblyException` with code 40000 at once when the connection
was `DISCONNECTED`. In 4.0.0 it waits for the connection to reconnect, as it already did while
`CONNECTING`, and then times out `realtime_request_timeout_seconds` after its heartbeat goes out. It
still fails if the connection becomes `SUSPENDED`, `CLOSED` or `FAILED` first, which can be up to
two minutes later. Bound the wait yourself if you need an answer sooner:

Example 4.0.0 code:
```python
response_time_ms = await asyncio.wait_for(pubsub_realtime_client.connection.ping(), timeout=5)
```

### The millisecond timing options take seconds, and end in `_seconds`

**Passing an old name raises `TypeError`, so a missed rename fails at construction rather
than silently scheduling a timeout a thousand times too long.** Four realtime timing options
and `fallback_retry_timeout`, which the HTTP client reads too, took milliseconds, where the
HTTP timeouts took seconds. They now take seconds, as an `int` or a `float`, and each is
renamed with a `_seconds` suffix so the unit is in the name. They read back from
`client.options` under the new names:

| 3.x option | Unit | 4.0.0 option | Unit | Default |
|---|---|---|---|---|
| `realtime_request_timeout` | ms | `realtime_request_timeout_seconds` | s | 10 |
| `disconnected_retry_timeout` | ms | `disconnected_retry_timeout_seconds` | s | 15 |
| `suspended_retry_timeout` | ms | `suspended_retry_timeout_seconds` | s | 30 |
| `channel_retry_timeout` | ms | `channel_retry_timeout_seconds` | s | 15 |
| `fallback_retry_timeout` | ms | `fallback_retry_timeout_seconds` | s | 600 |

Divide a 3.x value by 1000, or pass a `timedelta`'s `total_seconds()`. The values the Ably
protocol carries are still milliseconds: a token's `ttl`, `connection.connection_details`,
`auth.time_offset`, every timestamp and the round trip `connection.ping()` returns.

Example 3.x code:
```python
realtime = AblyRealtime(key='xxx', disconnected_retry_timeout=5000, realtime_request_timeout=2500)
```

Example 4.0.0 code:
```python
from datetime import timedelta

pubsub_realtime_client = create_realtime_client(
    key='xxx',
    disconnected_retry_timeout_seconds=5,
    realtime_request_timeout_seconds=timedelta(milliseconds=2500).total_seconds(),
)
```

### The HTTP timing options end in `_seconds`

**Passing an old name raises `TypeError`.** The HTTP timing options were already seconds, and
still are, but their names did not say so where the other timing options were milliseconds.
Each is renamed with a `_seconds` suffix, to match the options above, and reads back from
`client.options` under the new name. Only the name changes:

| 3.x option | Unit | 4.0.0 option | Unit | Default |
|---|---|---|---|---|
| `http_open_timeout` | s | `http_open_timeout_seconds` | s | 4 |
| `http_request_timeout` | s | `http_request_timeout_seconds` | s | 10 |
| `http_max_retry_duration` | s | `http_max_retry_duration_seconds` | s | 15 |

Keep a 3.x value as it is, or pass a `timedelta`'s `total_seconds()`.

Example 3.x code:
```python
rest = AblyRest(key='xxx', http_open_timeout=2, http_request_timeout=5)
```

Example 4.0.0 code:
```python
from datetime import timedelta

pubsub_http_client = create_http_client(
    key='xxx',
    http_open_timeout_seconds=2,
    http_request_timeout_seconds=timedelta(seconds=5).total_seconds(),
)
```

### An old timing option name says what to pass instead

Passing a timing option under its 3.x name raises a `TypeError` that names its replacement
and, where the unit changed, converts the value you passed, so a 3.x configuration fails at
construction with the fix in the message. Unknown options already raised `TypeError`, so
code that caught it still does:

```
TypeError: `disconnected_retry_timeout` was renamed to `disconnected_retry_timeout_seconds` in 4.0 and is now in seconds (15000 ms → 15)
TypeError: `http_request_timeout` was renamed to `http_request_timeout_seconds` in 4.0; it is still in seconds
```

All eight renames together:

| 3.x option | Unit | 4.0.0 option | Unit |
|---|---|---|---|
| `realtime_request_timeout` | ms | `realtime_request_timeout_seconds` | s |
| `disconnected_retry_timeout` | ms | `disconnected_retry_timeout_seconds` | s |
| `suspended_retry_timeout` | ms | `suspended_retry_timeout_seconds` | s |
| `channel_retry_timeout` | ms | `channel_retry_timeout_seconds` | s |
| `fallback_retry_timeout` | ms | `fallback_retry_timeout_seconds` | s |
| `http_open_timeout` | s | `http_open_timeout_seconds` | s |
| `http_request_timeout` | s | `http_request_timeout_seconds` | s |
| `http_max_retry_duration` | s | `http_max_retry_duration_seconds` | s |

A value held as a `timedelta` converts with `total_seconds()`, whichever option it is for.

### Timing options are validated when the client is created

The eight `_seconds` timing options must each be a finite, non-negative `int` or `float`.
Anything else raises an `InvalidArgumentException`, an `AblyException` with code 40000 that
is also a `ValueError`, when the client is created. In 3.x nothing was checked: a string or
a negative number failed later or not at all, and a `timedelta` passed to a realtime option
was accepted and then raised inside the timer, so the retry it scheduled never ran. Zero is
accepted, and no value is too small or too large to pass.

| 3.x option | Unit | 4.0.0 option | Unit | Accepts |
|---|---|---|---|---|
| `realtime_request_timeout` | ms | `realtime_request_timeout_seconds` | s | `int` or `float`, ≥ 0 |
| `disconnected_retry_timeout` | ms | `disconnected_retry_timeout_seconds` | s | `int` or `float`, ≥ 0 |
| `suspended_retry_timeout` | ms | `suspended_retry_timeout_seconds` | s | `int` or `float`, ≥ 0 |
| `channel_retry_timeout` | ms | `channel_retry_timeout_seconds` | s | `int` or `float`, ≥ 0 |
| `fallback_retry_timeout` | ms | `fallback_retry_timeout_seconds` | s | `int` or `float`, ≥ 0 |
| `http_open_timeout` | s | `http_open_timeout_seconds` | s | `int` or `float`, ≥ 0 |
| `http_request_timeout` | s | `http_request_timeout_seconds` | s | `int` or `float`, ≥ 0 |
| `http_max_retry_duration` | s | `http_max_retry_duration_seconds` | s | `int` or `float`, ≥ 0 |

Convert a `timedelta` with `total_seconds()`:

Example 3.x code:
```python
realtime = AblyRealtime(key='xxx', disconnected_retry_timeout=timedelta(seconds=5))
```

Example 4.0.0 code:
```python
pubsub_realtime_client = create_realtime_client(
    key='xxx', disconnected_retry_timeout_seconds=timedelta(seconds=5).total_seconds())
```

### A `timedelta` ttl is sent to the millisecond

A token `ttl` given as a `timedelta` is now converted to milliseconds exactly. 3.x went through
`total_seconds()` and truncated, so many values were sent one millisecond short: a ttl of
`timedelta(milliseconds=1001)` was requested as 1000. Whole seconds were unaffected. This applies
to token requests and to the params sent to an `auth_url`. A `ttl` given as a number of
milliseconds is sent as before.

No change is needed.

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
