import asyncio
import inspect
import json
import random
import string
import time
from typing import Callable, Dict, Tuple
from urllib.parse import parse_qs, urlparse

import msgpack

from ably.util.exceptions import AblyException


def get_random_id():
    # get random string of letters and digits
    source = string.ascii_letters + string.digits
    random_id = ''.join(random.choice(source) for i in range(8))
    return random_id


def is_callable_or_coroutine(value):
    return asyncio.iscoroutinefunction(value) or inspect.isfunction(value) or inspect.ismethod(value)


def unix_time_ms():
    return round(time.time_ns() / 1_000_000)


def is_token_error(exception):
    return 40140 <= exception.code < 40150


def extract_url_params(url: str) -> Tuple[str, Dict[str, str]]:
    """
    Extract URL parameters from a URL and return a clean URL and parameters dict.

    Args:
        url: The URL to parse

    Returns:
        Tuple of (clean_url_without_params, url_params_dict)
    """
    parsed_url = urlparse(url)
    url_params = {}

    if parsed_url.query:
        # Convert query parameters to a flat dictionary
        query_params = parse_qs(parsed_url.query)
        for key, values in query_params.items():
            # Take the last value if multiple values exist for the same key
            url_params[key] = values[-1]

    # Reconstruct clean URL without query parameters
    clean_url = f"{parsed_url.scheme}://{parsed_url.netloc}{parsed_url.path}"
    if parsed_url.fragment:
        clean_url += f"#{parsed_url.fragment}"

    return clean_url, url_params


class Timer:
    def __init__(self, timeout: float, callback: Callable):
        self._timeout = timeout
        self._callback = callback
        self._task = asyncio.create_task(self._job())

    async def _job(self):
        await asyncio.sleep(self._timeout / 1000)
        if asyncio.iscoroutinefunction(self._callback):
            await self._callback()
        else:
            self._callback()

    def cancel(self):
        self._task.cancel()


def select_timer(options) -> Callable:
    """The callable a client schedules its delayed callbacks with.

    `TestOptions.timer` substitutes for the real timer during tests, letting
    them drive time-dependent behaviour without waiting for it. Clients which
    supply none get `Timer`.
    """
    test_options = getattr(options, 'test_options', None)
    if test_options is not None and test_options.timer is not None:
        return test_options.timer
    return Timer

def validate_message_size(encoded_messages: list, use_binary_protocol: bool, max_message_size: int) -> None:
    """Validate that encoded messages don't exceed the maximum size limit.

    Args:
        encoded_messages: List of encoded message dictionaries
        use_binary_protocol: Whether to use binary (msgpack) or JSON encoding
        max_message_size: Maximum allowed size in bytes

    Raises:
        AblyException: If the encoded messages exceed the maximum size
    """
    if use_binary_protocol:
        size = len(msgpack.packb(encoded_messages, use_bin_type=True))
    else:
        size = len(json.dumps(encoded_messages, separators=(',', ':')).encode('utf-8'))

    if size > max_message_size:
        raise AblyException(
            f"Maximum size of messages that can be published at once exceeded "
            f"(was {size} bytes; limit is {max_message_size} bytes)",
            400,
            40009,
        )

def to_text(value):
    if value is None:
        return value
    elif isinstance(value, str):
        return value
    elif isinstance(value, bytes):
        return value.decode()
    else:
        raise TypeError(f"expected string or bytes, not {type(value)}")
