"""The programmable proxy the proxy integration specifications route their traffic through.

`uts/docs/proxy.md` puts [ably/uts-proxy](https://github.com/ably/uts-proxy)
between the SDK and the sandbox. The proxy runs a control API on one port and
binds a fresh port for each session opened through it; a client under test is
built with `endpoint='localhost'`, `port=session.proxy_port` and `tls=False`,
so its traffic arrives at the session port in the clear and the proxy speaks
TLS onwards to the sandbox. Rules attached to a session drop connections,
delay them, or answer them with a response the sandbox would never give, which
is how a specification exercises a fault path against the real server.

Three things have to be true before a test can do any of that, and this module
is responsible for all three.

The binary has to be on disk. The pinned release is downloaded from GitHub
into `~/.cache/uts-proxy/<version>/`, its archive checked against the sha256
the release publishes, and the `uts-proxy` entry extracted out of it. The
download is serialised across processes by an `fcntl.flock` on a lock file
beside the binary: CI runs the suite once per supported Python version and a
developer may run pytest under `-n`, so several processes can arrive at an
empty cache together. Setting `UTS_PROXY_LOCAL_PATH` to a locally built binary
or to a `.tar.gz` holding one takes the place of the download, which is how a
change to the proxy itself is tried out ahead of a release.

The control process has to be running. `ensure_proxy()` starts one for the
test session and `stop_proxy()` reaps it; between them the process is shared,
because a session port is per-session and one control process serves any
number of them. The port it listens on is chosen free rather than fixed, so
two suites on one machine do not collide, and `UTS_PROXY_CONTROL_URL` points
the harness at a proxy someone is already running instead of starting one.

A session has to exist. `create_proxy_session()` is the specifications'
function of that name and returns the `ProxySession` they drive.

Everything here talks to the control API over plain `httpx`, the way
`sandbox.py` talks to the sandbox's provisioning API. It is infrastructure,
and a proxy that could not be reached should look like broken infrastructure
rather than a failing assertion.
"""

import asyncio
import atexit
import fcntl
import hashlib
import io
import logging
import os
import platform
import shutil
import socket
import subprocess
import sys
import tarfile
import tempfile
from urllib.parse import urlsplit

import httpx

from test.uts.helpers.sandbox import SANDBOX_ENDPOINT, SANDBOX_URL

log = logging.getLogger(__name__)

# The release the suite is pinned to. The cache directory is keyed on it, so
# moving the pin downloads afresh rather than reusing the old binary.
PROXY_VERSION = 'v0.3.0'

# The sha256 of each release archive, copied from the release's own
# `checksums.txt`. The archive is what is verified, not the binary extracted
# from it, so a tampered download is rejected before anything is written to
# the cache and never becomes something a later run treats as a hit.
ARCHIVE_CHECKSUMS = {
    'uts-proxy_0.3.0_darwin_amd64.tar.gz':
        '1355526543c3022f87efb7f564f55200b78edc68d84c7dba2e49f63429e3b788',
    'uts-proxy_0.3.0_darwin_arm64.tar.gz':
        'a948f99b7daf9b3bffff742f6405637d40a79947389309eed5f87e59026de9a5',
    'uts-proxy_0.3.0_linux_amd64.tar.gz':
        'de741ba21f3630fea4f59714d00585638d565005599ecd84179931eba248f280',
    'uts-proxy_0.3.0_linux_arm64.tar.gz':
        '15b5ca87c40c2c4ff350c94af1911cea0ad6be5a2d890ba41029bc4b8bc52c61',
}

RELEASE_URL = f'https://github.com/ably/uts-proxy/releases/download/{PROXY_VERSION}'

BINARY_NAME = 'uts-proxy'
CACHE_ROOT = os.path.join(os.path.expanduser('~'), '.cache', 'uts-proxy')
CACHE_DIR = os.path.join(CACHE_ROOT, PROXY_VERSION)
LOCK_PATH = os.path.join(CACHE_DIR, 'uts-proxy.lock')

# A locally built binary, or a `.tar.gz` distributive holding one, in place of
# the pinned release. The name is the one the Kotlin harness uses, so a
# developer with both checkouts sets it once.
LOCAL_PATH_VAR = 'UTS_PROXY_LOCAL_PATH'

# The base URL of a control API someone else is running, as
# `http://localhost:9100`. When it is set nothing is downloaded and nothing is
# spawned, and the proxy outlives the test run because the test run did not
# start it.
CONTROL_URL_VAR = 'UTS_PROXY_CONTROL_URL'

