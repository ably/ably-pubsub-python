"""Fixtures the REST integration specifications share.

The sandbox app is provisioned once and read by every test that asks for it.
Each test creating its own app would make the tier several times slower and
would invite the sandbox's rate limiting.
"""

import os

import pytest
import pytest_asyncio

from test.uts.helpers.sandbox import delete_app, provision_app

# `integration-testing.md` puts a suite of this size at 120 seconds, against
# operations each bounded at 10 to 30. The repository default in
# `pyproject.toml` is 30 seconds, which suits a test served from a mock and not
# one that provisions an app, publishes over the network and polls for the
# result. The marker applies to this package alone, so the unit tiers keep the
# tighter default.
SUITE_TIMEOUT = 120

__package_dir = os.path.dirname(os.path.abspath(__file__))


def pytest_collection_modifyitems(items):
    for item in items:
        if os.path.abspath(str(item.fspath)).startswith(__package_dir + os.sep):
            item.add_marker(pytest.mark.timeout(SUITE_TIMEOUT))


@pytest_asyncio.fixture(scope='session')
async def sandbox():
    """The provisioned sandbox app, as a specification's `app_config`.

    This is the specifications' `BEFORE ALL TESTS` / `AFTER ALL TESTS` pair.
    `sandbox.key(0).key_str` is the full-access key they call `api_key`, and
    the other indices are the capabilities named in each specification's app
    provisioning section.
    """
    app = await provision_app()
    yield app
    await delete_app(app)


@pytest.fixture(params=[False, True], ids=['json', 'msgpack'])
def use_binary_protocol(request):
    """Runs the test once per protocol, which is the specifications' `PROTOCOL`.

    A specification carrying a `## Protocol Variants` section runs against both
    json and msgpack, and passes this straight to its clients:

        client = sandbox_rest_client(api_key, use_binary_protocol=use_binary_protocol)

    Only a test that asks for it is parametrised. The six specifications
    without that section are json only, and their clients take the JSON default
    `sandbox_rest_client` already applies.
    """
    return request.param
