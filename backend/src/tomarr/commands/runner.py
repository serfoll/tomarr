import asyncio
import contextlib
import logging
from collections.abc import Awaitable, Callable

from tomarr.commands.registry import CommandRegistry
from tomarr.core.errors import DomainError, ErrorCode, RateLimited
from tomarr.domain.command import Command
from tomarr.services.commands import CommandService

logger = logging.getLogger(__name__)

# A worker that misses a wake signal still looks for work this often, so a lost signal costs
# seconds instead of leaving a due Command waiting forever.
MAX_WAIT = 30.0

type Wait = Callable[[asyncio.Event, float], Awaitable[None]]


async def wait_for_wake(event: asyncio.Event, delay: float) -> None:
    with contextlib.suppress(TimeoutError):
        async with asyncio.timeout(delay):
            await event.wait()


class CommandRunner:
    def __init__(
        self,
        service: CommandService,
        registry: CommandRegistry,
        *,
        workers: int = 2,
        clock: Callable[[], float],
        wait: Wait = wait_for_wake,
    ) -> None:
        self._service = service
        self._registry = registry
        self._clock = clock
        self._wait = wait
        self._events = [asyncio.Event() for _ in range(workers)]
        self._tasks: list[asyncio.Task[None]] = []

    def start(self) -> None:
        self._tasks = [
            asyncio.create_task(self._work(event), name=f"command-worker-{index}")
            for index, event in enumerate(self._events)
        ]

    def wake(self) -> None:
        for event in self._events:
            event.set()

    async def stop(self) -> None:
        for task in self._tasks:
            task.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)
        self._tasks = []

    async def _work(self, event: asyncio.Event) -> None:
        while True:
            # Cleared before the claim, so a wake that lands while claiming is not lost.
            event.clear()
            command = await self._service.claim_next()
            if command is None:
                await self._wait(event, await self._timeout())
            else:
                await self._run(command)

    async def _timeout(self) -> float:
        earliest = await self._service.earliest_not_before()
        if earliest is None:
            return MAX_WAIT
        return min(max(earliest - self._clock(), 0.0), MAX_WAIT)

    async def _run(self, command: Command) -> None:
        # CancelledError is not an Exception, so a Command cancelled at shutdown is not recorded
        # and stays running for the next start to requeue.
        try:
            handler = self._registry.get(command.type)
            result = await handler(command.payload)
        except RateLimited as error:
            logger.info(
                "Command rate limited",
                extra={"command_id": command.id, "waiting_on": error.service},
            )
            await self._service.reschedule(command.id, error.retry_after, error.service)
        except Exception as error:
            # Only the code is stored, since the exception text can hold a URL with a key in it.
            logger.exception("Command failed", extra={"command_id": command.id})
            code = error.code if isinstance(error, DomainError) else ErrorCode.INTERNAL_ERROR
            await self._service.fail(command.id, code)
        else:
            await self._service.complete(command.id, result)
