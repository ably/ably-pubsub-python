"""Fixtures the LiveObjects proxy integration specification shares.

The specification in this package runs its traffic through `uts-proxy`, so each
test opens a proxy session and closes it again afterwards. The `realtime_sandbox`
app the clients connect to comes from the parent package, which provisions it
once for the whole LiveObjects integration tier. The fixtures in
`test/uts/realtime/integration/proxy/conftest.py` are not visible from here, so
the same two are defined again; `ensure_proxy()` hands every caller the one
control process, so a run that collects both packages still starts only one.

`test/uts/helpers/proxy.py` describes the proxy itself and the two environment
variables that change how it is obtained and started.
"""

import os

import pytest
import pytest_asyncio

from test.uts.helpers.proxy import create_proxy_session, ensure_proxy, stop_proxy

# What a test in this package gets, in seconds, in place of the 120 the parent
# package gives the rest of the tier. The first proxy test to run waits for the
# binary to be downloaded on a cold cache and for the control process to come up,
# and a fault test sits through a disconnect, a reconnection and a second objects
# sync before it can assert anything.
SUITE_TIMEOUT = 300

__package_dir = os.path.dirname(os.path.abspath(__file__))


def pytest_collection_modifyitems(items):
    # The parent package marks everything beneath it, this package included, with
    # its own shorter timeout, and pytest-timeout reads the first of the item's own
    # markers. Putting this one at the front is what makes it the one read,
    # whichever order the two hooks happen to run in.
    for item in items:
        if os.path.abspath(str(item.fspath)).startswith(__package_dir + os.sep):
            item.add_marker(pytest.mark.timeout(SUITE_TIMEOUT), append=False)


@pytest_asyncio.fixture(scope='session')
async def proxy_control():
    """The running `uts-proxy` control API, shared by every test in the package.

    One control process serves any number of sessions, each on a port of its own,
    so it is started once and reaped when the run ends. `proxy_session` asks for
    this fixture, so a test that opens sessions does not have to.
    """
    await ensure_proxy()
    yield
    stop_proxy()


@pytest_asyncio.fixture
async def proxy_session(proxy_control):
    """Opens proxy sessions, and closes every one of them when the test ends.

    This is the specification's `create_proxy_session(...)` together with its
    `AFTER EACH TEST: IF session IS NOT null: session.close()`. A test calls it as
    it would the function:

        session = await proxy_session(rules=[...])

    and leaves the closing alone, so a test that fails part way through still
    gives its sessions back.
    """
    sessions = []

    async def open_session(**options):
        session = await create_proxy_session(**options)
        sessions.append(session)
        return session

    yield open_session

    for session in reversed(sessions):
        await session.close()
