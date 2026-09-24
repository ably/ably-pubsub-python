"""The sandbox app the integration specifications run against, and its credentials.

Every integration specification opens with the same `BEFORE ALL TESTS` block:
POST the canonical app setup body to the sandbox, take the keys out of the
response, and DELETE the app when the tests are done.

Provisioning goes over plain `httpx` rather than through `AblyRest`. It is
infrastructure, and a client that cannot form a request would otherwise look
like a broken fixture rather than a failing test.

Also here are the pieces of the specifications' preamble that only make sense
against a real server: `random_id()` for the channel and client names the
specifications build, and the JWT signing the auth specification uses in place
of a third-party library.
"""

import base64
import hashlib
import hmac
import json
import logging
import os
import secrets
import time

import httpx

log = logging.getLogger(__name__)

# What a specification means by `endpoint: "nonprod:sandbox"`, and the URL the
# provisioning requests go to. The endpoint is for clients, which resolve it
# themselves; the URL is spelled out because provisioning does not go through
# the client.
SANDBOX_ENDPOINT = 'nonprod:sandbox'
SANDBOX_URL = 'https://sandbox.realtime.ably-nonprod.net'

# The wait `integration-testing.md` gives a provisioning or teardown request.
PROVISION_TIMEOUT = 30.0

# The channel the app setup pre-populates with presence members, which the
# presence specifications read rather than write.
PRESENCE_FIXTURES_CHANNEL = 'persisted:presence_fixtures'

# test/uts/assets/test-app-setup.json is a copy of
# test-resources/test-app-setup.json in ably/ably-common, carrying its
# `post_apps` and `cipher` objects and dropping the two comment keys beside
# them. The order of `post_apps.keys` is what the specifications index into —
# they name `keys[0]`, `keys[1]`, `keys[2]`, `keys[3]` and `keys[4]` and mean
# the capabilities that file gives at those positions, which are not the ones
# `test/assets/testAppSpec.json` gives. Refresh it from ably-common rather than
# editing it:
#
#   gh api "repos/ably/ably-common/contents/test-resources/test-app-setup.json" \
#       --jq '.content' | base64 -d
APP_SETUP_PATH = os.path.join(os.path.dirname(__file__), '..', 'assets', 'test-app-setup.json')

with open(APP_SETUP_PATH) as __asset:
    __app_setup = json.load(__asset)

APP_SETUP_BODY = __app_setup['post_apps']
CIPHER_FIXTURE = __app_setup['cipher']


def random_id(length=6):
    """A short unique suffix, for the names the specifications build.

    This is the specifications' `random_id()`, as in
    `"history-test-RSL2a-" + random_id()`. Channels and client ids have to be
    unique across tests and across concurrent runs against the same sandbox
    app, so the bytes come from `secrets` rather than from a seeded generator.
    """
    return base64.urlsafe_b64encode(secrets.token_bytes(length)).decode('ascii').rstrip('=')


def fixture_cipher_params():
    """The cipher the app setup encrypted the `client_encoded` fixture with.

    A presence specification reading that member builds its channel with
    `channels.get(name, cipher=fixture_cipher_params())`. The asset carries the
    key and the IV base64-encoded, which is not what `CipherParams` wants: it
    takes them as raw bytes and derives the key length from the key.
    """
    from ably.util.crypto import CipherParams

    return CipherParams(
        algorithm=CIPHER_FIXTURE['algorithm'],
        mode=CIPHER_FIXTURE['mode'],
        secret_key=base64.b64decode(CIPHER_FIXTURE['key']),
        iv=base64.b64decode(CIPHER_FIXTURE['iv']),
    )


class SandboxKey:
    """One of the app's API keys, as a specification's `app_config.keys[i]`."""

    def __init__(self, app_id, key):
        self.key_name = f"{app_id}.{key.get('id', '')}"
        self.key_secret = key.get('value', '')
        self.key_str = f'{self.key_name}:{self.key_secret}'
        self.capability = json.loads(key.get('capability') or '{}')

    def __repr__(self):
        return f'SandboxKey({self.key_name!r}, capability={self.capability!r})'


