# Deviations

Departures from the Universal Test Specifications, and the reasoning for each.
Headings are fixed and appear even when they hold nothing.

## UTS Spec Errors

*(none)*

## Failing Tests

*(none)*

## Adapted Tests

*(none)*

## Mock Infrastructure Limitations

### Mocks are installed per-client rather than globally

The specifications install a mock with `install_mock(mock_http)` and note under
"Common Mistakes to Avoid" that a mock should not be passed to the client.
`mock_http.md` leaves the mechanism open: "The mechanism for injecting the mock
is implementation-specific and not part of the public API."

The HTTP client here is built during construction and held for the lifetime of
the client, so a mock is supplied as a client option and takes effect for that
client alone. Derived tests construct the mock before the client, and use
`await client.close()` where a specification calls `uninstall_mock()`.
