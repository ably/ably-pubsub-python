
class InstallPycrypto:
    def __getattr__(self, name):
        raise ImportError(
            "This requires ably-pubsub-server with crypto support: pip install 'ably-pubsub-server[crypto]'"
        )


AES = Random = InstallPycrypto()
