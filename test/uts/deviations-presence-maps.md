# Deviations — presence maps

Recorded while deriving `uts/realtime/unit/presence/presence_map.md`,
`presence_sync.md` and `local_presence_map.md` into
`test/uts/realtime/unit/presence/presence_map_test.py`,
`presence_sync_test.py` and `local_presence_map_test.py`.

These three specifications are white-box: they drive the presence map directly. The
governing note in `uts/docs/writing-derived-tests.md` on internal APIs whose shape
differs applies throughout — the shape is adapted, the coverage is kept.

## UTS Spec Errors

*(none)*

## Failing Tests

### RTP2h2b — a LEAVE arriving during a SYNC is emitted, and emitted again at endSync

- **Spec point:** RTP2h2a and RTP2h2b ("When the `SYNC` completes, then all `ABSENT`
  members in the presence map must be deleted. (No leave events should be emitted other
  than those required by `RTP19`)").
- **What the spec says:** a LEAVE received while a SYNC is in progress is stored as
  `ABSENT` and nothing is emitted. At `endSync` the `ABSENT` entry is deleted silently;
  only members never seen during the sync (residuals) earn a synthesized LEAVE.
- **What the SDK does:** a subscriber receives **three** `leave` events for that one
  member. Measured with a `RealtimePresence` driven by the sync in
  `test_rtp2h2a_leave_during_sync_absent_cleanup`:
  `[('present', 'alice'), ('leave', 'bob'), ('leave', 'bob'), ('leave', 'bob')]`.
- **Root cause:** three separate places.
  1. `PresenceMap.remove()` (`ably/realtime/presencemap.py:186-196`) returns `True` for
     the ABSENT store exactly as it does for a deletion, and
     `RealtimePresence.set_presence()` (`ably/realtime/presence.py:552-554`) broadcasts
     on the strength of that return value with no test of `sync_in_progress`. That is
     the first LEAVE, during the sync.
  2. `PresenceMap.remove()` does not take the member out of `_residual_members`, so a
     member that left during the sync is still a residual at `end_sync`
     (`presencemap.py:296-305`). That is the second LEAVE.
  3. `set_presence()` synthesizes a LEAVE for `residual + absent`
     (`presence.py:575-587`), where the `absent` list exists so the caller can *delete*
     those members, not announce them. That is the third.
- **Tests affected:** `test_rtp2h2a_leave_during_sync_absent_cleanup` (`@deviation`).
- **Status:** Gated. With `RUN_DEVIATIONS=1`:
  `assert leaves(events) == []` → `Left contains one more item: <PresenceMessage>`
  (`presence_sync_test.py:302`), failing on the first of the three LEAVEs.
- **Note:** the ABSENT storage itself is correct and is covered ungated by
  `test_rtp2h2a_leave_during_sync_stores_absent` and
  `test_rtp2h2b_absent_deleted_on_endsync` in `presence_map_test.py`.

### RTP17h — the RTP17 map applies the newness check across connectionIds

- **Spec point:** RTP17h, with RTP2a.
- **What the spec says:** the RTP17 map is keyed only by `clientId`, expressly so that
  "entries associated with old `connectionId`s would never be removed" cannot happen. An
  `ENTER` for `user-1` on `conn-B` therefore replaces the entry for `user-1` on `conn-A`.
- **What the SDK does:** the entry for `conn-A` survives. `_my_members` is a plain
  `PresenceMap` with `client_id` as its key function (`ably/realtime/presence.py:79-81`),
  so `put()` runs the full RTP2b newness comparison against whatever is under that key.
  Both messages are non-synthesized, so `_is_newer` takes the RTP2b2 path and compares
  `conn-B:0:0` against `conn-A:0:0` by `msgSerial` then `index` — 0 against 0, so the
  incoming message is not newer and is discarded.
- **Root cause:** RTP2a scopes the newness check to the *matching* member, "matching"
  meaning the same `connectionId` **and** `clientId`. An entry under the same key but a
  different `connectionId` is not a matching member, and `msgSerial` is only ordered
  within one connection, so comparing across connections is meaningless as well as
  wrong. `PresenceMap.put()` has no notion of the key function it was built with, so it
  cannot make that distinction.
- **Tests affected:** `test_rtp17h_keyed_by_clientid` (`@deviation`).
- **Status:** Gated. With `RUN_DEVIATIONS=1`:
  `AssertionError: assert 'first' == 'second'` (`local_presence_map_test.py:83`).

### RTP18a — a new sync does not discard the in-flight one's residual set

- **Spec point:** RTP18a ("If a new sequence identifier is sent from Ably, then the
  client library must consider that to be the start of a new sync sequence and any
  previous in-flight sync should be discarded").
- **What the spec says:** the second `startSync` re-snapshots the current map as the
  residual set, so the first sync's record of who had been seen is thrown away.
- **What the SDK does:** `PresenceMap.start_sync()` is guarded by
  `if not self._sync_in_progress:` (`ably/realtime/presencemap.py:255-262`), so a second
  call while a sync is running is a complete no-op and the first sync's residual set
  carries into the second. A member delivered by the first sync but absent from the
  second therefore survives, where the specification requires it to be evicted. Nothing
  else distinguishes one sync sequence from another either: `set_presence` parses the
  `channelSerial` only to decide whether the cursor is empty
  (`ably/realtime/presence.py:538-546`) and never stores the sequence identifier, so a
  genuinely new sequence id is indistinguishable from a continuation of the old one.
- **Tests affected:** none. `realtime/unit/RTP18a/new-sync-discards-previous-1` delivers
  both members in the second sync, which leaves the residual set empty under either
  behaviour, so `test_rtp18a_new_sync_discards_previous` passes without discriminating.
  Recorded here because the non-compliance is real; the UTS test would need a second
  sync that omits a member seen in the first to catch it.
- **Status:** Recorded, not gated.

### RTP19 — a synthesized LEAVE's timestamp is timezone-aware, every other one is naive

- **Spec point:** RTP19 and RTP19a ("the `timestamp` set to the current time"), against
  TP3g.
- **What the spec says:** nothing about the representation, but a `timestamp` a
  subscriber receives must be comparable with the `timestamp` on every other presence
  message.
- **What the SDK does:** `_synthesize_leaves` and `set_presence` build the LEAVE with
  `datetime.now(timezone.utc)` (`ably/realtime/presence.py:586`, `:720`), while every
  wire-derived presence message gets a naive `datetime` from `_dt_from_ms_epoch`
  (`ably/types/presence.py:12-19`, `:182-184`). Comparing the two raises
  `TypeError: can't compare offset-naive and offset-aware datetimes`, verified directly.
- **Root cause:** the two constructions of a `PresenceMessage.timestamp` disagree on
  awareness. Nothing inside the library compares them, because synthesized leaves are
  emitted rather than stored, so this surfaces only in application code.
- **Tests affected:** none — `test_rtp19_synth_leave_null_id_timestamp` brackets the
  LEAVE with two aware `datetime.now(timezone.utc)` readings and passes.
- **Status:** Recorded, not gated.

## Adapted Tests

### `put()` and `remove()` answer with a bool, not with the message to emit

- **Spec point:** the `Interface Under Test` block of all three specifications;
  RTP2d1, RTP2h1a.
- **What the spec says:** `put(message) -> PresenceMessage?` and
  `remove(message) -> PresenceMessage?`, returning the message to emit or null when the
  incoming message is stale.
- **What the SDK does:** both return `bool`
  (`ably/realtime/presencemap.py:111`, `:159`). The message to emit is the caller's own,
  which `RealtimePresence.set_presence` appends to `broadcast_messages` when the return
  value is true (`ably/realtime/presence.py:554`, `:567`). The behaviour is right; only
  the accessor differs.
- **Root cause:** internal API shape, not compliance. The house ruling on missing
  accessors applies.
- **Tests affected:** every test in `presence_map_test.py`; `IS NOT null` is read as
  `is True` and `IS null` as `is False`.
- **Status:** Adapted and running.

### RTP2d1's original action is asserted on the emitted event

- **Spec point:** RTP2d1.
- **What the spec says:** `put()` returns a message whose action is the original ENTER
  or UPDATE, while the stored copy is PRESENT.
- **What the SDK does:** `PresenceMap.put` stores a *copy* with the action rewritten to
  PRESENT (`ably/realtime/presencemap.py:125-136`) and leaves the incoming message
  untouched, so `set_presence` broadcasts it with its original action under the
  stringified event name. Correct behaviour, reached a different way.
- **Root cause:** as above.
- **Tests affected:** `test_rtp2d1_put_returns_original_action`, which asserts both that
  the incoming message is unmodified and that a `RealtimePresence` subscriber receives
  `enter` then `update` with those actions.
- **Status:** Adapted and running.

### `end_sync()` answers with `(residual, absent)`, not with synthesized LEAVE events

- **Spec point:** the `Interface Under Test` block of `presence_sync.md`; RTP19.
- **What the spec says:** `endSync() -> List<PresenceMessage>`, the synthesized LEAVE
  events.
- **What the SDK does:** `PresenceMap.end_sync()` returns a
  `(residual_members, absent_members)` tuple of the *stored* members — action PRESENT or
  ABSENT, original ids — and `RealtimePresence.set_presence` builds one synthesized LEAVE
  per member across both lists (`ably/realtime/presence.py:575-587`).
- **Root cause:** the synthesis lives one level up, in `RealtimePresence`, not in the map.
- **Tests affected:** tests reading only the count and the `clientId` go through a local
  `end_sync_leaves()` helper that concatenates the two lists, exactly as `set_presence`
  does. Tests reading the LEAVE itself — `test_rtp19_stale_members_leave_after_sync`,
  `test_rtp19_synth_leave_null_id_timestamp`, `test_rtp18c_single_message_sync`,
  `test_rtp19a_no_has_presence_clears_members` — drive a `RealtimePresence` with the same
  messages and assert on what its subscribers receive.
- **Status:** Adapted and running.

### There is no `LocalPresenceMap` type

- **Spec point:** the `Interface Under Test` block of `local_presence_map.md`; RTP17,
  RTP17h.
- **What the spec says:** a distinct `LocalPresenceMap` keyed by `clientId`.
- **What the SDK does:** `RealtimePresence._my_members` is the same `PresenceMap` class
  built with `member_key_fn=lambda msg: msg.client_id`
  (`ably/realtime/presence.py:79-81`). The keying requirement of RTP17h is met; see the
  Failing Tests entry for the part that is not.
- **Root cause:** one class serves both maps.
- **Tests affected:** all of `local_presence_map_test.py`, through a local
  `local_presence_map()` helper.
- **Status:** Adapted and running.

### RTP17b's synthesized-LEAVE filter sits in `set_presence`, not in `remove()`

- **Spec point:** RTP17b.
- **What the spec says:** a synthesized LEAVE must not be applied to the RTP17 map. The
  specification's own implementation note allows the check to live "either inside the
  presence map's `remove()` method, or at the calling level".
- **What the SDK does:** the calling level. `set_presence` guards the `_my_members`
  removal with `if presence.connection_id == conn_id and not presence.is_synthesized()`
  (`ably/realtime/presence.py:557-558`); `PresenceMap.remove()` itself would remove the
  member. Within the licence the note gives, this is compliant.
- **Root cause:** placement permitted by the specification.
- **Tests affected:** `test_rtp17b_synthesized_leave_ignored`, which drives
  `set_presence` rather than the map and asserts `_my_members` is untouched.
- **Status:** Adapted and running.

### RTP19a is driven through `on_attached`, not through a bare start/end sync

- **Spec point:** RTP19a.
- **What the spec says:** the data-structure equivalent of an ATTACHED without
  HAS_PRESENCE is `startSync()` followed immediately by `endSync()`.
- **What the SDK does:** `RealtimePresence.on_attached(has_presence=False)` does not go
  near the sync lifecycle: it calls `_synthesize_leaves(self.members.values())` and then
  `clear()` (`ably/realtime/presence.py:611-618`), which is the requirement itself rather
  than the model of it.
- **Root cause:** a shorter path to the same outcome.
- **Tests affected:** `test_rtp19a_no_has_presence_clears_members` calls
  `on_attached(has_presence=False)`. It is an async test because `on_attached` ends with
  `asyncio.create_task(self._send_pending_presence())`, and its members are given
  connectionIds other than the connection's own so that RTP17i re-entry has nothing to do.
- **Status:** Adapted and running.

## Mock Infrastructure Limitations

*(none)*
