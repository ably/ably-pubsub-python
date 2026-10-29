import asyncio
import inspect
import random
import string
import time
from typing import Callable, Dict, Tuple
from urllib.parse import parse_qs, urlparse


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


def to_text(value):
    if value is None:
        return value
    elif isinstance(value, str):
        return value
    elif isinstance(value, bytes):
        return value.decode()
    else:
        raise TypeError(f"expected string or bytes, not {type(value)}")
