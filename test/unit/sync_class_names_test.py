"""The generated synchronous classes a sync client hands out are named with a `Sync` suffix.

unasync generates `ably/pubsub/sync/` from the async tree and renames the classes in its
`rename_classes`. The handles reached from a sync client — its auth, channels, channel,
presence, annotations and push admin objects — and the paginated results are all renamed,
so that no sync handle shares a `__name__` with the async class it was generated from. Data
types, enums and exceptions keep their names in both trees.
"""

import pytest

import ably.pubsub.server.sync as server_sync
from ably.pubsub.http import annotations, auth, channel, push
from ably.pubsub.request import paginatedresult
from ably.pubsub.scripts.unasync import rename_classes
from ably.pubsub.sync.http import annotations as sync_annotations
from ably.pubsub.sync.http import auth as sync_auth
from ably.pubsub.sync.http import channel as sync_channel
from ably.pubsub.sync.http import push as sync_push
from ably.pubsub.sync.request import paginatedresult as sync_paginatedresult
from ably.pubsub.sync.types import presence as sync_presence
from ably.pubsub.types import presence

# (async module, sync module, async class name) for every handle class a sync client
# hands out, and the paginated results it returns.
HANDLES = [
    (auth, sync_auth, 'Auth'),
    (channel, sync_channel, 'Channels'),
    (channel, sync_channel, 'Channel'),
    (presence, sync_presence, 'Presence'),
    (annotations, sync_annotations, 'HttpAnnotations'),
    (push, sync_push, 'Push'),
    (push, sync_push, 'PushAdmin'),
    (push, sync_push, 'PushDeviceRegistrations'),
    (push, sync_push, 'PushChannelSubscriptions'),
    (paginatedresult, sync_paginatedresult, 'PaginatedResult'),
    (paginatedresult, sync_paginatedresult, 'HttpPaginatedResponse'),
]


@pytest.mark.parametrize('module,sync_module,name', HANDLES, ids=[h[2] for h in HANDLES])
def test_sync_handle_class_has_the_sync_suffix(module, sync_module, name):
    async_cls = getattr(module, name)
    sync_cls = getattr(sync_module, f'{name}Sync')
    assert async_cls.__name__ == name
    assert sync_cls.__name__ == f'{name}Sync'
    assert not hasattr(sync_module, name)
    assert name in rename_classes


@pytest.mark.parametrize('name', ['PresenceSync', 'HttpAnnotationsSync',
                                  'PushDeviceRegistrationsSync', 'PushChannelSubscriptionsSync'])
def test_the_four_classes_renamed_in_4_0(name):
    assert name[:-len('Sync')] in rename_classes


def test_sync_client_hands_out_the_sync_classes():
    client = server_sync.create_http_client(key='fake:key')
    ch = client.channels.get('names')
    assert type(client.auth) is sync_auth.AuthSync
    assert type(client.channels) is sync_channel.ChannelsSync
    assert type(ch) is sync_channel.ChannelSync
    assert type(ch.presence) is sync_presence.PresenceSync
    assert type(ch.annotations) is sync_annotations.HttpAnnotationsSync
    assert type(client.push) is sync_push.PushSync
    assert type(client.push.admin) is sync_push.PushAdminSync
    assert type(client.push.admin.device_registrations) is sync_push.PushDeviceRegistrationsSync
    assert type(client.push.admin.channel_subscriptions) is sync_push.PushChannelSubscriptionsSync
    client.close()


def test_sync_handles_do_not_share_a_name_with_their_async_class():
    client = server_sync.create_http_client(key='fake:key')
    ch = client.channels.get('names')
    handles = [client.auth, client.channels, ch, ch.presence, ch.annotations, client.push,
               client.push.admin, client.push.admin.device_registrations,
               client.push.admin.channel_subscriptions]
    for handle in handles:
        assert type(handle).__name__.endswith('Sync'), type(handle)
    client.close()


# Renaming a class changes the name its private attributes are mangled under. The renamed
# classes keep working because each reads its own attributes inside the class body; this
# exercises the four newly renamed ones through their private state.
def test_renamed_classes_read_their_own_private_attributes():
    client = server_sync.create_http_client(key='fake:key')
    ch = client.channels.get('names')
    assert ch.presence._PresenceSync__channel is ch
    assert not hasattr(ch.presence, '_Presence__channel')
    assert client.push.admin.device_registrations.ably is client
    assert client.push.admin.channel_subscriptions.ably is client
    client.close()
