import asyncio
import math
from collections import deque
from collections.abc import Awaitable, Callable


class RateLimiter:
    """Sliding window: at most `requests` calls start in any `interval` seconds."""

    def __init__(
        self,
        requests: int,
        interval: float,
        clock: Callable[[], float],
        sleep: Callable[[float], Awaitable[None]],
    ) -> None:
        if requests < 1:
            raise ValueError("requests must be at least 1")
        if not math.isfinite(interval):
            raise ValueError("interval must be finite")
        if interval <= 0:
            raise ValueError("interval must be positive")
        self.requests = requests
        self.interval = interval
        self._clock = clock
        self._sleep = sleep
        self._starts: deque[float] = deque()
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        # Sleeping while holding the lock keeps waiters in arrival order. A slot is recorded only
        # once the wait is over, so a waiter cancelled mid-sleep takes none.
        async with self._lock:
            while self._full():
                await self._sleep(self._starts[0] + self.interval - self._clock())
            self._starts.append(self._clock())

    def _full(self) -> bool:
        cutoff = self._clock() - self.interval
        while self._starts and self._starts[0] <= cutoff:
            self._starts.popleft()
        return len(self._starts) >= self.requests
