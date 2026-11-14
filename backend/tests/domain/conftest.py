from collections.abc import AsyncIterator

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from tests.helpers.library import Library, new_series
from tomarr.core.database import Database
from tomarr.domain.chapter import Chapter
from tomarr.domain.edition import Edition
from tomarr.domain.volume import Volume


@pytest.fixture
async def session(database: Database) -> AsyncIterator[AsyncSession]:
    async with database.session_factory() as session:
        yield session


@pytest.fixture
async def library(session: AsyncSession) -> Library:
    series = new_series()
    session.add(series)
    await session.flush()
    edition = Edition(series_id=series.id, name="Japanese", language="ja", is_primary=True)
    chapter = Chapter(series_id=series.id, number=1, title=None)
    session.add_all([edition, chapter])
    await session.flush()
    volume = Volume(edition_id=edition.id, number=1)
    session.add(volume)
    await session.commit()
    return Library(series=series, edition=edition, volume=volume, chapter=chapter)
