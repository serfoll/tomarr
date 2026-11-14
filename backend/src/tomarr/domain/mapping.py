from enum import StrEnum

from sqlalchemy import ForeignKey, ForeignKeyConstraint, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from tomarr.domain.base import Base
from tomarr.domain.columns import string_enum
from tomarr.domain.provenance import Provenance


class Confidence(StrEnum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class Mapping(Base):
    """One Chapter inside one Volume, for one Edition."""

    __tablename__ = "mapping"
    __table_args__ = (
        UniqueConstraint("edition_id", "chapter_id"),
        ForeignKeyConstraint(
            ["volume_id", "edition_id"], ["volume.id", "volume.edition_id"], ondelete="CASCADE"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    edition_id: Mapped[int] = mapped_column(ForeignKey("edition.id", ondelete="CASCADE"))
    volume_id: Mapped[int] = mapped_column(index=True)
    chapter_id: Mapped[int] = mapped_column(
        ForeignKey("chapter.id", ondelete="CASCADE"), index=True
    )
    provenance: Mapped[Provenance] = mapped_column(string_enum(Provenance))
    # NULL for a user's Mapping, since a hand-made one is not a guess.
    confidence: Mapped[Confidence | None] = mapped_column(string_enum(Confidence))
    locked: Mapped[bool]
