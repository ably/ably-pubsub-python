"""Enforcement of the factories as the only way to build a client.

:mod:`ably.pubsub.server` exposes ``create_http_client`` and
``create_realtime_client`` rather than the client classes themselves, so that
the package a client comes from names the side the application runs on. The
classes stay importable for the library's own use and reject construction from
anywhere else.
"""

from contextlib import contextmanager
from contextvars import ContextVar

# True for the duration of a factory call. A ContextVar rather than a module
# global so that concurrent tasks cannot observe each other's state.
_in_factory: ContextVar = ContextVar('ably_pubsub_in_factory', default=False)


@contextmanager
def factory_construction():
    """Permit client construction within this block.

    For use by Ably's own factory functions only.
    """
    token = _in_factory.set(True)
    try:
        yield
    finally:
        _in_factory.reset(token)


def reject_direct_construction(cls: type, factory: str) -> None:
    """Raise unless we are inside a factory call.

    `factory` names the entry point the caller should have reached for, so
    that the error says what to do rather than only what went wrong.
    """
    if _in_factory.get():
        return
    raise TypeError(
        f'{cls.__name__} cannot be constructed directly. Use {factory} instead.'
    )
