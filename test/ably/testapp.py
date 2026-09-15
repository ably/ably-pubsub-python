import json
import logging
import os

# unasync rewrites `from ably.pubsub.server import ...` to the sync package, which
# is HTTP-only. Reaching the realtime factory through the module keeps the
# generated sync copy of this helper importable; it has no realtime tests.
import ably.pubsub.server
from ably.pubsub.server import create_http_client
from ably.pubsub.transport.defaults import Defaults
from ably.pubsub.types.capability import Capability
from ably.pubsub.types.options import Options
from ably.pubsub.util.exceptions import AblyException

log = logging.getLogger(__name__)

with open(os.path.dirname(__file__) + '/../assets/testAppSpec.json') as f:
    app_spec_local = json.loads(f.read())

tls = (os.environ.get('ABLY_TLS') or "true").lower() == "true"
endpoint = os.environ.get('ABLY_ENDPOINT', 'nonprod:sandbox')

port = 80
tls_port = 443

# Not named `ably`: that would shadow the `ably` package imported above, and
# `ably.pubsub.server.create_realtime_client` below would resolve against this
# client instead of the module.
app_setup_client = create_http_client(token='not_a_real_token',
                                      port=port, tls_port=tls_port, tls=tls,
                                      endpoint=endpoint,
                                      use_binary_protocol=False)


class TestApp:
    __test_vars = None

    @staticmethod
    async def get_test_vars():
        if not TestApp.__test_vars:
            r = await app_setup_client.http.post("/apps", body=app_spec_local, skip_auth=True)
            AblyException.raise_for_response(r)

            app_spec = r.json()

            app_id = app_spec.get("appId", "")

            test_vars = {
                "app_id": app_id,
                "port": port,
                "tls_port": tls_port,
                "tls": tls,
                "endpoint": endpoint,
                "host": Defaults.get_hostname(endpoint),
                "keys": [{
                    "key_name": "{}.{}".format(app_id, k.get("id", "")),
                    "key_secret": k.get("value", ""),
                    "key_str": "{}.{}:{}".format(app_id, k.get("id", ""), k.get("value", "")),
                    "capability": Capability(json.loads(k.get("capability", "{}"))),
                } for k in app_spec.get("keys", [])]
            }

            TestApp.__test_vars = test_vars
            log.debug([(app_id, k.get("id", ""), k.get("value", ""))
                      for k in app_spec.get("keys", [])])

        return TestApp.__test_vars

    @staticmethod
    async def get_ably_rest(**kw):
        test_vars = await TestApp.get_test_vars()
        options = TestApp.get_options(test_vars, **kw)
        options.update(kw)
        return create_http_client(**options)

    @staticmethod
    async def get_ably_realtime(**kw):
        test_vars = await TestApp.get_test_vars()
        options = TestApp.get_options(test_vars, **kw)
        return ably.pubsub.server.create_realtime_client(**options)

    @staticmethod
    def get_options(test_vars, **kwargs):
        options = {
            'port': test_vars["port"],
            'tls_port': test_vars["tls_port"],
            'tls': test_vars["tls"],
            'endpoint': test_vars["endpoint"],
        }
        auth_methods = ["auth_url", "auth_callback", "token", "token_details", "key"]
        if not any(x in kwargs for x in auth_methods):
            options["key"] = test_vars["keys"][0]["key_str"]

        options.update(kwargs)

        return options

    @staticmethod
    async def clear_test_vars():
        test_vars = TestApp.__test_vars
        options = Options(key=test_vars["keys"][0]["key_str"])
        options.port = test_vars["port"]
        options.tls_port = test_vars["tls_port"]
        options.tls = test_vars["tls"]
        ably = await TestApp.get_ably_rest()
        await ably.http.delete('/apps/' + test_vars['app_id'])
        TestApp.__test_vars = None
        await ably.close()
