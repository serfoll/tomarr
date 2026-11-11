import asyncio
import logging
from collections.abc import Sequence
from dataclasses import dataclass

from tomarr.commands.runner import Wait, wait_for_wake
from tomarr.services.commands import CommandService
from tomarr.services.settings import SettingKey, SettingsService

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Schedule:
    type: str
    setting_key: SettingKey[float]


class CommandScheduler:
    """Queues each scheduled Command type when its interval is due. All recurrence state lives in
    the command table, so a restart neither queues early nor forgets."""

    def __init__(
        self,
        service: CommandService,
        settings: SettingsService,
        schedules: Sequence[Schedule],
        *,
        wait: Wait = wait_for_wake,
        tick: float = 10.0,
    ) -> None:
        self._service = service
        self._settings = settings
        self._schedules = schedules
        self._wait = wait
        self._tick = tick
        self._stopping = asyncio.Event()
        self._task: asyncio.Task[None] | None = None

    def start(self) -> None:
        if self._task is not None:
            raise RuntimeError("The command scheduler is already running")
        self._stopping.clear()
        self._task = asyncio.create_task(self._run())

    async def stop(self) -> None:
        # Not cancelled, so a tick in progress finishes its database calls first.
        if self._task is None:
            return
        self._stopping.set()
        await asyncio.gather(self._task, return_exceptions=True)
        self._task = None

    async def _run(self) -> None:
        while not self._stopping.is_set():
            for schedule in self._schedules:
                try:
                    interval = await self._settings.get(schedule.setting_key)
                    await self._service.enqueue_if_due(schedule.type, interval)
                except Exception:
                    # The loop is the boundary: one bad tick must not end every schedule.
                    logger.exception("Scheduling failed", extra={"schedule_type": schedule.type})
            await self._wait(self._stopping, self._tick)
