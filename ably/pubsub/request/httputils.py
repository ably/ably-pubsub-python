import base64
import ipaddress
import os
import platform

from ably.pubsub.version import api_version, lib_version


class HttpUtils:
    default_format = "json"

    mime_types = {
        "json": "application/json",
        "xml": "application/xml",
        "html": "text/html",
        "binary": "application/x-msgpack",
    }

    @staticmethod
    def default_get_headers(binary=False, version=None, agents=None):
        headers = HttpUtils.default_headers(version=version, agents=agents)
        if binary:
            headers["Accept"] = HttpUtils.mime_types['binary']
        else:
            headers["Accept"] = HttpUtils.mime_types['json']
        return headers

    @staticmethod
    def default_post_headers(binary=False, version=None, agents=None):
        headers = HttpUtils.default_get_headers(binary=binary, version=version, agents=agents)
        headers["Content-Type"] = headers["Accept"]
        return headers

    @staticmethod
    def host_for_url(host):
        """Renders a host for inclusion in a URL.

        An IPv6 literal is bracketed so that its colons are not read as a port
        separator; every other form of host is returned unchanged.
        """
        try:
            is_ipv6 = ipaddress.ip_address(host).version == 6
        except ValueError:
            is_ipv6 = False
        return f'[{host}]' if is_ipv6 else host

    @staticmethod
    def get_host_header(host):
        return {
            'Host': host,
        }

    @staticmethod
    def default_headers(version=None, agents=None):
        if version is None:
            version = api_version
        return {
            "X-Ably-Version": version,
            "Ably-Agent": HttpUtils.agent_string(agents),
        }

    @staticmethod
    def agent_string(agents=None):
        """The `Ably-Agent` value: the library and platform, then each of `agents` (RSC7d6).

        An entry with no version is emitted bare: versionless identifiers are flags, such
        as the side a package declares, and `name/None` is not a valid Ably-Agent token.
        """
        agent = f'ably-pubsub-python/{lib_version} python/{platform.python_version()}'
        for name, version in (agents or {}).items():
            agent += f' {name}/{version}' if version else f' {name}'
        return agent

    @staticmethod
    def get_query_params(options):
        params = {}

        if options.add_request_ids:
            params['request_id'] = base64.urlsafe_b64encode(os.urandom(12)).decode('ascii')

        return params
