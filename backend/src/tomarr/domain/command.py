from enum import StrEnum

from sqlalchemy import JSON, Index
from sqlalchemy.orm import Mapped, mapped_column

from tomarr.domain.base import Base
from tomarr.domain.columns import string_enum


class CommandStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class Command(Base):
    __tablename__ = "command"

    id: Mapped[int] = mapped_column(primary_key=True)
    type: Mapped[str]
    payload: Mapped[dict[str, object]] = mapped_column(JSON)
    status: Mapped[CommandStatus] = mapped_column(string_enum(CommandStatus))
    priority: Mapped[int]
    # Epoch seconds, like http_cache.expires_at.
    not_before: Mapped[float | None]
    queued_at: Mapped[float]
    started_at: Mapped[float | None]
    ended_at: Mapped[float | None]
    result: Mapped[dict[str, object] | None] = mapped_column(JSON(none_as_null=True))
    # The service a rate-limited Command waits on, cleared when it next starts.
    waiting_on: Mapped[str | None]


# The claim query filters on status and sorts by priority, highest first, then age. Declared after
# the class so priority can carry its sort order, which lets SQLite read rows in claim order.
Index("ix_command_claim", Command.status, Command.priority.desc(), Command.queued_at)