# Where a local distributive is unpacked. It is kept apart from the pinned
# version's directory so that unpacking a development build does not leave
# something in the cache that a later run, without the override set, would
# mistake for the release.
LOCAL_CACHE_DIR = os.path.join(CACHE_ROOT, 'local')

# The upstream host a specification's `endpoint` names. The proxy is told a
# host rather than an endpoint, because it is not an Ably client and does not
# resolve endpoints; `nonprod:sandbox` serves both realtime and REST from the
# one host.
SANDBOX_HOST = urlsplit(SANDBOX_URL).hostname
TARGET_HOSTS = {SANDBOX_ENDPOINT: SANDBOX_HOST}

# How long a release download may take. Generous: the archive is a few
# megabytes and a cold CI runner fetches it over whatever link it has.
DOWNLOAD_TIMEOUT = 60.0

# How long a control API call may take. A control call is local and answers
# immediately, so a wait this long means the proxy has stopped serving.
CONTROL_TIMEOUT = 15.0

# How long a freshly spawned proxy is given to answer `/health`, and how often
# it is asked. The single health check is bounded far shorter than a control
# call, so that the poll keeps its cadence while the port is still refusing.
STARTUP_TIMEOUT = 15.0
STARTUP_INTERVAL = 0.2
HEALTH_TIMEOUT = 2.0

# How long a proxy is given to exit on SIGTERM before it is killed outright.
SHUTDOWN_TIMEOUT = 5.0

# The session's idle auto-cleanup timer, in milliseconds, which is a
# specification's `timeoutMs`. The proxy's own default is 30000, measured from
# the last piece of traffic through the session; a test that delays a response
# by twenty seconds and then reads the event log spends longer than that idle,
# and would find its session already torn down.
SESSION_TIMEOUT_MS = 120000

__control_url = None
__process = None
__process_output = None


def control_url():
    """The base URL of the control API this test run is using.

    Raises if the proxy has not been started, since a control call made before
    `ensure_proxy()` would otherwise fail as a connection error against
    whatever happens to be listening.
    """
    if __control_url is None:
        raise AssertionError(
            'The uts-proxy control API is not running. A test reaching the proxy asks for the '
            'fixture that calls ensure_proxy() first.')
    return __control_url


async def ensure_proxy(timeout=STARTUP_TIMEOUT):
    """Makes sure a control API is running, and returns its base URL.

    Called again once the proxy is up, this answers with the URL it already
    has: the process is shared for the whole test run, so a second caller must
    not start a second one.

    With `UTS_PROXY_CONTROL_URL` set, the proxy named there is used as it
    stands. It is health-checked all the same, so that a stale value in a
    developer's environment is reported as itself rather than as every proxy
    test failing to create a session.
    """
    global __control_url, __process, __process_output

    if __control_url is not None:
        return __control_url

    external = os.environ.get(CONTROL_URL_VAR)
    if external:
        external = external.rstrip('/')
        if not await _is_healthy(external):
            raise AssertionError(
                f'{CONTROL_URL_VAR} is set to {external}, where nothing answered GET /health. '
                'Start a uts-proxy there, or unset the variable to have one started here.')
        log.info(f'ensure_proxy(): using the uts-proxy already running at {external}')
        __control_url = external
        return __control_url

    loop = asyncio.get_running_loop()
    binary = await loop.run_in_executor(None, _ensure_binary)

    # The port is bound, read back and released before the proxy is told to
    # take it, so there is a moment in which something else could claim it.
    # Nothing on the machine is hunting for a port to steal, and the
    # alternative — a fixed port — collides with the suite running twice.
    port = _free_port()
    url = f'http://localhost:{port}'

    # The proxy's own output goes to a temporary file rather than to the
    # terminal, where it would interleave with pytest's, and is read back if
    # the process never becomes healthy. That is the one moment its output is
    # worth having, and the one moment nothing else can explain the failure.
    output = tempfile.TemporaryFile()
    log.info(f'ensure_proxy(): starting {binary} on port {port}')
    process = subprocess.Popen(
        [binary, '--port', str(port)],
        stdin=subprocess.DEVNULL,
        stdout=output,
        stderr=subprocess.STDOUT,
    )

    try:
        await _wait_for_health(process, output, url, timeout)
    except BaseException:
        _reap(process)
        output.close()
        raise

    __process = process
    __process_output = output
    __control_url = url
    return url