class SandboxApp:
    """A provisioned sandbox app, as a specification's `app_config`."""

    def __init__(self, response_body):
        self.app_id = response_body.get('appId', '')
        self.keys = [SandboxKey(self.app_id, key) for key in response_body.get('keys', [])]

    def key(self, index=0):
        """The key at `index`, which is the position `APP_SETUP_BODY` gave it.

        The specifications pick their credentials by index — `keys[0]` for full
        access, `keys[1]` for push admin, `keys[2]` for the per-channel
        capabilities, `keys[3]` for subscribe-only, `keys[4]` for revocable
        tokens — so an index here means the same thing it means in a spec.
        """
        return self.keys[index]

    @property
    def key_str(self):
        """The full-access key, which is what most specifications authenticate with."""
        return self.key(0).key_str

    def __repr__(self):
        return f'SandboxApp({self.app_id!r}, {len(self.keys)} keys)'


async def provision_app():
    """Creates a sandbox app from the canonical setup body.

    The app carries the keys the specifications index into and the presence
    fixtures they read, and lives until `delete_app` removes it or the sandbox
    expires it.
    """
    async with httpx.AsyncClient(timeout=PROVISION_TIMEOUT) as http:
        response = await http.post(f'{SANDBOX_URL}/apps', json=APP_SETUP_BODY)
    if response.status_code < 200 or response.status_code >= 300:
        raise AssertionError(
            f'Provisioning a sandbox app failed: {response.status_code} {response.text}')
    app = SandboxApp(response.json())
    log.info(f'provision_app(): created sandbox app {app.app_id}')
    return app


async def delete_app(app):
    """Deletes `app`, letting a failure to do so pass.

    Teardown is best effort. A sandbox app expires on its own, so an app left
    behind costs nothing, whereas a teardown that raises would fail a suite
    whose tests all passed.
    """
    key = app.key(0)
    try:
        async with httpx.AsyncClient(timeout=PROVISION_TIMEOUT) as http:
            response = await http.delete(
                f'{SANDBOX_URL}/apps/{app.app_id}',
                auth=(key.key_name, key.key_secret),
            )
        if response.status_code < 200 or response.status_code >= 300:
            log.warning(
                f'delete_app(): sandbox app {app.app_id} was not deleted: '
                f'{response.status_code} {response.text}')
        else:
            log.info(f'delete_app(): deleted sandbox app {app.app_id}')
    except Exception as error:
        log.warning(f'delete_app(): sandbox app {app.app_id} was not deleted: {error!r}')


def extract_key_name(api_key):
    """The key name half of `app_id.key_id:secret`."""
    return api_key.split(':', 1)[0]


def extract_key_secret(api_key):
    """The secret half of `app_id.key_id:secret`."""
    return api_key.split(':', 1)[1]


def generate_jwt(key_name, key_secret, ttl=3600000, client_id=None, capability=None, expires_at=None):
    """An Ably JWT signed with `key_secret`, as the auth specification's `generate_jwt`.

    The specification reaches for a third-party JWT library; an Ably JWT is
    HS256 over the key secret, so signing it here keeps the integration tier
    off a dependency the locked environment does not carry.

    `ttl` is milliseconds from now, as the specification passes it. `expires_at`
    overrides it with a unix time in seconds, which is how the token-renewal
    test asks for a JWT that has already expired. `capability` is a JSON string,
    defaulting to the whole app.

    The server reads a JWT's lifetime as `exp - iat` and rejects a negative one
    with 40003 before it ever considers whether the token has expired. So an
    `expires_at` in the past backdates `iat` by `ttl` rather than leaving it at
    now: the lifetime stays positive and the token is expired, which is the
    condition a renewal test is after.
    """
    seconds = int(ttl // 1000)
    issued_at = int(expires_at) - seconds if expires_at is not None else int(time.time())
    header = {'typ': 'JWT', 'alg': 'HS256', 'kid': key_name}
    claims = {
        'iat': issued_at,
        'exp': issued_at + seconds,
        'x-ably-capability': capability if capability is not None else '{"*":["*"]}',
    }
    if client_id is not None:
        claims['x-ably-clientId'] = client_id

    signing_input = b'.'.join(__jwt_segment(part) for part in (header, claims))
    signature = hmac.new(key_secret.encode('utf-8'), signing_input, hashlib.sha256).digest()
    return b'.'.join((signing_input, __base64url(signature))).decode('ascii')


def __jwt_segment(part):
    return __base64url(json.dumps(part, separators=(',', ':')).encode('utf-8'))


def __base64url(raw):
    # A JWT's segments are base64url with the padding stripped (RFC 7515 §2).
    return base64.urlsafe_b64encode(raw).rstrip(b'=')
