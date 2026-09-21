"""Version constants for the Ably Pub/Sub library.

These live in a module of their own rather than in a package ``__init__.py``
because ``ably.pubsub`` is a PEP 420 namespace package, shared with the other
``ably-pubsub-*`` distributions, and so cannot carry one.
"""

api_version = '5'
lib_version = '3.1.3'
