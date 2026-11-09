from sqlalchemy import JSON
from sqlalchemy.orm import Mapped, mapped_column

from tomarr.domain.base import Base


class Setting(Base):
    __tablename__ = "setting"

    key: Mapped[str] = mapped_column(primary_key=True)
    # none_as_null is left off, so a None value is written as the JSON null, not SQL NULL.
    value: Mapped[object] = mapped_column(JSON, nullable=False)
