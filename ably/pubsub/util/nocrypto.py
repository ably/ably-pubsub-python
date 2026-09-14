
class InstallPycrypto:
    def __getattr__(self, name):
        raise ImportError(
            "This requires to install ably with crypto support: pip install 'ably[crypto]'"
        )


AES = Random = InstallPycrypto()
