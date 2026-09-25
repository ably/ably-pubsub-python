"""Fixtures the realtime integration specifications share.

The sandbox app is provisioned once and read by every test that asks for it,
as it is for the REST integration tier: a specification's `BEFORE ALL TESTS`
provisions an app, and twenty specifications each provisioning their own would
make the tier several times slower and would invite the sandbox's rate
limiting.
"""

import os

import pytest
import pytest_asyncio

from test.uts.helpers.sandbox import delete_app, provision_app

# `integration-testing.md` puts a suite of this size at 120 seconds. The
# individual operations these specifications wait on are bounded at 10 to 30,
# and a realtime test spends longer than a REST one: it opens a connection,
# attaches a channel and waits on state changes before it asserts anything.
# The repository default in `pyproject.toml` is 30 seconds, which suits a test
# served from a mock. The marker applies to this package alone, so the unit
# tiers keep the tighter default.
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
    `realtime_sandbox.key(0).key_str` is the full-access key they call
    `api_key`, and the other indices are the capabilities named in each
    specification's app provisioning section.

    It is a separate app from the REST tier's `sandbox`, and separately named,
    so that a realtime test entering presence or publishing to a channel cannot
    be seen by a REST test reading the same channel name.
    """
    app = await provision_app()
    yield app
    await delete_app(app)


@pytest.fixture(params=[False, True], ids=['json', 'msgpack'])
def use_binary_protocol(request):
    """Runs the test once per protocol, which is the specifications' `PROTOCOL`.

    A specification carrying a `## Protocol Variants` section runs against both
    json and msgpack, and passes this straight to its clients:

        client = sandbox_realtime_client(api_key, use_binary_protocol=use_binary_protocol)

    Only a test that asks for it is parametrised. The specifications without
    that section are json only, and their clients take the JSON default
    `sandbox_realtime_client` already applies.
    """
    return request.param
