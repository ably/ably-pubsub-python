import asyncio
import functools
import os
import random
import string
import time
from typing import Awaitable, Callable
from unittest import mock

import msgpack
import respx
from httpx import Response

from ably.http.http import Http


class BaseTestCase:

    def respx_add_empty_msg_pack(self, url, method='GET'):
        respx.route(method=method, url=url).return_value = Response(
            status_code=200,
            headers={'content-type': 'application/x-msgpack'},
            content=msgpack.packb({})
        )

    @classmethod
    def get_channel_name(cls, prefix=''):
        return prefix + random_string(10)

    @classmethod
    def get_channel(cls, prefix=''):
        name = cls.get_channel_name(prefix)
        return cls.ably.channels.get(name)


class BaseAsyncTestCase:

    def respx_add_empty_msg_pack(self, url, method='GET'):
        respx.route(method=method, url=url).return_value = Response(
            status_code=200,
            headers={'content-type': 'application/x-msgpack'},
            content=msgpack.packb({})
        )

    @classmethod
    def get_channel_name(cls, prefix=''):
        return prefix + random_string(10)

    def get_channel(self, prefix=''):
        name = self.get_channel_name(prefix)
        return self.ably.channels.get(name)


def assert_responses_type(protocol):
    """
    This is a decorator to check if we retrieved responses with the correct protocol.
    usage:

    @assert_responses_type('json')
    def test_something(self):
        ...

    this will check if all responses received during the test will be in the format
    json.
    supports json and msgpack
    """
    responses = []

    def patch():
        original = Http.make_request

        async def fake_make_request(self, *args, **kwargs):
            response = await original(self, *args, **kwargs)
            responses.append(response)
            return response

        patcher = mock.patch.object(Http, 'make_request', fake_make_request)
        patcher.start()
        return patcher

    def unpatch(patcher):
        patcher.stop()

    def test_decorator(fn):
        @functools.wraps(fn)
        async def test_decorated(self, *args, **kwargs):
            patcher = patch()
            try:
                await fn(self, *args, **kwargs)
            finally:
                # The patch is undone however the test body exits, so Http.make_request is
                # left as it was found even when an assertion or a transport error escapes.
                unpatch(patcher)

            assert len(responses) >= 1, \
                "If your test doesn't make any requests, use the @dont_vary_protocol decorator"

            for response in responses:
                # In HTTP/2 some header fields are optional in case of 204 status code
                if protocol == 'json':
                    if response.status_code != 204:
                        assert response.headers['content-type'] == 'application/json'
                    if response.content:
                        response.json()
                else:
                    if response.status_code != 204:
                        assert response.headers['content-type'] == 'application/x-msgpack'
                    if response.content:
                        msgpack.unpackb(response.content)

        return test_decorated

    return test_decorator


class VaryByProtocolTestsMetaclass(type):
    """
    Metaclass to run tests in more than one protocol.
    Usage:
        * set this as metaclass of the TestCase class
        * create the following method:
        def per_protocol_setup(self, use_binary_protocol):
            # do something here that will run before each test.
        * now every test will run twice and before test is run per_protocol_setup
          is called
        * exclude tests with the @dont_vary_protocol decorator
    """

    def __new__(cls, clsname, bases, dct):
        for key, value in tuple(dct.items()):
            if key.startswith('test') and not getattr(value, 'dont_vary_protocol',
                                                      False):
                wrapper_bin = cls.wrap_as('bin', key, value)
                wrapper_text = cls.wrap_as('text', key, value)

                dct[key + '_bin'] = wrapper_bin
                dct[key + '_text'] = wrapper_text
                del dct[key]

        return super().__new__(cls, clsname, bases, dct)

    @staticmethod
    def wrap_as(ttype, old_name, old_func):
        expected_content = {'bin': 'msgpack', 'text': 'json'}

        @assert_responses_type(expected_content[ttype])
        async def wrapper(self):
            if hasattr(self, 'per_protocol_setup'):
                self.per_protocol_setup(ttype == 'bin')
            await old_func(self)

        wrapper.__name__ = old_name + '_' + ttype
        return wrapper


def dont_vary_protocol(func):
    func.dont_vary_protocol = True
    return func


def random_string(length, alphabet=string.ascii_letters):
    return ''.join([random.choice(alphabet) for x in range(length)])


def new_dict(src, **kw):
    new = src.copy()
    new.update(kw)
    return new


def get_random_key(d):
    return random.choice(list(d))


def get_submodule_dir(filepath):
    root_dir = os.path.dirname(filepath)
    while True:
        if os.path.exists(os.path.join(root_dir, 'submodules')):
            return os.path.join(root_dir, 'submodules')
        root_dir = os.path.dirname(root_dir)


async def assert_waiter(block: Callable[[], Awaitable[bool]], timeout: float = 10) -> None:
    """
    Polls a condition until it succeeds or times out.
    Args:
        block: A callable that returns a boolean indicating success
        timeout: Maximum time to wait in seconds (default: 10)
    Raises:
        TimeoutError: If condition not met within timeout
    """
    try:
        await asyncio.wait_for(_poll_until_success(block), timeout=timeout)
    except asyncio.TimeoutError:
        raise asyncio.TimeoutError(f"Condition not met within {timeout}s") from None


async def _poll_until_success(block: Callable[[], Awaitable[bool]]) -> None:
    while True:
        try:
            success = await block()
            if success:
                break
        except Exception:
            pass

        await asyncio.sleep(0.1)


def assert_waiter_sync(block: Callable[[], bool], timeout: float = 10) -> None:
    """
    Blocking version of assert_waiter that polls a condition until it succeeds or times out.
    Args:
        block: A callable that returns a boolean indicating success
        timeout: Maximum time to wait in seconds (default: 10)
    Raises:
        TimeoutError: If condition not met within timeout
    """
    start_time = time.time()

    while True:
        try:
            success = block()
            if success:
                break
        except Exception:
            pass

        if time.time() - start_time >= timeout:
            raise TimeoutError(f"Condition not met within {timeout}s")

        time.sleep(0.1)


class WaitableEvent:
    """
    Replacement for asyncio.Future that will work with autogenerated sync tests.
    """
    def __init__(self):
        self._finished = False

    def checker(self):
        async def inner_checker():
            return self._finished

        return inner_checker

    async def wait(self, timeout=10):
        await assert_waiter(self.checker(), timeout)

    def finish(self):
        self._finished = True

class ReusableFuture:
    """
    A reusable future that after each wait() resets itself and wait for the next value.
    """
    def __init__(self):
        self.__future = asyncio.Future()

    async def get(self, timeout=10):
        await asyncio.wait_for(self.__future, timeout=timeout)
        self.__future = asyncio.Future()

    def set_result(self, result):
        if not self.__future.done():
            self.__future.set_result(result)

    def set_exception(self, exception):
        if not self.__future.done():
            self.__future.set_exception(exception)
