import asyncio
from collections.abc import AsyncGenerator, AsyncIterator
from contextlib import asynccontextmanager


class _End:
    """Queued after the last item to end a subscriber's stream."""


_END = _End()


class Broadcaster[T]:
    """Fans each published item out to every subscriber, each behind its own bounded queue."""

    def __init__(self, max_queue: int = 100) -> None:
        self._max_queue = max_queue
        self._subscribers: set[asyncio.Queue[T | _End]] = set()
        self._closed = False

    @property
    def subscriber_count(self) -> int:
        return len(self._subscribers)

    @asynccontextmanager
    async def subscribe(self) -> AsyncGenerator[AsyncIterator[T]]:
        queue = asyncio.Queue[T | _End](self._max_queue)
        if self._closed:
            queue.put_nowait(_END)
        else:
            self._subscribers.add(queue)
        try:
            yield self._stream(queue)
        finally:
            self._subscribers.discard(queue)

    def publish(self, item: T) -> None:
        for queue in tuple(self._subscribers):
            try:
                queue.put_nowait(item)
            except asyncio.QueueFull:
                self._subscribers.discard(queue)
                _end(queue)

    def close(self) -> None:
        self._closed = True
        for queue in self._subscribers:
            _end(queue)
        self._subscribers.clear()

    async def _stream(self, queue: asyncio.Queue[T | _End]) -> AsyncIterator[T]:
        while True:
            item = await queue.get()
            if isinstance(item, _End):
                return
            yield item


def _end[T](queue: asyncio.Queue[T | _End]) -> None:
    # A full queue has no room for the sentinel, so its backlog is discarded to make room.
    while True:
        try:
            queue.put_nowait(_END)
            return
        except asyncio.QueueFull:
            queue.get_nowait()
