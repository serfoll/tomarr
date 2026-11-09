from collections.abc import AsyncIterator
from pathlib import Path

import pytest

from tomarr.core.database import Database, create_database
from tomarr.core.migrations import upgrade_to_head


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    path = tmp_path / "tomarr.db"
    upgrade_to_head(path)
    return path


@pytest.fixture
async def database(db_path: Path) -> AsyncIterator[Database]:
    db = create_database(db_path)
    yield db
    await db.dispose()
