import asyncio


class FakeClock:
    """A monotonic clock whose sleep advances it, so tests never really wait. Sleeps overlap like
    real ones: two sleepers started together wake together."""

    def __init__(self) -> None:
        self.now = 0.0
        self.gate: asyncio.Event | None = None
        self.sleeping = 0
        self.sleep_started = asyncio.Event()

    def __call__(self) -> float:
        return self.now

    async def sleep(self, delay: float) -> None:
        wake_at = self.now + delay
        self.sleeping += 1
        self.sleep_started.set()
        try:
            if self.gate is not None:
                await self.gate.wait()
            else:
                await asyncio.sleep(0)
        finally:
            self.sleeping -= 1
        self.now = max(self.now, wake_at)