def stop_proxy():
    """Stops the proxy this test run started, if it started one.

    Registered to run at interpreter exit as well as being called from the
    fixture that started it, because a `Popen` child does not die with its
    parent: a suite interrupted between the two would otherwise leave a proxy
    holding its control port for as long as the machine is up.
    """
    global __control_url, __process, __process_output

    __control_url = None
    process, __process = __process, None
    output, __process_output = __process_output, None

    if process is not None:
        _reap(process)
    if output is not None:
        output.close()


atexit.register(stop_proxy)


async def create_proxy_session(endpoint=SANDBOX_ENDPOINT, port=None, rules=None,
                               timeout_ms=SESSION_TIMEOUT_MS):
    """Opens a proxy session against `endpoint`, as the specifications' function of that name.

    `rules` are the rule objects a specification writes out as JSON, passed
    through to the control API unchanged — `{'match': {...}, 'action': {...},
    'times': 1, 'comment': '...'}`, with the key spellings the proxy's API
    reference gives. They are left as plain dictionaries rather than wrapped,
    so that a derived test reads as the specification it came from and a rule
    the proxy grows tomorrow needs nothing here.

    `port` asks for a particular session port, which the control API answers
    with 409 if it is taken. Left out, the proxy binds a free one and reports
    it back as `proxy_port`.

    `timeout_ms` is the session's idle timeout, not a deadline for the test.
    """
    host = TARGET_HOSTS.get(endpoint)
    if host is None:
        raise AssertionError(
            f'No upstream host is known for endpoint {endpoint!r}; '
            f'the endpoints this harness resolves are {sorted(TARGET_HOSTS)}.')

    body = {
        'target': {'realtimeHost': host, 'restHost': host},
        'rules': list(rules) if rules else [],
    }
    if port is not None:
        body['port'] = port
    if timeout_ms is not None:
        body['timeoutMs'] = timeout_ms

    base = control_url()
    created = await _control_request('POST', f'{base}/sessions', body)

    session_id = created.get('sessionId')
    assigned = (created.get('proxy') or {}).get('port', port)
    if not session_id or not isinstance(assigned, int):
        raise AssertionError(
            f'The uts-proxy control API answered POST /sessions with {created!r}, which names '
            'no session id or no port.')

    log.info(f'create_proxy_session(): session {session_id} proxying localhost:{assigned} to {host}')
    return ProxySession(session_id, assigned, base)


class ProxySession:
    """One session on the proxy, as a specification's `session`.

    A session owns a port of its own, and the rules and event log that go with
    it. A test builds its client against `proxy_host` and `proxy_port`, runs
    its scenario, reads `get_log()` for the traffic the proxy saw, and closes
    the session — which is what frees the port again.
    """

    def __init__(self, session_id, proxy_port, control_url, proxy_host='localhost'):
        self.session_id = session_id
        self.proxy_host = proxy_host
        self.proxy_port = proxy_port
        self.control_url = control_url
        self.closed = False

    @property
    def _session_url(self):
        return f'{self.control_url}/sessions/{self.session_id}'

    async def add_rules(self, rules, position='append'):
        """Adds `rules` to the session while it is running.

        `position` is `'append'` or `'prepend'`. Rules are evaluated in order
        and the first match wins, so a rule added to the front takes
        precedence over everything the session was created with — which is how
        a specification faults traffic only after the client has reached a
        state it wants to fault it from.
        """
        await _control_request('POST', f'{self._session_url}/rules', {
            'rules': list(rules),
            'position': position,
        })

    async def trigger_action(self, action):
        """Performs `action` on the session's live WebSocket connection, now.

        This is the imperative half of the proxy's interface, for what a timed
        rule says awkwardly: `{'type': 'disconnect'}`,
        `{'type': 'close', 'closeCode': 1000}`, or an `inject_to_client`
        carrying the protocol message to plant. The control API answers 409
        when no connection is open, which surfaces here as a failure naming
        that, rather than as the action quietly doing nothing.
        """
        await _control_request('POST', f'{self._session_url}/actions', dict(action))

    async def get_log(self):
        """Every event the proxy recorded for this session, in order.

        Each event is the dictionary the control API sent, with the field
        names its reference gives: `type`, `direction`, `path`, `status`,
        `queryParams`, `message`, `ruleMatched` and the rest, absent where
        they do not apply. A specification's assertions are written against
        those names, so they are carried through rather than renamed:

            requests = [event for event in await session.get_log()
                        if event['type'] == 'http_request' and '/time' in event['path']]
        """
        body = await _control_request('GET', f'{self._session_url}/log')
        return body.get('events') or []

    async def close(self):
        """Tears the session down, closing its connections and freeing its port.

        Teardown is best effort and never raises. A session the proxy has
        already expired, or one whose proxy has gone, is nothing a passing
        test should be failed over, and the idle timeout collects anything
        left behind. Closing twice is harmless, since the fixture closes every
        session it handed out whether or not the test closed it too.
        """
        if self.closed:
            return
        self.closed = True
        try:
            await _control_request('DELETE', self._session_url)
        except Exception as error:
            log.warning(f'ProxySession.close(): session {self.session_id} was not closed: {error!r}')

    def __repr__(self):
        return f'ProxySession({self.session_id!r}, {self.proxy_host}:{self.proxy_port})'


