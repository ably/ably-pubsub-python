"""Derived from uts/rest/unit/logging.md in ably/specification.

Spec points: RSC2, RSC2b, RSC3, RSC4, TO3b, TO3c, TO3c2

ably-python has no log_handler client option, and logs through the standard library
`logging` module: a handler attached to the `ably` logger is the idiomatic rendering of
the specification's `logHandler`. The `log_level` option exists but is never applied to
any logger, so the tests that turn on verbosity or silence it depart from the spec.
"""

import logging
from collections import namedtuple
from contextlib import contextmanager

from test.uts.helpers.client import rest_client
from test.uts.helpers.deviations import deviation
from test.uts.helpers.mock_http import MockHttpClient

SERVER_TIME_MS = 1704067200000

# The spec's verbose level, and a level above every level the standard library emits at,
# for the spec's `none`
LOG_LEVEL_VERBOSE = logging.DEBUG
LOG_LEVEL_NONE = logging.CRITICAL + 1

LogEvent = namedtuple('LogEvent', ['level', 'message', 'context'])


class _CapturingHandler(logging.Handler):
    """Records the SDK's log events in the shape the specification's handler receives."""

    def __init__(self, captured_logs):
        super().__init__(level=logging.NOTSET)
        self.__captured_logs = captured_logs

    def emit(self, record):
        # Standard library records carry no structured context map
        self.__captured_logs.append(LogEvent(record.levelno, record.getMessage(), {}))


@contextmanager
def capture_ably_logs(captured_logs, level=None):
    logger = logging.getLogger('ably')
    handler = _CapturingHandler(captured_logs)
    original_level = logger.level
    logger.addHandler(handler)
    if level is not None:
        logger.setLevel(level)
    try:
        yield
    finally:
        logger.removeHandler(handler)
        logger.setLevel(original_level)


def time_responder(request):
    request.respond_with(200, [SERVER_TIME_MS])


def connect_successfully(conn):
    conn.respond_with_success()


# UTS: rest/unit/RSC2/default-log-level-warn-0
async def test_rsc2_default_log_level_warn():
    # NOTE: the SDK sets no level on its loggers, so the effective level is the standard
    # library default of warning, and info, debug and verbose events are never emitted.
    captured_logs = []

    mock_http = MockHttpClient(on_connection_attempt=connect_successfully, on_request=time_responder)

    with capture_ably_logs(captured_logs):
        client = rest_client(mock_http)
        await client.time()

    assert all(log.level >= logging.WARNING for log in captured_logs)


# UTS: rest/unit/TO3b/log-level-changeable-0
@deviation
async def test_to3b_log_level_changeable():
    # DEVIATION: log_level is accepted and stored, but never applied to a logger, so raising
    # it to verbose emits nothing. The SDK also has no "HTTP request" log event.
    captured_logs = []

    mock_http = MockHttpClient(on_connection_attempt=connect_successfully, on_request=time_responder)

    with capture_ably_logs(captured_logs):
        client = rest_client(mock_http, log_level=LOG_LEVEL_VERBOSE)
        await client.time()

    info_logs = [log for log in captured_logs if log.level == logging.INFO]
    assert len(info_logs) > 0

    debug_logs = [log for log in captured_logs if log.level == logging.DEBUG]
    assert any('HTTP request' in log.message for log in debug_logs)


# UTS: rest/unit/TO3c/custom-handler-structured-events-0
@deviation
async def test_to3c_custom_handler_structured_events():
    # DEVIATION: there is no log_handler client option, so this raises TypeError on
    # construction. Log events also carry no structured context map.
    captured_logs = []

    mock_http = MockHttpClient(on_connection_attempt=connect_successfully, on_request=time_responder)

    def handler(level, message, context):
        captured_logs.append(LogEvent(level, message, context))

    client = rest_client(mock_http, log_level=logging.INFO, log_handler=handler)

    await client.time()

    assert len(captured_logs) > 0
    assert any(log.context for log in captured_logs)


# UTS: rest/unit/TO3c2/context-contains-expected-keys-0
@deviation
async def test_to3c2_context_contains_expected_keys():
    # DEVIATION: there is no log_handler client option, so this raises TypeError on
    # construction. Log events also carry no structured context map.
    captured_logs = []

    mock_http = MockHttpClient(on_connection_attempt=connect_successfully, on_request=time_responder)

    def handler(level, message, context):
        captured_logs.append(LogEvent(level, message, context))

    client = rest_client(mock_http, log_level=logging.DEBUG, log_handler=handler)

    await client.time()

    http_logs = [log for log in captured_logs
                 if 'HTTP request' in log.message and log.level == logging.DEBUG]
    assert len(http_logs) >= 1
    assert 'method' in http_logs[0].context
    assert 'host' in http_logs[0].context
    assert 'path' in http_logs[0].context


# UTS: rest/unit/RSC2b/log-level-none-suppresses-all-0
@deviation
async def test_rsc2b_log_level_none_suppresses_all():
    # DEVIATION: log_level is never applied, so it silences nothing. The SDK's logger is
    # turned up to debug first, so that suppression is observable at all.
    captured_logs = []

    mock_http = MockHttpClient(on_connection_attempt=connect_successfully, on_request=time_responder)

    with capture_ably_logs(captured_logs, level=logging.DEBUG):
        client = rest_client(mock_http, log_level=LOG_LEVEL_NONE)
        await client.time()

    assert len(captured_logs) == 0
