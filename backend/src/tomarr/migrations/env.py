from alembic import context
from sqlalchemy import URL, create_engine
from sqlalchemy.pool import NullPool

# Imported for their side effect: each model registers itself on Base.metadata.
import tomarr.domain.alias  # pyright: ignore[reportUnusedImport]
import tomarr.domain.chapter  # pyright: ignore[reportUnusedImport]
import tomarr.domain.command  # pyright: ignore[reportUnusedImport]
import tomarr.domain.edition  # pyright: ignore[reportUnusedImport]
import tomarr.domain.external_id  # pyright: ignore[reportUnusedImport]
import tomarr.domain.http_cache  # pyright: ignore[reportUnusedImport]
import tomarr.domain.mapping  # pyright: ignore[reportUnusedImport]
import tomarr.domain.series  # pyright: ignore[reportUnusedImport]
import tomarr.domain.setting  # pyright: ignore[reportUnusedImport]
import tomarr.domain.volume  # noqa: F401  # pyright: ignore[reportUnusedImport]
from tomarr.domain.base import Base

# logging.config.fileConfig is not called: it would replace the handlers from core/logging.py.
config = context.config


def _database_url() -> URL | str:
    url: URL | str | None = config.attributes.get("url")
    if url is None:
        url = config.get_main_option("sqlalchemy.url")
    if url is None:
        url = context.get_x_argument(as_dictionary=True).get("url")
    if url is None:
        raise RuntimeError(
            "No database URL. From the command line, pass -x url=sqlite:///path/to/tomarr.db"
        )
    return url


def run_migrations() -> None:
    # A plain sqlite3 engine: Alembic is synchronous, the async driver is the app's concern.
    engine = create_engine(_database_url(), poolclass=NullPool)
    with engine.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=Base.metadata,
            render_as_batch=True,
        )
        with context.begin_transaction():
            context.run_migrations()
    engine.dispose()


run_migrations()