async def _control_request(method, url, body=None):
    """Makes one call to the control API and returns its decoded body.

    A fresh `httpx.AsyncClient` per call, as in `sandbox.py`: these calls are
    occasional, and a client held across calls would be bound to the event
    loop that built it, which is not the loop every caller runs on.
    """
    async with httpx.AsyncClient(timeout=CONTROL_TIMEOUT) as http:
        response = await http.request(method, url, json=body)
    if response.status_code < 200 or response.status_code >= 300:
        raise AssertionError(
            f'The uts-proxy control API answered {method} {url} with '
            f'{response.status_code} {response.text}')
    if not response.content:
        return {}
    return response.json()


async def _is_healthy(url):
    """Whether a control API is answering at `url`."""
    try:
        async with httpx.AsyncClient(timeout=HEALTH_TIMEOUT) as http:
            response = await http.get(f'{url}/health')
    except Exception:
        return False
    return response.status_code == 200


async def _wait_for_health(process, output, url, timeout):
    """Waits for a freshly started proxy to answer `/health`.

    A proxy that exits — because its port was taken between being chosen and
    being bound, or because the binary will not run on this machine — is
    noticed as soon as it happens rather than at the end of the timeout, and
    what it printed on its way out is quoted.
    """
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    while True:
        if process.poll() is not None:
            raise AssertionError(
                f'uts-proxy exited with status {process.returncode} before answering GET '
                f'{url}/health:\n{_read_output(output)}')
        if await _is_healthy(url):
            return
        if loop.time() >= deadline:
            raise AssertionError(
                f'uts-proxy did not answer GET {url}/health within {timeout}s:\n'
                f'{_read_output(output)}')
        await asyncio.sleep(STARTUP_INTERVAL)


def _read_output(output):
    """Whatever the proxy has written to its output file so far."""
    try:
        output.seek(0)
        return output.read().decode('utf-8', 'replace').strip() or '(no output)'
    except Exception as error:
        return f'(the proxy output could not be read: {error!r})'


def _reap(process):
    """Ends `process`, politely and then not."""
    if process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(SHUTDOWN_TIMEOUT)
    except subprocess.TimeoutExpired:
        log.warning(f'_reap(): uts-proxy {process.pid} ignored SIGTERM, killing it')
        process.kill()
        process.wait()


