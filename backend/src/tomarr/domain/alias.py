from sqlalchemy import ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from tomarr.domain.base import Base
from tomarr.domain.columns import string_enum
from tomarr.domain.external_id import Provider


class Alias(Base):
    __tablename__ = "alias"
    __table_args__ = (UniqueConstraint("series_id", "name"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    series_id: Mapped[int] = mapped_column(ForeignKey("series.id", ondelete="CASCADE"))
    name: Mapped[str]
    # NULL means the user added it.
    provider: Mapped[Provider | None] = mapped_column(string_enum(Provider))
