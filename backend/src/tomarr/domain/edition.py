from sqlalchemy import ForeignKey, Index, text
from sqlalchemy.orm import Mapped, mapped_column

from tomarr.domain.base import Base


class Edition(Base):
    __tablename__ = "edition"

    id: Mapped[int] = mapped_column(primary_key=True)
    series_id: Mapped[int] = mapped_column(ForeignKey("series.id", ondelete="CASCADE"))
    name: Mapped[str]
    language: Mapped[str]
    is_primary: Mapped[bool]


# At most one primary Edition per Series. The index is partial, so any number of others are fine.
Index(
    "uq_edition_primary_per_series",
    Edition.series_id,
    unique=True,
    sqlite_where=text("is_primary"),
)
