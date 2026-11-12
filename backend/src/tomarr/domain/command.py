from enum import StrEnum

from sqlalchemy import JSON, Enum, Index
from sqlalchemy.orm import Mapped, mapped_column

from tomarr.domain.base import Base


class CommandStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


def _values(statuses: type[CommandStatus]) -> list[str]:
    return [status.value for status in statuses]


class Command(Base):
    __tablename__ = "command"

    id: Mapped[int] = mapped_column(primary_key=True)
    type: Mapped[str]
    payload: Mapped[dict[str, object]] = mapped_column(JSON)
    # A plain string column with no CHECK constraint, since SQLite cannot alter one in place.
    status: Mapped[CommandStatus] = mapped_column(
        Enum(CommandStatus, native_enum=False, create_constraint=False, values_callable=_values)
    )
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
