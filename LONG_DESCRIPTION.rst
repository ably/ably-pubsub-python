Official Ably Pub/Sub Bindings for Python Servers
=================================================

A Python client library for Ably Pub/Sub realtime messaging, for use from
servers.


Setup
-----

You can install this package by using the pip tool and installing:

    pip install ably-pubsub-server

The package installs into ``ably.pubsub``. Both ``ably`` and ``ably.pubsub``
are namespace packages shared with the other ``ably-*`` distributions, so the
whole public API is reached through ``ably.pubsub.server``::

    from ably.pubsub.server import create_http_client, create_realtime_client


Using Ably for Python
---------------------

- Sign up for Ably at https://ably.com/sign-up
- Get usage examples at https://github.com/ably/ably-pubsub-python
- Visit https://ably.com/docs for a complete API reference and more examples