def _free_port():
    """A port nothing is listening on, from the ephemeral range."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(('127.0.0.1', 0))
        return sock.getsockname()[1]


def _ensure_binary():
    """The path to a `uts-proxy` binary, downloading the pinned release if need be.

    Blocking throughout — it holds a file lock across a network download — so
    callers run it off the event loop.
    """
    local = os.environ.get(LOCAL_PATH_VAR)
    if local:
        return _install_local(local)

    os.makedirs(CACHE_DIR, exist_ok=True)
    target = os.path.join(CACHE_DIR, BINARY_NAME)

    # The lock is held across the check as well as the download, so that a
    # process arriving while another is mid-download waits and then sees the
    # finished binary rather than starting a download of its own.
    with open(LOCK_PATH, 'w') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if os.path.exists(target) and os.access(target, os.X_OK):
            log.debug(f'_ensure_binary(): {target} is already cached')
            return target
        archive_name = _archive_name()
        archive = _download_archive(archive_name)
        _verify_checksum(archive_name, archive)
        _extract_binary(archive_name, archive, target)
        log.info(f'_ensure_binary(): installed uts-proxy {PROXY_VERSION} at {target}')
        return target


def _install_local(path):
    """The binary `UTS_PROXY_LOCAL_PATH` names, unpacking it first if it is an archive.

    A path to a binary is used where it lies, so that rebuilding the proxy is
    enough to pick the new build up. A `.tar.gz` is unpacked into a directory
    of its own, away from the pinned release's, because a development build
    sitting where the release belongs would be picked up by every later run
    whether or not the override was still set.
    """
    if not os.path.exists(path):
        raise AssertionError(f'{LOCAL_PATH_VAR} is set to {path}, which does not exist.')

    if path.endswith('.tar.gz') or path.endswith('.tgz'):
        os.makedirs(LOCAL_CACHE_DIR, exist_ok=True)
        target = os.path.join(LOCAL_CACHE_DIR, BINARY_NAME)
        with open(path, 'rb') as archive:
            _extract_binary(os.path.basename(path), archive.read(), target)
        log.info(f'_install_local(): unpacked {path} to {target}')
        return target

    if not os.access(path, os.X_OK):
        raise AssertionError(f'{LOCAL_PATH_VAR} is set to {path}, which is not executable.')
    log.info(f'_install_local(): using the uts-proxy binary at {path}')
    return path


def _archive_name():
    """The release asset for this machine.

    The platforms are the ones the release publishes, which are the ones the
    checksum table covers; anything else is named in the failure rather than
    being downloaded and found to be for the wrong architecture.
    """
    if sys.platform.startswith('darwin'):
        operating_system = 'darwin'
    elif sys.platform.startswith('linux'):
        operating_system = 'linux'
    else:
        raise AssertionError(
            f'uts-proxy publishes no release for {sys.platform}. Build it and point '
            f'{LOCAL_PATH_VAR} at the binary.')

    machine = platform.machine().lower()
    if machine in ('x86_64', 'amd64'):
        architecture = 'amd64'
    elif machine in ('arm64', 'aarch64'):
        architecture = 'arm64'
    else:
        raise AssertionError(
            f'uts-proxy publishes no release for {machine}. Build it and point '
            f'{LOCAL_PATH_VAR} at the binary.')

    name = f'{BINARY_NAME}_{PROXY_VERSION.lstrip("v")}_{operating_system}_{architecture}.tar.gz'
    if name not in ARCHIVE_CHECKSUMS:
        raise AssertionError(f'No checksum is recorded for {name}.')
    return name


def _download_archive(archive_name):
    """The bytes of the release archive, fetched anonymously.

    The release is public, and CI has no GitHub token to offer; the download
    redirects to the asset CDN, which `follow_redirects` takes it to.
    """
    url = f'{RELEASE_URL}/{archive_name}'
    log.info(f'_download_archive(): downloading {url}')
    with httpx.Client(timeout=DOWNLOAD_TIMEOUT, follow_redirects=True) as http:
        response = http.get(url)
    if response.status_code != 200:
        raise AssertionError(
            f'Downloading uts-proxy from {url} failed: {response.status_code} {response.text[:200]}')
    return response.content


def _verify_checksum(archive_name, archive):
    """Checks the downloaded archive against the sha256 the release publishes."""
    expected = ARCHIVE_CHECKSUMS[archive_name]
    actual = hashlib.sha256(archive).hexdigest()
    if actual != expected:
        raise AssertionError(
            f'Checksum mismatch for {archive_name}: expected {expected}, got {actual}.')


def _extract_binary(archive_name, archive, target):
    """Writes the `uts-proxy` entry of `archive` to `target`, executable.

    The archive also carries a README, a changelog and a licence, so the one
    entry wanted is pulled out by name rather than the whole thing being
    unpacked. It is written beside its destination and moved into place, so
    that an interrupted extraction cannot leave a truncated binary where a
    later run would find it and take it for a complete one.
    """
    partial = f'{target}.partial'
    with tarfile.open(fileobj=io.BytesIO(archive), mode='r:gz') as tar:
        for member in tar.getmembers():
            if not member.isfile() or os.path.basename(member.name) != BINARY_NAME:
                continue
            source = tar.extractfile(member)
            with open(partial, 'wb') as binary:
                shutil.copyfileobj(source, binary)
            os.chmod(partial, 0o755)
            os.replace(partial, target)
            return
    raise AssertionError(f'{archive_name} holds no {BINARY_NAME} entry.')
