from decimal import Decimal

from sqlalchemy import ForeignKey, Index, Numeric, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from tomarr.domain.base import Base


class Chapter(Base):
    __tablename__ = "chapter"
    __table_args__ = (UniqueConstraint("series_id", "number"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    series_id: Mapped[int] = mapped_column(ForeignKey("series.id", ondelete="CASCADE"))
    number: Mapped[Decimal] = mapped_column(Numeric(8, 3))
    title: Mapped[str | None]


class Episode(Base):
    __tablename__ = "episode"

    id: Mapped[int] = mapped_column(primary_key=True)
    series_id: Mapped[int] = mapped_column(ForeignKey("series.id", ondelete="CASCADE"))
    # The platform's own numbering, which can restart each season.
    number: Mapped[int]
    season: Mapped[int | None]
    chapter_id: Mapped[int | None] = mapped_column(
        ForeignKey("chapter.id", ondelete="SET NULL"), index=True
    )


# A plain unique constraint treats every NULL season as different. coalesce counts "no season" as
# one value, so a real season 0 would collide with it. Platforms number seasons from 1.
# Alembic cannot reflect an expression index on SQLite, so a batch migration of `episode` drops
# this index and must recreate it by hand.
Index(
    "uq_episode_series_season_number",
    Episode.series_id,
    func.coalesce(Episode.season, 0),
    Episode.number,
    unique=True,
)
