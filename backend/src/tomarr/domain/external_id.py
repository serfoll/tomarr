from enum import StrEnum

from sqlalchemy import ForeignKey, Index, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from tomarr.domain.base import Base
from tomarr.domain.columns import string_enum


class Provider(StrEnum):
    MANGABAKA = "mangabaka"
    ANILIST = "anilist"
    MANGADEX = "mangadex"
    MANGAUPDATES = "mangaupdates"
    RAKUTEN = "rakuten"
    NDL = "ndl"
    OPENBD = "openbd"
    WEBTOON = "webtoon"


# Two tables, so each foreign key cascades without an either-or CHECK.
class SeriesExternalId(Base):
    __tablename__ = "series_external_id"
    __table_args__ = (
        UniqueConstraint("series_id", "provider"),
        Index("ix_series_external_id_provider_value", "provider", "value"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    series_id: Mapped[int] = mapped_column(ForeignKey("series.id", ondelete="CASCADE"))
    provider: Mapped[Provider] = mapped_column(string_enum(Provider))
    value: Mapped[str]


class VolumeExternalId(Base):
    __tablename__ = "volume_external_id"
    __table_args__ = (
        UniqueConstraint("volume_id", "provider"),
        Index("ix_volume_external_id_provider_value", "provider", "value"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    volume_id: Mapped[int] = mapped_column(ForeignKey("volume.id", ondelete="CASCADE"))
    provider: Mapped[Provider] = mapped_column(string_enum(Provider))
    value: Mapped[str]
