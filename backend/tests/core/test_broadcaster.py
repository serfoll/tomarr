import asyncio
from collections.abc import AsyncIterator

from tomarr.core.broadcaster import Broadcaster


async def take(stream: AsyncIterator[int], count: int) -> list[int]:
    async with asyncio.timeout(1):
        return [await anext(stream) for _ in range(count)]


async def drain(stream: AsyncIterator[int]) -> list[int]:
    async with asyncio.timeout(1):
        return [item async for item in stream]


async def test_every_subscriber_gets_every_item_in_order() -> None:
    broadcaster = Broadcaster[int]()
    async with broadcaster.subscribe() as first, broadcaster.subscribe() as second:
        for item in (1, 2, 3):
            broadcaster.publish(item)

        assert await take(first, 3) == [1, 2, 3]
        assert await take(second, 3) == [1, 2, 3]


async def test_subscriber_that_exits_stops_receiving() -> None:
    broadcaster = Broadcaster[int](max_queue=1)
    async with broadcaster.subscribe() as stay:
        async with broadcaster.subscribe():
            assert broadcaster.subscriber_count == 2

        assert broadcaster.subscriber_count == 1
        broadcaster.publish(1)
        assert await take(stay, 1) == [1]


async def test_lagging_subscriber_is_dropped_and_its_stream_ends() -> None:
    broadcaster = Broadcaster[int](max_queue=2)
    async with broadcaster.subscribe() as slow, broadcaster.subscribe() as fast:
        broadcaster.publish(1)
        broadcaster.publish(2)
        assert await take(fast, 2) == [1, 2]

        broadcaster.publish(3)

        assert broadcaster.subscriber_count == 1
        assert await take(fast, 1) == [3]
        assert 3 not in await drain(slow)


async def test_publish_with_no_subscribers_does_nothing() -> None:
    broadcaster = Broadcaster[int]()

    broadcaster.publish(1)

    assert broadcaster.subscriber_count == 0


async def test_close_ends_every_stream() -> None:
    broadcaster = Broadcaster[int]()
    async with broadcaster.subscribe() as first, broadcaster.subscribe() as second:
        broadcaster.publish(1)
        broadcaster.close()

        assert await drain(first) == [1]
        assert await drain(second) == [1]


async def test_subscribe_after_close_ends_at_once() -> None:
    broadcaster = Broadcaster[int]()
    broadcaster.close()

    async with broadcaster.subscribe() as stream:
        assert await drain(stream) == []

    broadcaster.publish(1)
