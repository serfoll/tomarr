import logging
from collections.abc import Callable, Sequence

from sqlalchemy import Update, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from tomarr.core.errors import ErrorCode
from tomarr.domain.command import Command, CommandStatus

logger = logging.getLogger(__name__)

DEFAULT_RETRY_DELAY = 60.0
# The floor stops a service that sends Retry-After: 0 from being hit in a loop. The ceiling stops
# a broken or hostile header from parking a Command for years.
MIN_RETRY_DELAY = 5.0
MAX_RETRY_DELAY = 3600.0

ACTIVE = (CommandStatus.QUEUED, CommandStatus.RUNNING)


class CommandService:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        on_change: Callable[[Command], None],
        now: Callable[[], float],
    ) -> None:
        self._session_factory = session_factory
        self._on_change = on_change
        self._now = now

    async def enqueue(
        self,
        type: str,
        payload: dict[str, object] | None = None,
        priority: int = 0,
        not_before: float | None = None,
    ) -> Command:
        command = self._new(type, payload, priority, not_before)
        async with self._session_factory.begin() as session:
            session.add(command)
        self._changed(command)
        return command

    async def claim_next(self) -> Command | None:
        now = self._now()
        next_id = (
            select(Command.id)
            .where(
                Command.status == CommandStatus.QUEUED,
                or_(Command.not_before.is_(None), Command.not_before <= now),
            )
            .order_by(Command.priority.desc(), Command.queued_at, Command.id)
            .limit(1)
            .scalar_subquery()
        )
        # One statement, so two workers can never both take the row: SQLite runs writes one at a
        # time and the second one's subquery no longer sees it as queued.
        claimed = await self._update(
            update(Command)
            .where(Command.id == next_id)
            .values(status=CommandStatus.RUNNING, started_at=now, waiting_on=None)
        )
        return claimed[0] if claimed else None

    async def complete(self, id: int, result: dict[str, object] | None) -> Command:
        return await self._finish(id, CommandStatus.COMPLETED, result)

    async def fail(self, id: int, error: ErrorCode) -> Command:
        return await self._finish(id, CommandStatus.FAILED, {"error": error.value})

    async def reschedule(self, id: int, retry_after: float | None, service: str) -> Command:
        delay = DEFAULT_RETRY_DELAY if retry_after is None else retry_after
        delay = min(max(delay, MIN_RETRY_DELAY), MAX_RETRY_DELAY)
        [command] = await self._update(
            update(Command)
            .where(Command.id == id)
            .values(
                status=CommandStatus.QUEUED,
                not_before=self._now() + delay,
                started_at=None,
                waiting_on=service,
            )
        )
        return command

    async def requeue_interrupted(self) -> int:
        requeued = await self._update(
            update(Command)
            .where(Command.status == CommandStatus.RUNNING)
            .values(status=CommandStatus.QUEUED, started_at=None)
        )
        return len(requeued)

    async def active(self) -> list[Command]:
        async with self._session_factory() as session:
            commands = await session.scalars(
                select(Command).where(Command.status.in_(ACTIVE)).order_by(Command.id)
            )
            return list(commands)

    async def earliest_not_before(self) -> float | None:
        async with self._session_factory() as session:
            return await session.scalar(
                select(func.min(Command.not_before)).where(
                    Command.status == CommandStatus.QUEUED, Command.not_before > self._now()
                )
            )

    async def enqueue_if_due(self, type: str, interval: float) -> Command | None:
        if interval <= 0:
            return None
        async with self._session_factory.begin() as session:
            busy = await session.scalar(
                select(func.count())
                .select_from(Command)
                .where(Command.type == type, Command.status.in_(ACTIVE))
            )
            last_queued_at = await session.scalar(
                select(func.max(Command.queued_at)).where(Command.type == type)
            )
            if busy or (last_queued_at is not None and self._now() - last_queued_at < interval):
                return None
            command = self._new(type, None, 0, None)
            session.add(command)
        self._changed(command)
        return command

    def _new(
        self, type: str, payload: dict[str, object] | None, priority: int, not_before: float | None
    ) -> Command:
        return Command(
            type=type,
            payload={} if payload is None else payload,
            status=CommandStatus.QUEUED,
            priority=priority,
            not_before=not_before,
            queued_at=self._now(),
        )

    async def _finish(
        self, id: int, status: CommandStatus, result: dict[str, object] | None
    ) -> Command:
        [command] = await self._update(
            update(Command)
            .where(Command.id == id)
            .values(status=status, result=result, ended_at=self._now())
        )
        return command

    async def _update(self, statement: Update) -> Sequence[Command]:
        async with self._session_factory.begin() as session:
            result = await session.scalars(
                statement.returning(Command), execution_options={"synchronize_session": False}
            )
            commands = result.all()
        for command in commands:
            self._changed(command)
        return commands

    def _changed(self, command: Command) -> None:
        # Runs after the commit, so a listener never sees a state the database does not hold, and
        # a failing listener can neither undo the change nor hide it from the caller.
        try:
            self._on_change(command)
        except Exception:
            logger.exception("Command change listener failed", extra={"command_id": command.id})
