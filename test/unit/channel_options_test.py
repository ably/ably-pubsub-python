from ably.pubsub.server import (
    ChannelMode,
    ChannelOptions,
    create_http_client,
    create_realtime_client,
    generate_random_key,
    get_default_params,
)
from ably.pubsub.types.message import Message


def cipher_options(**kwargs):
    return ChannelOptions(cipher=get_default_params({'key': generate_random_key()}), **kwargs)


def is_encrypted(channel):
    message = Message('name', 'data')
    if channel.cipher:
        message.encrypt(channel.cipher)
    return 'cipher' in message.as_dict().get('encoding', '')


async def test_http_set_options_without_a_cipher_turns_encryption_off():
    ably = create_http_client(token='foo')
    channel = ably.channels.get('test', cipher_options())
    assert is_encrypted(channel)

    await channel.set_options(ChannelOptions())

    assert channel.options.cipher is None
    assert channel.cipher is None
    assert not is_encrypted(channel)
    await ably.close()


async def test_http_get_with_options_replaces_the_cipher():
    ably = create_http_client(token='foo')
    channel = ably.channels.get('test', cipher_options())

    assert ably.channels.get('test', ChannelOptions()) is channel

    assert channel.cipher is None
    await ably.close()


async def test_http_get_without_options_keeps_the_cipher():
    ably = create_http_client(token='foo')
    options = cipher_options()
    channel = ably.channels.get('test', options)

    assert ably.channels.get('test') is channel

    assert channel.options is options
    assert is_encrypted(channel)
    await ably.close()


async def test_realtime_set_options_without_a_cipher_turns_encryption_off():
    ably = create_realtime_client(key='fake.key:secret', auto_connect=False)
    channel = ably.channels.get('test', cipher_options(params={'rewind': '1'}))

    await channel.set_options(ChannelOptions(params={'rewind': '1'}))

    assert channel.options.params == {'rewind': '1'}
    assert channel.options.cipher is None
    assert not is_encrypted(channel)
    await ably.close()


async def test_realtime_set_options_replaces_rather_than_merges():
    ably = create_realtime_client(key='fake.key:secret', auto_connect=False)
    channel = ably.channels.get('test', ChannelOptions(params={'rewind': '1'}, modes=[ChannelMode.SUBSCRIBE]))

    await channel.set_options(ChannelOptions(params={'delta': 'vcdiff'}))

    assert channel.options.params == {'delta': 'vcdiff'}
    assert channel.options.modes is None
    await ably.close()


async def test_realtime_get_with_options_replaces_the_cipher():
    ably = create_realtime_client(key='fake.key:secret', auto_connect=False)
    channel = ably.channels.get('test', cipher_options())

    assert ably.channels.get('test', ChannelOptions()) is channel

    assert not is_encrypted(channel)
    await ably.close()
