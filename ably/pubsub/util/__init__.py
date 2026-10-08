import logging

# Silence "no handler" output for every logger in the library. This would
# normally go in the top-level package's __init__.py, but `ably.pubsub` is a
# PEP 420 namespace package and so has none; `ably.pubsub.util` is the one
# module every entry point, async and sync alike, imports on its way in. The
# unasync'd copy of this module runs the same line, hence the guard.
_root_logger = logging.getLogger('ably.pubsub')
if not any(isinstance(handler, logging.NullHandler) for handler in _root_logger.handlers):
    _root_logger.addHandler(logging.NullHandler())
