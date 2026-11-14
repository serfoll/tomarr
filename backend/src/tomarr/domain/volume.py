from datetime import date
from decimal import Decimal

from sqlalchemy import ForeignKey, Numeric, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from tomarr.domain.base import Base


class Volume(Base):
    __tablename__ = "volume"
    __table_args__ = (
        UniqueConstraint("edition_id", "number"),
        # The target of Mapping's composite foreign key, which keeps its Volume in its Edition.
        UniqueConstraint("id", "edition_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    edition_id: Mapped[int] = mapped_column(ForeignKey("edition.id", ondelete="CASCADE"))
    number: Mapped[Decimal] = mapped_column(Numeric(8, 3))
    title: Mapped[str | None]
    release_date: Mapped[date | None]
    isbn: Mapped[str | None]
    cover_url: Mapped[str | None]
    # The original text from the Provider, before any translation.
    synopsis: Mapped[str | None]
