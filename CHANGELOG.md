# Change Log

## [3.1.4](https://github.com/ably/ably-pubsub-python/tree/v3.1.4)

[Full Changelog](https://github.com/ably/ably-pubsub-python/compare/v3.1.3...v3.1.4)

### What's Changed

- Fixed delta decoding so a protocol message carrying several chained delta messages decodes as a chain, instead of failing on the second message and dropping the whole batch [#707](https://github.com/ably/ably-pubsub-python/pull/707)

## [3.1.3](https://github.com/ably/ably-python/tree/v3.1.3)

[Full Changelog](https://github.com/ably/ably-python/compare/v3.1.2...v3.1.3)

### What's Changed

- Fixed `ping()` so a timed-out, rejected, or connection-dropped ping no longer leaves a stale future behind that made every later `ping()` call fail or hang [#687](https://github.com/ably/ably-python/pull/687)
- Annotation `data` is now encrypted on publish and decrypted on REST `get()` for channels with a cipher configured, instead of being sent in plaintext [#680](https://github.com/ably/ably-python/pull/680)
- Fixed the "unable to attach" log to report the connection state that is blocking the attach rather than the channel state [#653](https://github.com/ably/ably-python/pull/653)

## [3.1.2](https://github.com/ably/ably-python/tree/v3.1.2)

[Full Changelog](https://github.com/ably/ably-python/compare/v3.1.1...v3.1.2)

### What's Changed

- Fixed preserving extras in message updates methods to prevent data loss [#670](https://github.com/ably/ably-python/pull/670)

## [v3.1.1](https://github.com/ably/ably-python/tree/v3.1.1)

[Full Changelog](https://github.com/ably/ably-python/compare/v3.1.0...v3.1.1)

### What's Changed

- Fixed handling of normal WebSocket close frames and improved reconnection logic [#672](https://github.com/ably/ably-python/pull/672)

## [v3.1.0](https://github.com/ably/ably-python/tree/v3.1.0)

[Full Changelog](https://github.com/ably/ably-python/compare/v3.0.0...v3.1.0)

### What's Changed

- Added realtime and rest support for Annotations API [#667](https://github.com/ably/ably-python/pull/667)

## [v3.0.0](https://github.com/ably/ably-python/tree/v3.0.0)

[Full Changelog](https://github.com/ably/ably-python/compare/v2.1.3...v3.0.0)

### What's Changed

- Added realtime publish support for publishing messages to channels over the realtime connection [#648](https://github.com/ably/ably-python/pull/648)
- Added realtime presence support, allowing clients to enter, leave, update presence data, and track presence on channels [#651](https://github.com/ably/ably-python/pull/651)
- Added mutable messages API with support for editing, deleting, and appending to messages [#660](https://github.com/ably/ably-python/pull/660), [#659](https://github.com/ably/ably-python/pull/659)
- Added publish results containing serial of published messages [#660](https://github.com/ably/ably-python/pull/660), [#659](https://github.com/ably/ably-python/pull/659)
- Deprecated `environment`, `rest_host`, and `realtime_host` client options in favor of `endpoint` option [#590](https://github.com/ably/ably-python/pull/590)

### Breaking change

The 3.0.0 version of ably-python introduces several breaking changes to improve the realtime experience and align the API with the Ably specification. These include:

- The realtime channel publish method now uses WebSocket connection instead of REST
- `ably.realtime.realtime_channel` module renamed to `ably.realtime.channel`
- `ChannelOptions` moved to `ably.types.channeloptions`
- REST publish returns publish result with message serials instead of Response object
- Deprecated `environment`, `rest_host`, and `realtime_host` client options in favor of `endpoint` option

For detailed migration instructions, please refer to the [Upgrading Guide](UPDATING.md).

## [v2.1.3](https://github.com/ably/ably-python/tree/v2.1.3)

[Full Changelog](https://github.com/ably/ably-python/compare/v2.1.2...v2.1.3)

## What's Changed

- Got rid of `methoddispatch` dependency in [\#639](https://github.com/ably/ably-python/pull/639)
- Upgraded internal build tools

## [v2.1.2](https://github.com/ably/ably-python/tree/v2.1.2)

[Full Changelog](https://github.com/ably/ably-python/compare/v2.1.1...v2.1.2)

## What's Changed

- Support `methoddispatch` version 5 [\#634](https://github.com/ably/ably-python/pull/634)
- Support `pyee` version 13 [\#635](https://github.com/ably/ably-python/pull/635)

## [v2.1.1](https://github.com/ably/ably-python/tree/v2.1.1)

[Full Changelog](https://github.com/ably/ably-python/compare/v2.1.0...v2.1.1)

## What's Changed

* Added missed `sync` folder to the wheel package 

## [v2.1.0](https://github.com/ably/ably-python/tree/v2.1.0)

[Full Changelog](https://github.com/ably/ably-python/compare/v2.0.13...v2.1.0)

## What's Changed

* Added support for VCDiff delta-compressed messages. If VCDiff compression is enabled in the client options, and 
deltas are provided by the Ably service, the SDK reconstructs full message payloads from the base content 
and the received delta, reducing bandwidth usage without requiring changes to your application code.
[\#620](https://github.com/ably/ably-python/pull/620)

## [v2.0.13](https://github.com/ably/ably-python/tree/v2.0.13)

[Full Changelog](https://github.com/ably/ably-python/compare/v2.0.12...v2.0.13)

## What's Changed
* Removed await from sync `connect()` function call by @kavindail in https://github.com/ably/ably-python/pull/605
* Upgraded websockets dependency to support 15+ by @ttypic in https://github.com/ably/ably-python/pull/612

## [v2.0.12](https://github.com/ably/ably-python/tree/v2.0.12)

[Full Changelog](https://github.com/ably/ably-python/compare/v2.0.11...v2.0.12)

**Closed issues:**
- The REST client’s retry mechanism doesn’t follow the spec and doesn’t retry when it should [\#597](https://github.com/ably/ably-python/issues/597)

## [v2.0.11](https://github.com/ably/ably-python/tree/v2.0.11)

[Full Changelog](https://github.com/ably/ably-python/compare/v2.0.10...v2.0.11)

**Closed issues:**
- Support `websockets` version 13 [\#591](https://github.com/ably/ably-python/issues/591)

## [v2.0.10](https://github.com/ably/ably-python/tree/v2.0.10)

Fixed sync version of the library

## [v2.0.9](https://github.com/ably/ably-python/tree/v2.0.9)

[Full Changelog](https://github.com/ably/ably-python/compare/v2.0.8...v2.0.9)

**Fixed bugs:**

- Fix the inability to pass a JSON string value for a `capability` parameter when creating a token [\#579](https://github.com/ably/ably-python/issues/579)

**Closed issues:**
- Support `pyee` 12 [\#580](https://github.com/ably/ably-python/issues/580)

## [v2.0.8](https://github.com/ably/ably-python/tree/v2.0.8)

[Full Changelog](https://github.com/ably/ably-python/compare/v2.0.7...v2.0.8)

**Fixed bugs:**

- Fix `TypeError: '>' not supported between instances of 'float' and 'NoneType'` in http [\#573](https://github.com/ably/ably-python/pull/573)

## [v2.0.7](https://github.com/ably/ably-python/tree/v2.0.7)

[Full Changelog](https://github.com/ably/ably-python/compare/v2.0.6...v2.0.7)

**Fixed bugs:**

- Decoding issue for 40010 Error \(Invalid Channel Name\) [\#569](https://github.com/ably/ably-python/issues/569)

## [v2.0.6](https://github.com/ably/ably-python/tree/v2.0.6)

[Full Changelog](https://github.com/ably/ably-python/compare/v2.0.5...v2.0.6)

**Closed issues:**

- Support httpx 0.26, 0.27 and so on [\#560](https://github.com/ably/ably-python/issues/560)

**Merged pull requests:**

- Fix dependencies [\#559](https://github.com/ably/ably-python/pull/559) ([sacOO7](https://github.com/sacOO7))

## [v2.0.5](https://github.com/ably/ably-python/tree/v2.0.5)

[Full Changelog](https://github.com/ably/ably-python/compare/v2.0.4...v2.0.5)

**Closed issues:**

- Question: Bump websockets version [\#556](https://github.com/ably/ably-python/issues/556)
- "RuntimeError: no running event loop" exception when connecting to Realtime [\#555](https://github.com/ably/ably-python/issues/555)

**Merged pull requests:**

- Bumped up websocket lib [\#557](https://github.com/ably/ably-python/pull/557) ([sacOO7](https://github.com/sacOO7))

## [v2.0.4](https://github.com/ably/ably-python/tree/v2.0.4)

[Full Changelog](https://github.com/ably/ably-python/compare/v2.0.3...v2.0.4)

**Merged pull requests:**

- Upgrade httpx version [\#552](https://github.com/ably/ably-python/pull/552) ([sacOO7](https://github.com/sacOO7))

## [v2.0.3](https://github.com/ably/ably-python/tree/v2.0.3)

[Full Changelog](https://github.com/ably/ably-python/compare/v2.0.2...v2.0.3)

**Closed issues:**

- Support for python 3.12 [\#546](https://github.com/ably/ably-python/issues/546)

**Merged pull requests:**

- Support latest python versions [\#547](https://github.com/ably/ably-python/pull/547) ([sacOO7](https://github.com/sacOO7))
- Update README.md to add in 'publish message to channel including metadata' [\#545](https://github.com/ably/ably-python/pull/545) ([cameron-michie](https://github.com/cameron-michie))

## [v2.0.2](https://github.com/ably/ably-python/tree/v2.0.2)

[Full Changelog](https://github.com/ably/ably-python/compare/v2.0.1...v2.0.2)

**Implemented enhancements:**

- Add synchronous AblyRest client (for more info see the [docs]()) [\#537](https://github.com/ably/ably-python/issues/537)

**Closed issues:**

- Update httpx dependency to version 0.24.1 or higher [\#523](https://github.com/ably/ably-python/issues/523)

**Merged pull requests:**

- Updated poetry httpx dependency and lock file [\#524](https://github.com/ably/ably-python/pull/524) ([sacOO7](https://github.com/sacOO7))
- Remove unused dependency: h2 [\#526](https://github.com/ably/ably-python/pull/526) ([gdrosos](https://github.com/gdrosos))
- Add sync support using unasync [\#537](https://github.com/ably/ably-python/pull/526) ([sacOO7](https://github.com/sacOO7))

## [v2.0.1](https://github.com/ably/ably-python/tree/v2.0.1)

[Full Changelog](https://github.com/ably/ably-python/compare/v2.0.0...v2.0.1)

**Closed issues:**

- Implement / Add tests for TM1,TM2,TM3 Message spec [\#516](https://github.com/ably/ably-python/issues/516)

**Merged pull requests:**

- \[SDK-3807\] Implement and test empty inner message fields [\#517](https://github.com/ably/ably-python/pull/517) ([sacOO7](https://github.com/sacOO7))

## [v2.0.0](https://github.com/ably/ably-python/tree/v2.0.0)

**New ably-python realtime client**: This new release features our first ever python realtime client! Currently the realtime client only supports realtime message subscription. Check out the README for usage examples. There have been some minor breaking changes from the 1.2 version, please consult the [migration guide](https://github.com/ably/ably-python/blob/main/UPDATING.md) for instructions on how to upgrade to 2.0.

[Full Changelog](https://github.com/ably/ably-python/compare/v1.2.2...v2.0.0)

- refactor!: add mandatory version param to `Rest.request` [\#500](https://github.com/ably/ably-python/issues/500)
- bump api_version to 2.0, add DeviceDetails.deviceSecret [\#507](https://github.com/ably/ably-python/issues/507)
- Include cause in AblyException.__str__ result [\#508](https://github.com/ably/ably-python/issues/508)
- feat!: use api v3 and untyped stats [\#505](https://github.com/ably/ably-python/issues/505)
- Implement `add_request_ids` client option [\#399](https://github.com/ably/ably-python/issues/399)
- Improve logger output upon disconnection [\#492](https://github.com/ably/ably-python/issues/492)
- Fix an issue where in some cases the client was unable to recover after loss of connectivity [\#493](https://github.com/ably/ably-python/issues/493)
- Remove soft-deprecated APIs [\#482](https://github.com/ably/ably-python/issues/482)
- Improve realtime client typings [\#476](https://github.com/ably/ably-python/issues/476)
- Improve REST client typings [\#477](https://github.com/ably/ably-python/issues/477)
- Stop raising `KeyError` when releasing a channel which doesn't exist [\#474](https://github.com/ably/ably-python/issues/474)
- Allow token auth methods for realtime constructor [\#425](https://github.com/ably/ably-python/issues/425)
- Send `AUTH` protocol message when `Auth.authorize` called on realtime client [\#427](https://github.com/ably/ably-python/issues/427)
- Reauth upon inbound `AUTH` protocol message [\#428](https://github.com/ably/ably-python/issues/428)
- Handle connection request failure due to token error [\#445](https://github.com/ably/ably-python/issues/445)
- Handle token `ERROR` response to a resume request [\#444](https://github.com/ably/ably-python/issues/444)
- Handle `DISCONNECTED` messages containing token errors [\#443](https://github.com/ably/ably-python/issues/443)
- Pass `clientId` as query string param when opening a new connection [\#449](https://github.com/ably/ably-python/issues/449)
- Validate `clientId` in `ClientOptions` [\#448](https://github.com/ably/ably-python/issues/448)
- Apply `Auth#clientId` only after a realtime connection has been established [\#409](https://github.com/ably/ably-python/issues/409)
- Channels should transition to `INITIALIZED` if `Connection.connect` called from terminal state [\#411](https://github.com/ably/ably-python/issues/411)
- Calling connect while `CLOSING` should start connect on a new transport [\#410](https://github.com/ably/ably-python/issues/410)
- Handle realtime channel errors [\#455](https://github.com/ably/ably-python/issues/455)
- Resend protocol messages for pending channels upon resume [\#347](https://github.com/ably/ably-python/issues/347)
- Attempt to resume connection when disconnected unexpectedly [\#346](https://github.com/ably/ably-python/issues/346)
- Handle `CONNECTED` messages once connected [\#345](https://github.com/ably/ably-python/issues/345)
- Implement `maxIdleInterval` [\#344](https://github.com/ably/ably-python/issues/344)
- Implement realtime connectivity check [\#343](https://github.com/ably/ably-python/issues/343)
- Use fallback realtime hosts when encountering an appropriate error [\#342](https://github.com/ably/ably-python/issues/342)
- Add `fallbackHosts` client option for realtime clients [\#341](https://github.com/ably/ably-python/issues/341)
- Implement `connectionStateTtl` [\#340](https://github.com/ably/ably-python/issues/340)
- Implement `disconnectedRetryTimeout` [\#339](https://github.com/ably/ably-python/issues/339)
- Handle recoverable connection opening errors [\#338](https://github.com/ably/ably-python/issues/338)
- Implement `channelRetryTimeout` [\#442](https://github.com/ably/ably-python/issues/436)
- Queue protocol messages when connection state is `CONNECTING` or `DISCONNECTED` [\#418](https://github.com/ably/ably-python/issues/418)
- Propagate connection interruptions to realtime channels [\#417](https://github.com/ably/ably-python/issues/417)
- Spec compliance: `Realtime.connect` should be sync [\#413](https://github.com/ably/ably-python/issues/413)
- Emit `update` event on additional `ATTACHED` message [\#386](https://github.com/ably/ably-python/issues/386)
- Set the `ATTACH_RESUME` flag on unclean attach [\#385](https://github.com/ably/ably-python/issues/385)
- Handle fatal resume error [\#384](https://github.com/ably/ably-python/issues/384)
- Handle invalid resume response [\#383](https://github.com/ably/ably-python/issues/383)
- Handle clean resume response [\#382](https://github.com/ably/ably-python/issues/382)
- Send resume query param when reconnecting within `connectionStateTtl`  [\#381](https://github.com/ably/ably-python/issues/381)
- Immediately reattempt connection when unexpectedly disconnected [\#380](https://github.com/ably/ably-python/issues/380)
- Clear connection state when `connectionStateTtl` elapsed [\#379](https://github.com/ably/ably-python/issues/379)
- Refactor websocket async tasks into WebSocketTransport class [\#373](https://github.com/ably/ably-python/issues/373)
- Send version transport param [\#368](https://github.com/ably/ably-python/issues/368)
- Clear `Connection.error_reason` when `Connection.connect` is called [\#367](https://github.com/ably/ably-python/issues/367)
- Fix a bug with realtime_host configuration [\#358](https://github.com/ably/ably-python/pull/358)
- Create Basic Api Key connection [\#311](https://github.com/ably/ably-python/pull/311)
- Send Ably-Agent header in realtime connection [\#314](https://github.com/ably/ably-python/pull/314)
- Close client service [\#315](https://github.com/ably/ably-python/pull/315)
- Implement EventEmitter interface on Connection [\#316](https://github.com/ably/ably-python/pull/316)
- Finish tasks gracefully on failed connection [\#317](https://github.com/ably/ably-python/pull/317)
- Implement realtime ping [\#318](https://github.com/ably/ably-python/pull/318)
- Realtime channel attach/detach [\#319](https://github.com/ably/ably-python/pull/319)
- Add `auto_connect` implementation and client option [\#325](https://github.com/ably/ably-python/pull/325)
- RealtimeChannel subscribe/unsubscribe [\#326](https://github.com/ably/ably-python/pull/326)
- ConnectionStateChange [\#327](https://github.com/ably/ably-python/pull/327)
- Improve realtime logging [\#330](https://github.com/ably/ably-python/pull/330)
- Update readme with realtime documentation [\#334](334](https://github.com/ably/ably-python/pull/334)
- Use string-based enums [\#351](https://github.com/ably/ably-python/pull/351)
- Add environment client option for realtime [\#335](https://github.com/ably/ably-python/pull/335)
- EventEmitter: allow signatures with no event arg [\#350](https://github.com/ably/ably-python/pull/350)

## [v2.0.0-beta.6](https://github.com/ably/ably-python/tree/v2.0.0-beta.6)

[Full Changelog](https://github.com/ably/ably-python/compare/v2.0.0-beta.5...v2.0.0-beta.6)

- Improve logger output upon disconnection [\#492](https://github.com/ably/ably-python/issues/492)
- Fix an issue where in some cases the client was unable to recover after loss of connectivity [\#493](https://github.com/ably/ably-python/issues/493)

## [v2.0.0-beta.5](https://github.com/ably/ably-python/tree/v2.0.0-beta.5)

The latest beta release of ably-python 2.0 makes some minor breaking changes, removing already soft-deprecated features from the 1.x branch. Most users will not be affected by these changes since the library was already warning that these features were deprecated. For information on how to migrate, please consult the [migration guide](https://github.com/ably/ably-python/blob/main/UPDATING.md).

[Full Changelog](https://github.com/ably/ably-python/compare/v2.0.0-beta.4...v2.0.0-beta.5)

- Remove soft-deprecated APIs [\#482](https://github.com/ably/ably-python/issues/482)
- Improve realtime client typings [\#476](https://github.com/ably/ably-python/issues/476)
- Improve REST client typings [\#477](https://github.com/ably/ably-python/issues/477)
- Stop raising `KeyError` when releasing a channel which doesn't exist [\#474](https://github.com/ably/ably-python/issues/474)

## [v2.0.0-beta.4](https://github.com/ably/ably-python/tree/v2.0.0-beta.4)

This new beta release of the ably-python realtime client implements token authentication for realtime connections, allowing you to use all currently supported token options to authenticate a realtime client (auth_url, auth_callback, jwt, etc). The client will reauthenticate when the token expires or otherwise becomes invalid.

[Full Changelog](https://github.com/ably/ably-python/compare/v2.0.0-beta.3...v2.0.0-beta.4)

- Allow token auth methods for realtime constructor [\#425](https://github.com/ably/ably-python/issues/425)
- Send `AUTH` protocol message when `Auth.authorize` called on realtime client [\#427](https://github.com/ably/ably-python/issues/427)
- Reauth upon inbound `AUTH` protocol message [\#428](https://github.com/ably/ably-python/issues/428)
- Handle connection request failure due to token error [\#445](https://github.com/ably/ably-python/issues/445)
- Handle token `ERROR` response to a resume request [\#444](https://github.com/ably/ably-python/issues/444)
- Handle `DISCONNECTED` messages containing token errors [\#443](https://github.com/ably/ably-python/issues/443)
- Pass `clientId` as query string param when opening a new connection [\#449](https://github.com/ably/ably-python/issues/449)
- Validate `clientId` in `ClientOptions` [\#448](https://github.com/ably/ably-python/issues/448)
- Apply `Auth#clientId` only after a realtime connection has been established [\#409](https://github.com/ably/ably-python/issues/409)
- Channels should transition to `INITIALIZED` if `Connection.connect` called from terminal state [\#411](https://github.com/ably/ably-python/issues/411)
- Calling connect while `CLOSING` should start connect on a new transport [\#410](https://github.com/ably/ably-python/issues/410)
- Handle realtime channel errors [\#455](https://github.com/ably/ably-python/issues/455)

## [v2.0.0-beta.3](https://github.com/ably/ably-python/tree/v2.0.0-beta.3)

This new beta release of the ably-python realtime client implements a number of new features to improve the stability of realtime connections, allowing the client to reconnect during a temporary disconnection, use fallback hosts when necessary, and catch up on messages missed while the client was disconnected.

[Full Changelog](https://github.com/ably/ably-python/compare/v2.0.0-beta.2...v2.0.0-beta.3)

- Resend protocol messages for pending channels upon resume [\#347](https://github.com/ably/ably-python/issues/347)
- Attempt to resume connection when disconnected unexpectedly [\#346](https://github.com/ably/ably-python/issues/346)
- Handle `CONNECTED` messages once connected [\#345](https://github.com/ably/ably-python/issues/345)
- Implement `maxIdleInterval` [\#344](https://github.com/ably/ably-python/issues/344)
- Implement realtime connectivity check [\#343](https://github.com/ably/ably-python/issues/343)
- Use fallback realtime hosts when encountering an appropriate error [\#342](https://github.com/ably/ably-python/issues/342)
- Add `fallbackHosts` client option for realtime clients [\#341](https://github.com/ably/ably-python/issues/341)
- Implement `connectionStateTtl` [\#340](https://github.com/ably/ably-python/issues/340)
- Implement `disconnectedRetryTimeout` [\#339](https://github.com/ably/ably-python/issues/339)
- Handle recoverable connection opening errors [\#338](https://github.com/ably/ably-python/issues/338)
- Implement `channelRetryTimeout` [\#442](https://github.com/ably/ably-python/issues/436)
- Queue protocol messages when connection state is `CONNECTING` or `DISCONNECTED` [\#418](https://github.com/ably/ably-python/issues/418)
- Propagate connection interruptions to realtime channels [\#417](https://github.com/ably/ably-python/issues/417)
- Spec compliance: `Realtime.connect` should be sync [\#413](https://github.com/ably/ably-python/issues/413)
- Emit `update` event on additional `ATTACHED` message [\#386](https://github.com/ably/ably-python/issues/386)
- Set the `ATTACH_RESUME` flag on unclean attach [\#385](https://github.com/ably/ably-python/issues/385)
- Handle fatal resume error [\#384](https://github.com/ably/ably-python/issues/384)
- Handle invalid resume response [\#383](https://github.com/ably/ably-python/issues/383)
- Handle clean resume response [\#382](https://github.com/ably/ably-python/issues/382)
- Send resume query param when reconnecting within `connectionStateTtl`  [\#381](https://github.com/ably/ably-python/issues/381)
- Immediately reattempt connection when unexpectedly disconnected [\#380](https://github.com/ably/ably-python/issues/380)
- Clear connection state when `connectionStateTtl` elapsed [\#379](https://github.com/ably/ably-python/issues/379)
- Refactor websocket async tasks into WebSocketTransport class [\#373](https://github.com/ably/ably-python/issues/373)
- Send version transport param [\#368](https://github.com/ably/ably-python/issues/368)
- Clear `Connection.error_reason` when `Connection.connect` is called [\#367](https://github.com/ably/ably-python/issues/367)

## [v2.0.0-beta.2](https://github.com/ably/ably-python/tree/v2.0.0-beta.2)

[Full Changelog](https://github.com/ably/ably-python/compare/v2.0.0-beta.1...v2.0.0-beta.2)
- Fix a bug with realtime_host configuration [\#358](https://github.com/ably/ably-python/pull/358)

## [v2.0.0-beta.1](https://github.com/ably/ably-python/tree/v2.0.0-beta.1)

**New ably-python realtime client**: This beta release features our first ever python realtime client! Currently the realtime client only supports basic authentication and realtime message subscription. Check out the README for usage examples.

[Full Changelog](https://github.com/ably/ably-python/compare/v1.2.1...2.0.0-beta.1)

- Create Basic Api Key connection [\#311](https://github.com/ably/ably-python/pull/311)
- Send Ably-Agent header in realtime connection [\#314](https://github.com/ably/ably-python/pull/314)
- Close client service [\#315](https://github.com/ably/ably-python/pull/315)
- Implement EventEmitter interface on Connection [\#316](https://github.com/ably/ably-python/pull/316)
- Finish tasks gracefully on failed connection [\#317](https://github.com/ably/ably-python/pull/317)
- Implement realtime ping [\#318](https://github.com/ably/ably-python/pull/318)
- Realtime channel attach/detach [\#319](https://github.com/ably/ably-python/pull/319)
- Add `auto_connect` implementation and client option [\#325](https://github.com/ably/ably-python/pull/325)
- RealtimeChannel subscribe/unsubscribe [\#326](https://github.com/ably/ably-python/pull/326)
- ConnectionStateChange [\#327](https://github.com/ably/ably-python/pull/327)
- Improve realtime logging [\#330](https://github.com/ably/ably-python/pull/330)
- Update readme with realtime documentation [\#334](334](https://github.com/ably/ably-python/pull/334)
- Use string-based enums [\#351](https://github.com/ably/ably-python/pull/351)
- Add environment client option for realtime [\#335](https://github.com/ably/ably-python/pull/335)
- EventEmitter: allow signatures with no event arg [\#350](https://github.com/ably/ably-python/pull/350)

## [v1.2.1](https://github.com/ably/ably-python/tree/v1.2.1)

[Full Changelog](https://github.com/ably/ably-python/compare/v1.2.0...v1.2.1)

**Implemented enhancements:**

- Add support to get channel lifecycle status [\#271](https://github.com/ably/ably-python/issues/271)
- Migrate project to poetry [\#305](https://github.com/ably/ably-python/issues/305)

## [v1.2.0](https://github.com/ably/ably-python/tree/v1.2.0)

**Breaking API Changes**: Please see our [Upgrade / Migration Guide](UPDATING.md) for notes on changes you need to make to your code to update it to use the new API introduced by version 1.2.0.

[Full Changelog](https://github.com/ably/ably-python/compare/v1.1.1...v1.2.0)

**Implemented enhancements:**

- Respect content-type with charset [\#256](https://github.com/ably/ably-python/issues/256)
- Release a new version for python 3.10 support [\#249](https://github.com/ably/ably-python/issues/249)
- Support HTTP/2 [\#197](https://github.com/ably/ably-python/issues/197)
- Support Async HTTP [\#171](https://github.com/ably/ably-python/issues/171)
- Implement RSC7d \(Ably-Agent header\) [\#168](https://github.com/ably/ably-python/issues/168)
- Defaults: Generate environment fallbacks [\#155](https://github.com/ably/ably-python/issues/155)
- Clarify string encoding when sending push notifications [\#119](https://github.com/ably/ably-python/issues/119)
- Support for environments fallbacks [\#198](https://github.com/ably/ably-python/pull/198) ([d8x](https://github.com/d8x))

**Fixed bugs:**

- Channel.publish sometimes returns None after exhausting retries [\#160](https://github.com/ably/ably-python/issues/160)
- Token issue potential bug [\#54](https://github.com/ably/ably-python/issues/54)

**Closed issues:**

- Conform ReadMe and create Contributing Document [\#199](https://github.com/ably/ably-python/issues/199)
- Add support for DataTypes TokenParams AO2g [\#187](https://github.com/ably/ably-python/issues/187)
- Add support for TO3m [\#172](https://github.com/ably/ably-python/issues/172
- Using a clientId should no longer be forcing token auth in the 1.1 spec [\#149](https://github.com/ably/ably-python/issues/149)

**Merged pull requests:**

- Add support for Python 3.10, age out 3.6 [\#253](https://github.com/ably/ably-python/pull/253) ([tomkirbygreen](https://github.com/tomkirbygreen))
- Compat with 'httpx' public API changes. [\#252](https://github.com/ably/ably-python/pull/252) ([tomkirbygreen](https://github.com/tomkirbygreen))
- Respect content-type with charset [\#248](https://github.com/ably/ably-python/pull/248) ([tomkirbygreen](https://github.com/tomkirbygreen))
- 'TypedBuffer' fix attempt to call a non-callable object [\#226](https://github.com/ably/ably-python/pull/226) ([tomkirbygreen](https://github.com/tomkirbygreen))
- 'auth' module, fix possible unbound local variables warning [\#225](https://github.com/ably/ably-python/pull/225) ([tomkirbygreen](https://github.com/tomkirbygreen))
- rest setup - fix redeclared name without usage [\#217](https://github.com/ably/ably-python/pull/217) ([tomkirbygreen](https://github.com/tomkirbygreen))
- Fixes mutable-value used as argument default value [\#215](https://github.com/ably/ably-python/pull/215) ([tomkirbygreen](https://github.com/tomkirbygreen))
- Fixes most of the PEP 8 coding style violations [\#214](https://github.com/ably/ably-python/pull/214) ([tomkirbygreen](https://github.com/tomkirbygreen))
- 'Channel' remove unused 'history' parameter 'timeout'. [\#209](https://github.com/ably/ably-python/pull/209) ([tomkirbygreen](https://github.com/tomkirbygreen))
- \[\#149\] Specifying clientId does not force token auth [\#204](https://github.com/ably/ably-python/pull/204) ([d8x](https://github.com/d8x))
- Support for async [\#202](https://github.com/ably/ably-python/pull/202) ([d8x](https://github.com/d8x))
- Support for HTTP/2 Protocol [\#200](https://github.com/ably/ably-python/pull/200) ([d8x](https://github.com/d8x))
- Add missing `modified` property in DeviceDetails [\#196](https://github.com/ably/ably-python/pull/196) ([d8x](https://github.com/d8x))
- RSC7d - Support for Ably-Agent header [\#195](https://github.com/ably/ably-python/pull/195) ([d8x](https://github.com/d8x))
- fix error message for invalid push data type [\#169](https://github.com/ably/ably-python/pull/169) ([netspencer](https://github.com/netspencer))
- Raise error if all servers reply with a 5xx response [\#161](https://github.com/ably/ably-python/pull/161) ([jdavid](https://github.com/jdavid))

## [v1.1.1](https://github.com/ably/ably-python/tree/v1.1.1)

[Full Changelog](https://github.com/ably/ably-python/compare/v1.1.0...v1.1.1)

**Implemented enhancements:**

- Improve handling of clock skew [\#145](https://github.com/ably/ably-python/issues/145)
- Test variable length 256 bit AES CBC fixtures [\#150](https://github.com/ably/ably-python/pull/150) ([QuintinWillison](https://github.com/QuintinWillison))

**Closed issues:**

- Remove develop branch [\#151](https://github.com/ably/ably-python/issues/151)

**Merged pull requests:**

- bump msgpack version to 1.0.0 and update tests [\#152](https://github.com/ably/ably-python/pull/152) ([abordeau](https://github.com/abordeau))
- Fix flake8 [\#148](https://github.com/ably/ably-python/pull/148) ([jdavid](https://github.com/jdavid))
- RSA4b1 Detect expired token to avoid extra request [\#147](https://github.com/ably/ably-python/pull/147) ([jdavid](https://github.com/jdavid))
- push.admin.publish returns None [\#146](https://github.com/ably/ably-python/pull/146) ([jdavid](https://github.com/jdavid))
- 'Known limitations' section in the README [\#143](https://github.com/ably/ably-python/pull/143) ([Srushtika](https://github.com/Srushtika))

## [v1.1.0](https://github.com/ably/ably-python/tree/v1.1.0)
[Full Changelog](https://github.com/ably/ably-python/compare/v1.0.3...v1.1.0)

**Closed issues:**

- Idempotent publishing is not enabled in the upcoming 1.1 release [\#132](https://github.com/ably/ably-python/issues/132)
- forward slash in channel name [\#130](https://github.com/ably/ably-python/issues/130)
- Refactor tests setup [\#109](https://github.com/ably/ably-python/issues/109)

**Implemented enhancements:**

- Add support for remembered REST fallback host  [\#131](https://github.com/ably/ably-python/issues/131)
- Ensure request method accepts UPDATE, PATCH & DELETE verbs [\#128](https://github.com/ably/ably-python/issues/128)
- Add idempotent REST publishing support  [\#121](https://github.com/ably/ably-python/issues/121)
- Allow to configure logger [\#107](https://github.com/ably/ably-python/issues/107)

**Merged pull requests:**

- Fix flake8 [\#142](https://github.com/ably/ably-python/pull/142) ([jdavid](https://github.com/jdavid))
- Rsc15f Support for remembered REST fallback host  [\#141](https://github.com/ably/ably-python/pull/141) ([jdavid](https://github.com/jdavid))
- Add patch [\#135](https://github.com/ably/ably-python/pull/135) ([jdavid](https://github.com/jdavid))
- Idempotent publishing [\#129](https://github.com/ably/ably-python/pull/129) ([jdavid](https://github.com/jdavid))
- Push [\#127](https://github.com/ably/ably-python/pull/127) ([jdavid](https://github.com/jdavid))
- RSH1c5 New push.admin.channel\_subscriptions.remove\_where [\#126](https://github.com/ably/ably-python/pull/126) ([jdavid](https://github.com/jdavid))
- RSH1c4 New push.admin.channel\_subscriptions.remove [\#125](https://github.com/ably/ably-python/pull/125) ([jdavid](https://github.com/jdavid))
- RSH1c2 New push.admin.channel\_subscriptions.list\_channels [\#124](https://github.com/ably/ably-python/pull/124) ([jdavid](https://github.com/jdavid))
- RSH1c1 New push.admin.channel\_subscriptions.list [\#120](https://github.com/ably/ably-python/pull/120) ([jdavid](https://github.com/jdavid))
- RSH1c3 New push.admin.channel\_subscriptions.save [\#118](https://github.com/ably/ably-python/pull/118) ([jdavid](https://github.com/jdavid))
- RHS1b5 New push.admin.device\_registrations.remove\_where [\#117](https://github.com/ably/ably-python/pull/117) ([jdavid](https://github.com/jdavid))
- RHS1b4 New push.admin.device\_registrations.remove [\#116](https://github.com/ably/ably-python/pull/116) ([jdavid](https://github.com/jdavid))
- RSH1b2 New push.admin.device\_registrations.list [\#114](https://github.com/ably/ably-python/pull/114) ([jdavid](https://github.com/jdavid))
- Rsh1b1 New push.admin.device\_registrations.get [\#113](https://github.com/ably/ably-python/pull/113) ([jdavid](https://github.com/jdavid))
- RSH1b3 New push.admin.device\_registrations.save [\#112](https://github.com/ably/ably-python/pull/112) ([jdavid](https://github.com/jdavid))
- Document how to configure logging [\#110](https://github.com/ably/ably-python/pull/110) ([jdavid](https://github.com/jdavid))
- Rsh1a New push.admin.publish [\#106](https://github.com/ably/ably-python/pull/106) ([jdavid](https://github.com/jdavid))

## [v1.0.3](https://github.com/ably/ably-python/tree/v1.0.3) (2019-01-18)
[Full Changelog](https://github.com/ably/ably-python/compare/v1.0.2...v1.0.3)

**Closed issues:**

- Travis failures with Python 2 in the 1.0 branch [\#138](https://github.com/ably/ably-python/issues/138)

**Fixed bugs:**

- Authentication with auth\_url doesn't accept camel case [\#136](https://github.com/ably/ably-python/issues/136)

**Merged pull requests:**

- clientId must be a \(text\) string [\#139](https://github.com/ably/ably-python/pull/139) ([jdavid](https://github.com/jdavid))
- Fix authentication with auth\_url [\#137](https://github.com/ably/ably-python/pull/137) ([jdavid](https://github.com/jdavid))

## [v1.0.2](https://github.com/ably/ably-python/tree/v1.0.2) (2018-12-10)
[Full Changelog](https://github.com/ably/ably-python/compare/v1.0.1...v1.0.2)

**Fixed bugs:**

- HTTP connection pooling [\#133](https://github.com/ably/ably-python/issues/133)
- Timeouts when publishing messages [\#111](https://github.com/ably/ably-python/issues/111)
- AWS lambda packaging [\#97](https://github.com/ably/ably-python/issues/97)
- Rate limit requests to sandbox app [\#68](https://github.com/ably/ably-python/issues/68)

**Closed issues:**

- TokenRequest ttl unit discrepancy [\#104](https://github.com/ably/ably-python/issues/104)
- Python subscribe? [\#100](https://github.com/ably/ably-python/issues/100)

**Merged pull requests:**

- Fix README so it doesn't mislead ttl to be in s [\#105](https://github.com/ably/ably-python/pull/105) ([jdavid](https://github.com/jdavid))
- Fix tests [\#103](https://github.com/ably/ably-python/pull/103) ([jdavid](https://github.com/jdavid))
- Update README with supported platforms [\#102](https://github.com/ably/ably-python/pull/102) ([funkyboy](https://github.com/funkyboy))

## [v1.0.1](https://github.com/ably/ably-python/tree/v1.0.1) (2017-12-20)
[Full Changelog](https://github.com/ably/ably-python/compare/v1.0.0...v1.0.1)

**Implemented enhancements:**

- Fix HttpRequest & HttpRetry timeouts [\#86](https://github.com/ably/ably-python/issues/86)
- Cast TTL to integer [\#71](https://github.com/ably/ably-python/issues/71)
- Make PyCrypto optional [\#65](https://github.com/ably/ably-python/issues/65)

**Fixed bugs:**

- Travis random failures [\#88](https://github.com/ably/ably-python/issues/88)

**Closed issues:**

- pycrypto --\> pycryptodome [\#96](https://github.com/ably/ably-python/issues/96)
- `ably` module seems to be broken / empty in some circumstances [\#95](https://github.com/ably/ably-python/issues/95)
- installing via pip installs a more restrictive version of requests [\#91](https://github.com/ably/ably-python/issues/91)
- Add test coverage to prevent possible MsgPack regression [\#89](https://github.com/ably/ably-python/issues/89)
- 1.0 spec review [\#84](https://github.com/ably/ably-python/issues/84)
- When using python2 with msgpack, dicts are not encoded correctly [\#72](https://github.com/ably/ably-python/issues/72)

**Merged pull requests:**

- Fix unit tests [\#99](https://github.com/ably/ably-python/pull/99) ([jdavid](https://github.com/jdavid))
- Switch to cryptodome [\#98](https://github.com/ably/ably-python/pull/98) ([jdavid](https://github.com/jdavid))
- ttl: use isinstance instead of type [\#94](https://github.com/ably/ably-python/pull/94) ([jdavid](https://github.com/jdavid))
- Fix Flake8 warnings regarding spacing [\#93](https://github.com/ably/ably-python/pull/93) ([sginn](https://github.com/sginn))
- Bumped upper limit on requests library, and removed websocket [\#92](https://github.com/ably/ably-python/pull/92) ([sginn](https://github.com/sginn))
- Fix \#65, \#71, \#72, \#86 and \#89 [\#90](https://github.com/ably/ably-python/pull/90) ([jdavid](https://github.com/jdavid))

## [v1.0.0](https://github.com/ably/ably-python/tree/v1.0.0) (2017-03-07)
[Full Changelog](https://github.com/ably/ably-python/compare/v0.8.2...v1.0.0)

### v1.0 release and upgrade notes from v0.8

- See https://github.com/ably/docs/issues/235

**Implemented enhancements:**

- RSC19\*, HP\* - New REST \#request method + HttpPaginatedResponse type [\#78](https://github.com/ably/ably-python/issues/78)
- Update REST library for realtime platform to v1.0 specification [\#77](https://github.com/ably/ably-python/issues/77)

**Closed issues:**

- requests version pin too strict? [\#66](https://github.com/ably/ably-python/issues/66)

**Merged pull requests:**

- Issue\#84 TP4, RSC15a \(test\), RSC19e \(test\), .. [\#87](https://github.com/ably/ably-python/pull/87) ([jdavid](https://github.com/jdavid))
- Fix issue 72 [\#85](https://github.com/ably/ably-python/pull/85) ([jdavid](https://github.com/jdavid))
- Fix README, now using pytest instead of nose [\#83](https://github.com/ably/ably-python/pull/83) ([jdavid](https://github.com/jdavid))
- RSA5, RSA6, RSA10, RSL\*, TM\*, TE6, TD7 [\#82](https://github.com/ably/ably-python/pull/82) ([jdavid](https://github.com/jdavid))

## [v0.8.2](https://github.com/ably/ably-python/tree/v0.8.2) (2017-02-17)
[Full Changelog](https://github.com/ably/ably-python/compare/v0.8.1...v0.8.2)

**Implemented enhancements:**

- PaginatedResult attributes [\#70](https://github.com/ably/ably-python/issues/70)
- 0.8.x finalisation [\#48](https://github.com/ably/ably-python/issues/48)

**Fixed bugs:**

- Do not persist authorise attributes force & timestamp  [\#52](https://github.com/ably/ably-python/issues/52)

**Closed issues:**

- Publish on PyPI [\#50](https://github.com/ably/ably-python/issues/50)

**Merged pull requests:**

- RSC7, RSC11, RSC15, RSC19 [\#81](https://github.com/ably/ably-python/pull/81) ([jdavid](https://github.com/jdavid))
- Several python code repo improvements [\#73](https://github.com/ably/ably-python/pull/73) ([txomon](https://github.com/txomon))
- updated reqests version in requirements [\#67](https://github.com/ably/ably-python/pull/67) ([essweine](https://github.com/essweine))

## [v0.8.1](https://github.com/ably/ably-python/tree/v0.8.1) (2016-03-22)
[Full Changelog](https://github.com/ably/ably-python/compare/v0.8.0...v0.8.1)

**Implemented enhancements:**

- Don't require get\_default\_params for encryption [\#56](https://github.com/ably/ably-python/issues/56)
- Consistent README [\#8](https://github.com/ably/ably-python/issues/8)

**Closed issues:**

- when msgpack enabled, python 2 string literals are encoded as binaries [\#60](https://github.com/ably/ably-python/issues/60)

**Merged pull requests:**

- Python 2: assume str is intended as a string [\#64](https://github.com/ably/ably-python/pull/64) ([SimonWoolf](https://github.com/SimonWoolf))
- Implement latest encryption spec [\#63](https://github.com/ably/ably-python/pull/63) ([SimonWoolf](https://github.com/SimonWoolf))
- RSA7b4, RSA8f3, RSA8f4 [\#62](https://github.com/ably/ably-python/pull/62) ([fjsj](https://github.com/fjsj))
- RSA7a4 [\#61](https://github.com/ably/ably-python/pull/61) ([fjsj](https://github.com/fjsj))
- RSA7a2 [\#59](https://github.com/ably/ably-python/pull/59) ([fjsj](https://github.com/fjsj))
- RSA12 [\#58](https://github.com/ably/ably-python/pull/58) ([fjsj](https://github.com/fjsj))

## [v0.8.0](https://github.com/ably/ably-python/tree/v0.8.0) (2016-03-10)
**Implemented enhancements:**

- Switch arity of auth methods [\#42](https://github.com/ably/ably-python/issues/42)
- API changes Apr 2015 [\#7](https://github.com/ably/ably-python/issues/7)
- Change of repository name imminent [\#4](https://github.com/ably/ably-python/issues/4)

**Fixed bugs:**

- Switch arity of auth methods [\#42](https://github.com/ably/ably-python/issues/42)
- Use sandbox not staging [\#38](https://github.com/ably/ably-python/issues/38)
- API changes Apr 2015 [\#7](https://github.com/ably/ably-python/issues/7)

**Closed issues:**

- AblyException does not have \_\_str\_\_ [\#32](https://github.com/ably/ably-python/issues/32)
- Add a requirements-test.txt [\#29](https://github.com/ably/ably-python/issues/29)
- Fix message on test [\#23](https://github.com/ably/ably-python/issues/23)
- Rename test\_channels\_remove to test\_channels\_release [\#20](https://github.com/ably/ably-python/issues/20)
- Add comments in Python 2/3 code at ably/rest/channel.py [\#19](https://github.com/ably/ably-python/issues/19)
- Support for 2.6 [\#10](https://github.com/ably/ably-python/issues/10)
- Spec validation [\#9](https://github.com/ably/ably-python/issues/9)

**Merged pull requests:**

- Fixes for PyPI publishing \(already published\) [\#57](https://github.com/ably/ably-python/pull/57) ([fjsj](https://github.com/fjsj))
- RSL1g [\#55](https://github.com/ably/ably-python/pull/55) ([fjsj](https://github.com/fjsj))
- Ensure that force and timestamp are not stored in authorise [\#53](https://github.com/ably/ably-python/pull/53) ([meiralins](https://github.com/meiralins))
- Improve readme, fix setup.py and add support for Python 3.5. [\#51](https://github.com/ably/ably-python/pull/51) ([meiralins](https://github.com/meiralins))
- Minor adjustments to fit specs. [\#49](https://github.com/ably/ably-python/pull/49) ([meiralins](https://github.com/meiralins))
- More changes to auth to fit specs. [\#47](https://github.com/ably/ably-python/pull/47) ([meiralins](https://github.com/meiralins))
- Changes to auth to fit specs. [\#46](https://github.com/ably/ably-python/pull/46) ([aericson](https://github.com/aericson))
- Changes to client options [\#44](https://github.com/ably/ably-python/pull/44) ([aericson](https://github.com/aericson))
- RSA10: Auth\#authorise [\#43](https://github.com/ably/ably-python/pull/43) ([aericson](https://github.com/aericson))
- Done with stats, as well as varying every test to each protocol \(G1\) [\#41](https://github.com/ably/ably-python/pull/41) ([aericson](https://github.com/aericson))
- Requirements test [\#40](https://github.com/ably/ably-python/pull/40) ([aericson](https://github.com/aericson))
- Now when sending binary data messages one should use bytearray [\#39](https://github.com/ably/ably-python/pull/39) ([aericson](https://github.com/aericson))
- Fix travis [\#37](https://github.com/ably/ably-python/pull/37) ([aericson](https://github.com/aericson))
- Rsc7 and rsc18 [\#36](https://github.com/ably/ably-python/pull/36) ([aericson](https://github.com/aericson))
- Message pack [\#35](https://github.com/ably/ably-python/pull/35) ([aericson](https://github.com/aericson))
- Add Query time parameter TO3j10 and RSA9d [\#34](https://github.com/ably/ably-python/pull/34) ([aericson](https://github.com/aericson))
- Missing channel tests [\#33](https://github.com/ably/ably-python/pull/33) ([aericson](https://github.com/aericson))
- RSL2a and RSL2b3 - Channel\#history [\#31](https://github.com/ably/ably-python/pull/31) ([aericson](https://github.com/aericson))
- Message encoding [\#30](https://github.com/ably/ably-python/pull/30) ([aericson](https://github.com/aericson))
- RSC13 and RSC15 - Hosts fallback and timeouts [\#28](https://github.com/ably/ably-python/pull/28) ([fjsj](https://github.com/fjsj))
- RSP Presence, TG PaginatedResult and Presence Message TP [\#26](https://github.com/ably/ably-python/pull/26) ([aericson](https://github.com/aericson))
- \(RSL1d\) Indicates an error if the message was not successfully published to Ably [\#25](https://github.com/ably/ably-python/pull/25) ([fjsj](https://github.com/fjsj))
- Fix wrongly named tests [\#24](https://github.com/ably/ably-python/pull/24) ([fjsj](https://github.com/fjsj))
- RSL1a, RSL1b, RSL1e and RSL1c \(incomplete\) [\#21](https://github.com/ably/ably-python/pull/21) ([fjsj](https://github.com/fjsj))
- Channels - RSN1 to RSN4a [\#18](https://github.com/ably/ably-python/pull/18) ([fjsj](https://github.com/fjsj))
- Rsc1 api constructor [\#16](https://github.com/ably/ably-python/pull/16) ([aericson](https://github.com/aericson))
- Fix travis [\#15](https://github.com/ably/ably-python/pull/15) ([fjsj](https://github.com/fjsj))
- Fix tests except for crypto, messagepack and stats [\#14](https://github.com/ably/ably-python/pull/14) ([aericson](https://github.com/aericson))
- Fix the readme with the examples and the links [\#5](https://github.com/ably/ably-python/pull/5) ([matrixise](https://github.com/matrixise))
- Ably Python Rest Library Testing Fixes [\#3](https://github.com/ably/ably-python/pull/3) ([jcrubino](https://github.com/jcrubino))



\* *This Change Log was automatically generated by [github_changelog_generator](https://github.com/skywinder/Github-Changelog-Generator)*
