"""Derived from uts/rest/integration/pagination.md in ably/specification.

Spec points: TG1, TG2, TG3, TG4, TG5
"""

from ably.http.paginatedresult import PaginatedResult
from ably.types.message import Message
from test.uts.helpers.client import sandbox_rest_client, wall_clock_poll_until
from test.uts.helpers.sandbox import random_id

# The specifications publish their fixture messages one at a time. A round trip
# each turns the setup for the 25-message case into the slowest part of the
# tier, and the messages are the same set either way, so they go up in one
# request here.
PUBLISH_BATCH = 25

# `poll_until(interval: 500ms, timeout: 15s)`, as the specifications write it.
# History is not immediately consistent, so every test waits for the messages
# it published to be visible before it paginates over them.
HISTORY_TIMEOUT = 20.0


async def publish_events(channel, count):
    """The specifications' `FOR i IN 1..count: publish("event-" + i, str(i))`."""
    for start in range(1, count + 1, PUBLISH_BATCH):
        batch = range(start, min(start + PUBLISH_BATCH, count + 1))
        await channel.publish([Message(f'event-{i}', str(i)) for i in batch])


async def history_of_size(channel, count, timeout=HISTORY_TIMEOUT):
    """Waits until `count` messages are visible in history, as the specifications' `poll_until`.

    A `PaginatedResult` is truthy whether or not it holds anything, so the
    condition answers `None` until the page is the size the test needs.
    """
    async def full_history():
        page = await channel.history()
        return page if len(page.items) == count else None

    return await wall_clock_poll_until(
        full_history, timeout=timeout,
        description=f'the {count} published messages to reach history')


# UTS: rest/integration/TG1/items-and-navigation-0
async def test_tg1_items_and_navigation(sandbox):
    client = sandbox_rest_client(sandbox.key(0).key_str)
    channel = client.channels.get(f'pagination-basic-{random_id()}')

    await publish_events(channel, 15)
    await history_of_size(channel, 15)

    # Request with small limit to force pagination
    page1 = await channel.history(limit=5)

    # TG1 - items contains array of results
    assert isinstance(page1, PaginatedResult)
    assert isinstance(page1.items, list)
    assert len(page1.items) == 5

    # TG2 - hasNext/isLast indicate more pages. Both are methods in this SDK, so
    # the specification's `page1.hasNext() == true` is `page1.has_next()`; a bare
    # `page1.has_next` would be a bound method and pass whatever the answer.
    assert page1.has_next() is True
    assert page1.is_last() is False


# UTS: rest/integration/TG3/next-retrieves-page-0
async def test_tg3_next_retrieves_page(sandbox):
    client = sandbox_rest_client(sandbox.key(0).key_str)
    channel = client.channels.get(f'pagination-next-{random_id()}')

    await publish_events(channel, 12)
    await history_of_size(channel, 12)

    page1 = await channel.history(limit=5)
    page2 = await page1.next()
    page3 = await page2.next()

    assert len(page1.items) == 5
    assert len(page2.items) == 5
    assert len(page3.items) == 2  # Remaining messages

    # Verify no duplicate messages across pages
    all_ids = []
    for page in (page1, page2, page3):
        for item in page.items:
            assert item.id not in all_ids
            all_ids.append(item.id)

    assert len(all_ids) == 12


# UTS: rest/integration/TG4/first-retrieves-page-0
async def test_tg4_first_retrieves_page(sandbox):
    client = sandbox_rest_client(sandbox.key(0).key_str)
    channel = client.channels.get(f'pagination-first-{random_id()}')

    await publish_events(channel, 10)
    await history_of_size(channel, 10)

    page1 = await channel.history(limit=3)
    page2 = await page1.next()
    first_page = await page2.first()

    # first_page should have same items as page1
    assert first_page is not None
    assert len(first_page.items) == len(page1.items)

    for expected, actual in zip(page1.items, first_page.items):
        assert actual.id == expected.id


# UTS: rest/integration/TG5/iterate-all-pages-0
async def test_tg5_iterate_all_pages(sandbox):
    client = sandbox_rest_client(sandbox.key(0).key_str)
    channel = client.channels.get(f'pagination-iterate-{random_id()}')

    message_count = 25
    await publish_events(channel, message_count)
    await history_of_size(channel, message_count, timeout=30.0)

    all_messages = []
    page = await channel.history(limit=7)

    while True:
        all_messages.extend(page.items)

        if not page.has_next():
            break

        page = await page.next()

    assert len(all_messages) == message_count

    # Verify all messages retrieved
    event_names = [message.name for message in all_messages]
    for i in range(1, message_count + 1):
        assert f'event-{i}' in event_names


# UTS: rest/integration/TG3/next-last-page-null-1
async def test_tg3_next_last_page_null(sandbox):
    client = sandbox_rest_client(sandbox.key(0).key_str)
    channel = client.channels.get(f'pagination-lastnext-{random_id()}')

    await publish_events(channel, 3)
    await history_of_size(channel, 3, timeout=15.0)

    page = await channel.history(limit=10)  # Larger than message count

    assert len(page.items) == 3
    assert page.has_next() is False
    assert page.is_last() is True

    # `next()` answers None when the response carried no `next` link rel, which
    # is the specification's "returns null on the last page".
    next_page = await page.next()
    assert next_page is None
