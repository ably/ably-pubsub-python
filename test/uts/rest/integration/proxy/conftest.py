"""Fixtures the proxy integration specifications share.

The specifications in this package run their traffic through `uts-proxy`, so
each of them opens with a proxy session and closes it again afterwards. The
`sandbox` app they publish to comes from the parent package, which provisions
it once for the whole REST integration tier.

`test/uts/helpers/proxy.py` describes the proxy itself and the two environment
variables that change how it is obtained and started.
"""

import os

import pytest
import pytest_asyncio

from test.uts.helpers.proxy import create_proxy_session, ensure_proxy, stop_proxy

# What a test in this package gets, in seconds, in place of the 120 the parent
# package gives the rest of the tier. A proxy test spends its budget on things
# the other integration tests do not: the first one to run waits for the
# binary to be downloaded on a cold cache and for the control process to come
# up, and a specification that provokes a timeout deliberately sits through
# a twenty-second delay before the request it is measuring even fails.
SUITE_TIMEOUT = 300

__package_dir = os.path.dirname(os.path.abspath(__file__))


def pytest_collection_modifyitems(items):
    # The parent package marks everything beneath it, this package included,
    # with its own shorter timeout, and pytest-timeout reads the marker
    # closest to the test — the first of the item's own markers. Putting this
    # one at the front rather than on the end is what makes it the one read,
    # whichever order the two hooks happen to run in.
    for item in items:
        if os.path.abspath(str(item.fspath)).startswith(__package_dir + os.sep):
            item.add_marker(pytest.mark.timeout(SUITE_TIMEOUT), append=False)


@pytest_asyncio.fixture(scope='session')
async def proxy_control():
    """The running `uts-proxy` control API, shared by every test in the package.

    One control process serves any number of sessions, each on a port of its
    own, so it is started once and reaped when the run ends. Asking for this
    fixture is what guarantees a proxy is up; `proxy_session` asks for it, so
    a test that opens sessions does not have to.
    """
    await ensure_proxy()
    yield
    stop_proxy()


@pytest_asyncio.fixture
async def proxy_session(proxy_control):
    """Opens proxy sessions, and closes every one of them when the test ends.

    This is the specifications' `create_proxy_session(...)` together with
    their `AFTER EACH TEST: IF session IS NOT null: session.close()`. A test
    calls it as it would the function:

        session = await proxy_session(rules=[...])

    and leaves the closing alone. Each session holds a port and an event log
    on the proxy until it is closed, so a test that fails part way through —
    which, in a suite about faults, is the case worth planning for — still
    gives them back.
    """
    sessions = []

    async def open_session(**options):
        session = await create_proxy_session(**options)
        sessions.append(session)
        return session

    yield open_session

    for session in reversed(sessions):
        await session.close()
