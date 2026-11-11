"""The agent entry a package stamps to declare which side it runs on.

Nothing here may grow into a general abstraction over the client: it exists only to
stamp the side a package's factories declare.
"""

# The `-server` suffix on this identifier is load-bearing, not cosmetic. On API-key auth
# the realtime system grants the server exemption from monthly-active-user counting by
# matching an agent entry ending in `-server`, and an identifier that is not yet in the
# ably-common registry is classified by that suffix alone. Renaming it without preserving
# its suffix silently reclassifies every client the package constructs as a device.
#
# It matches the identifier the other Pub/Sub SDKs' server packages send, and lives here
# rather than in `ably.pubsub.server` so the naming scheme can be changed in one place.
SERVER_AGENT_IDENTIFIER = 'ably-pubsub-server'


def options_with_side_agent(kwargs, identifier):
    """A copy of the caller's client options carrying the agent entry that declares the side.

    Only `agents` is replaced, with a new dict rather than by mutation, so the caller's
    options and their own `agents` dict are both left untouched. Every other option is
    copied by reference.

    The caller's `agents` entries are kept alongside the side stamp, so an SDK layered on
    top of this package keeps its attribution. The side stamp is applied last and so wins
    a collision on its own identifier: which side the package declares is the package's to
    state, not the caller's to redefine.

    The side entry is versionless — a flag — because the identifier is shared by every
    Pub/Sub SDK, so a version could not say what it versions, and would only duplicate the
    `ably-pubsub-python` entry sent alongside it.
    """
    return {**kwargs, 'agents': {**(kwargs.get('agents') or {}), identifier: None}}
