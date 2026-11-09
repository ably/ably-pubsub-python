"""Fixtures the LiveObjects integration specifications share.

The sandbox app is provisioned once and read by every test that asks for it, as
it is for the realtime integration tier: each specification's `BEFORE ALL TESTS`
provisions an app, and provisioning one per file would make the tier slower and
invite the sandbox's rate limiting. The fixtures in
`test/uts/realtime/integration/conftest.py` are not visible from this package,
so the same shape is defined here; the app is a separate one from the realtime
tier's, so that a channel one tier writes objects to is never one the other
reads.
"""

import os

import pytest
import pytest_asyncio

from test.uts.helpers.sandbox import delete_app, provision_app

# `integration-testing.md` puts a suite of this size at 120 seconds. A LiveObjects
# test opens one or two connections, attaches, waits for the objects sync and then
# waits again for a mutation to reach a second client, each bounded at 10 to 30
# seconds. The repository default in `pyproject.toml` is 30 seconds, which suits a
# test served from a mock; the marker applies to this package alone.
SUITE_TIMEOUT = 120

__package_dir = os.path.dirname(os.path.abspath(__file__))


def pytest_collection_modifyitems(items):
    for item in items:
        if os.path.abspath(str(item.fspath)).startswith(__package_dir + os.sep):
            item.add_marker(pytest.mark.timeout(SUITE_TIMEOUT))


@pytest_asyncio.fixture(scope='session')
async def realtime_sandbox():
    """The provisioned sandbox app, as a specification's `app_config`.

    This is the specifications' `BEFORE ALL TESTS` / `AFTER ALL TESTS` pair.
    `realtime_sandbox.key_str` is the full-access key they call `api_key`.
    """
    app = await provision_app()
    yield app
    await delete_app(app)


@pytest.fixture(params=[False, True], ids=['json', 'msgpack'])
def use_binary_protocol(request):
    """Runs the test once per protocol, which is the specifications' `PROTOCOL`.

    The three specifications directly in this package carry a
    `## Protocol Variants` section, so their tests run against both json and
    msgpack and pass this straight to every client they build:

        client = sandbox_realtime_client(api_key, use_binary_protocol=use_binary_protocol)

    The proxy specification has no such section and runs json only, which the
    proxy requires in any case.
    """
    return request.param
