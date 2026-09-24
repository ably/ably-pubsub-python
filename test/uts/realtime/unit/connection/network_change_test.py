"""Derived from uts/realtime/unit/connection/network_change_test.md in ably/specification.

Spec points: RTN20, RTN20a, RTN20b, RTN20c
"""

import pytest

NETWORK_LISTENER_SKIP = (
    'RTN20 applies only "when the client library can subscribe to OS events for '
    'network/internet connectivity changes". ably-python subscribes to none, and has no '
    'network connectivity listener interface for a mock to stand in for, so there is '
    'nothing to install and no event to simulate. The specification itself lists Python '
    'as a platform where RTN20 may not apply and says such SDKs should skip these tests. '
    'See deviations.md.')


# UTS: realtime/unit/RTN20a/network-loss-connected-disconnects-0
@pytest.mark.skip(reason=NETWORK_LISTENER_SKIP)
async def test_rtn20a_network_loss_connected_disconnects():
    pass


# UTS: realtime/unit/RTN20a/network-loss-connecting-disconnects-1
@pytest.mark.skip(reason=NETWORK_LISTENER_SKIP)
async def test_rtn20a_network_loss_connecting_disconnects():
    pass


# UTS: realtime/unit/RTN20b/network-available-disconnected-connects-0
@pytest.mark.skip(reason=NETWORK_LISTENER_SKIP)
async def test_rtn20b_network_available_disconnected_connects():
    pass


# UTS: realtime/unit/RTN20c/network-available-connecting-restarts-0
@pytest.mark.skip(reason=NETWORK_LISTENER_SKIP)
async def test_rtn20c_network_available_connecting_restarts():
    pass
