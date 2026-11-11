from sqlalchemy import JSON, LargeBinary
from sqlalchemy.orm import Mapped, mapped_column

from tomarr.domain.base import Base


class HttpCacheEntry(Base):
    __tablename__ = "http_cache"

    key: Mapped[str] = mapped_column(primary_key=True)
    adapter: Mapped[str]
    status_code: Mapped[int]
    # A list of [name, value] pairs, so a header that repeats keeps every value.
    headers: Mapped[list[list[str]]] = mapped_column(JSON)
    body: Mapped[bytes] = mapped_column(LargeBinary)
    # Epoch seconds. SQLite drops the timezone from DateTime(timezone=True).
    expires_at: Mapped[float] = mapped_column(index=True)
