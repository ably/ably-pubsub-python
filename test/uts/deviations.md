# Deviations

Where the derived tests depart from the Universal Test Specifications, and why.
The closing section covers how the specifications are adopted here; everything
before it records behaviour.

Entries are grouped by root cause rather than by test, so one entry covers every
test it affects. Headings are fixed and appear even when they hold nothing.

Entries closed by a fix are removed rather than kept as history; `git log` holds that.

Run the gated tests with:

```
RUN_DEVIATIONS=1 uv run --extra crypto pytest test/uts
```

## UTS Spec Errors

Faults in the specifications themselves, found while deriving. A fault here is not an
SDK deviation, so it is recorded against the specification and not adapted to what the
SDK happens to do.

Where a specification *asserts* something `features.md` or `protocol.md` contradicts,
there is no spec-correct assertion left to write. The test is still derived faithfully
from the specification text, so that correcting the specification is all it takes to make
it pass, and it is marked `@spec_error` — a skip gated on `RUN_DEVIATIONS`, the same gate
`@deviation` uses, with a reason naming the specification rather than the SDK. The suite
stays green, a real regression still shows, and the failure is one environment variable
away. Each is filed upstream, in the issues named below.

Where instead only a specification's *fixture*, *setup* or *label* is at fault, the
assertion it carries still stands. Those tests keep the corrected fixture (or the
corrected label in a comment), pass, and carry a `# UTS SPEC ERROR:` comment at the
site. The entries below cover both kinds and say which applies.

The three sections that follow this one record SDK behaviour rather than specification
faults.

Raised upstream:

| Issue | Covers |
|---|---|
| [#523](https://github.com/ably/specification/issues/523) | `fallback.md` written against a mock API the contract does not define and the guide bans |
| [#524](https://github.com/ably/specification/issues/524) | `/time` stubbed as an object rather than an array |
| [#525](https://github.com/ably/specification/issues/525) | Spec points mislabelled across four specs |
| [#526](https://github.com/ably/specification/issues/526) | Presence actions written as strings, and wire action 4 asserted to be LEAVE |
| [#527](https://github.com/ably/specification/issues/527) | Wire encodings that contradict the features spec, and eight specs that read a body without pinning the protocol |
| [#528](https://github.com/ably/specification/issues/528) | Fixtures that cannot hold their stated values |
| [#529](https://github.com/ably/specification/issues/529) | Token expiry tests that demand optional behaviour |
| [#530](https://github.com/ably/specification/issues/530) | Token renewal driven through `/time` |
| [#531](https://github.com/ably/specification/issues/531) | `RSA10i` asserting that an API key survives `authorize()`, with no assertions |
| [#532](https://github.com/ably/specification/issues/532) | Housekeeping: a leaked local path, sections carrying no Test ID, a duplicate, misfiled tests |

Not every entry has an issue of its own: the URL-safe base64 alphabet is recorded below
and not filed, because ably-python's own encoding settles the tests either way. Line
references in these entries are against `ably/specification@d9a04ca`.


## Failing Tests

The specification's assertion is preserved and gated behind `@deviation`. Removing
the mark is the only change needed once the SDK behaviour lands.

## Adapted Tests

The test asserts what the SDK does, with the specification's expectation in a
comment above. These run, so they guard against regression.

## Mock Infrastructure Limitations
