import pytest

from test.uts.helpers.client import close_open_clients


@pytest.fixture(autouse=True)
async def close_clients():
    """Closes the clients a test built through the UTS helpers, whether or not its assertions held."""
    yield
    await close_open_clients()
