from decimal import Decimal

import pytest
from sqlalchemy import delete, func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from tests.helpers.library import Library
from tomarr.domain.chapter import Chapter
from tomarr.domain.edition import Edition
from tomarr.domain.mapping import Confidence, Mapping
from tomarr.domain.provenance import Provenance
from tomarr.domain.volume import Volume


def _mapping(library: Library, **overrides: object) -> Mapping:
    fields: dict[str, object] = {
        "edition_id": library.edition.id,
        "volume_id": library.volume.id,
        "chapter_id": library.chapter.id,
        "provenance": Provenance.USER,
        "confidence": None,
        "locked": False,
    }
    return Mapping(**(fields | overrides))


async def test_mapping_stores_provenance_confidence_and_lock(
    session: AsyncSession, library: Library
) -> None:
    session.add(_mapping(library, provenance=Provenance.LLM_EXTRACTION, confidence=Confidence.LOW))
    await session.commit()
    session.expire_all()

    stored = await session.scalar(select(Mapping))
    assert stored is not None
    assert (stored.provenance, stored.confidence, stored.locked) == (
        Provenance.LLM_EXTRACTION,
        Confidence.LOW,
        False,
    )
    raw = (await session.execute(text("SELECT provenance, confidence FROM mapping"))).one()
    assert tuple(raw) == ("llm_extraction", "low")
    assert [c.value for c in Confidence] == ["high", "medium", "low"]


async def test_a_user_mapping_has_no_confidence_and_can_be_locked(
    session: AsyncSession, library: Library
) -> None:
    session.add(_mapping(library, locked=True))
    await session.commit()
    session.expire_all()

    stored = await session.scalar(select(Mapping))
    assert stored is not None
    assert (stored.confidence, stored.locked) == (None, True)


async def test_a_chapter_sits_in_one_volume_per_edition(
    session: AsyncSession, library: Library
) -> None:
    second = Volume(edition_id=library.edition.id, number=Decimal("2"))
    session.add_all([second, _mapping(library)])
    await session.flush()
    session.add(_mapping(library, volume_id=second.id))

    with pytest.raises(IntegrityError, match="UNIQUE constraint failed"):
        await session.commit()


async def test_a_chapter_can_sit_in_a_volume_of_each_edition(
    session: AsyncSession, library: Library
) -> None:
    omnibus = Edition(series_id=library.series.id, name="Omnibus", language="en", is_primary=False)
    session.add(omnibus)
    await session.flush()
    omnibus_volume = Volume(edition_id=omnibus.id, number=Decimal("1"))
    session.add(omnibus_volume)
    await session.flush()
    session.add_all(
        [_mapping(library), _mapping(library, edition_id=omnibus.id, volume_id=omnibus_volume.id)]
    )

    await session.commit()


async def test_a_volume_holds_many_chapters(session: AsyncSession, library: Library) -> None:
    second = Chapter(series_id=library.series.id, number=Decimal("2"))
    session.add(second)
    await session.flush()
    session.add_all([_mapping(library), _mapping(library, chapter_id=second.id)])

    await session.commit()


async def test_a_volume_from_another_edition_is_refused(
    session: AsyncSession, library: Library
) -> None:
    other = Edition(series_id=library.series.id, name="English", language="en", is_primary=False)
    session.add(other)
    await session.flush()
    session.add(_mapping(library, edition_id=other.id))

    with pytest.raises(IntegrityError, match="FOREIGN KEY constraint failed"):
        await session.commit()


@pytest.mark.parametrize("parent", [Chapter, Volume, Edition])
async def test_deleting_a_parent_removes_its_mappings(
    session: AsyncSession, library: Library, parent: type[Chapter] | type[Volume] | type[Edition]
) -> None:
    session.add(_mapping(library))
    await session.commit()

    await session.execute(delete(parent))
    await session.commit()

    assert await session.scalar(select(func.count()).select_from(Mapping)) == 0
