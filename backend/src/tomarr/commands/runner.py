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
ERROR_BACKOFF = 5.0

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
        self._handlers: set[asyncio.Future[dict[str, object] | None]] = set()
        self._stopping = False

    def start(self) -> None:
        if self._tasks:
            raise RuntimeError("The command runner is already running")
        self._stopping = False
        self._tasks = [
            asyncio.create_task(self._work(event), name=f"command-worker-{index}")
            for index, event in enumerate(self._events)
        ]

    def wake(self) -> None:
        for event in self._events:
            event.set()

    async def stop(self) -> None:
        # Only handlers are cancelled. Cancelling a worker inside a service call makes SQLAlchemy
        # force-close the connection, and the next one can then wait out SQLite's busy timeout.
        self._stopping = True
        self.wake()
        for handler in self._handlers:
            handler.cancel()
        for outcome in await asyncio.gather(*self._tasks, return_exceptions=True):
            if isinstance(outcome, Exception):
                logger.error("Command worker stopped with an error", exc_info=outcome)
        self._tasks = []

    async def _work(self, event: asyncio.Event) -> None:
        while not self._stopping:
            # Cleared before the claim, so a wake that lands while claiming is not lost.
            event.clear()
            command: Command | None = None
            try:
                command = await self._service.claim_next()
                if command is not None:
                    await self._run(command)
                    continue
                delay = await self._timeout()
            except Exception:
                # A failed claim or record, such as a locked database, must not cost the pool a
                # worker. The backoff keeps a database that stays broken from being hammered.
                command_id = None if command is None else command.id
                logger.exception("Command worker failed", extra={"command_id": command_id})
                if command is not None:
                    await self._fail_quietly(command.id)
                delay = ERROR_BACKOFF
            await self._wait(event, delay)

    async def _timeout(self) -> float:
        # The service reads its clock again here, so a Command that became due just after the
        # claim is skipped and waits for the next wake or MAX_WAIT at most.
        earliest = await self._service.earliest_not_before()
        if earliest is None:
            return MAX_WAIT
        return min(max(earliest - self._clock(), 0.0), MAX_WAIT)

    async def _run(self, command: Command) -> None:
        try:
            handler = self._registry.get(command.type)
            task = asyncio.ensure_future(handler(command.payload))
            self._handlers.add(task)
            if self._stopping:
                task.cancel()
            try:
                await asyncio.wait([task])
            finally:
                self._handlers.discard(task)
            if task.cancelled() and self._stopping:
                # Not recorded, so the row stays running for the next start to requeue.
                return
            # Inside the try so a result that cannot be stored fails the Command instead of
            # leaving it running.
            await self._service.complete(command.id, _result(task))
        except RateLimited as error:
            logger.info(
                "Command rate limited",
                extra={"command_id": command.id, "waiting_on": error.service},
            )
            await self._service.reschedule(command.id, error.retry_after, error.service)
        except Exception as error:
            # Only the code is stored, since the exception text can hold a URL with a key in it.
            logger.exception("Command failed", extra={"command_id": command.id})
            await self._service.fail(command.id, _error_code(error))

    async def _fail_quietly(self, id: int) -> None:
        # The last chance to end a claimed Command whose outcome could not be stored. Left
        # running, it would look busy until the next start and block its schedule.
        try:
            await self._service.fail(id, ErrorCode.INTERNAL_ERROR)
        except Exception:
            logger.exception("Command could not be failed", extra={"command_id": id})


def _result[T](task: asyncio.Future[T]) -> T:
    """The handler's result, or its exception. A handler that cancelled itself or raised a
    BaseException gets a RuntimeError instead, so it fails its Command and not the worker."""
    if task.cancelled():
        raise RuntimeError("The command handler was cancelled")
    error = task.exception()
    if error is not None and not isinstance(error, Exception):
        raise RuntimeError("The command handler raised a BaseException") from error
    return task.result()


def _error_code(error: Exception) -> ErrorCode:
    code = getattr(error, "code", None) if isinstance(error, DomainError) else None
    return code if isinstance(code, ErrorCode) else ErrorCode.INTERNAL_ERROR
