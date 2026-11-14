from datetime import date
from decimal import Decimal

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from tests.helpers.library import Library
from tomarr.domain.chapter import Chapter, Episode
from tomarr.domain.series import Format, ReadingDirection, Series
from tomarr.domain.volume import Volume


async def _numbers(session: AsyncSession, column: type[Chapter] | type[Volume]) -> list[Decimal]:
    return list((await session.scalars(select(column.number).order_by(column.number))).all())


async def test_chapter_numbers_sort_as_numbers(session: AsyncSession, library: Library) -> None:
    session.add_all(
        Chapter(series_id=library.series.id, number=Decimal(n)) for n in ("11", "10.5", "10", "9")
    )
    session.add(Chapter(series_id=library.series.id, number=Decimal("10.1")))
    await session.commit()

    assert await _numbers(session, Chapter) == [
        Decimal(n) for n in ("1", "9", "10", "10.1", "10.5", "11")
    ]


async def test_chapter_zero_is_stored_and_found_by_equality(
    session: AsyncSession, library: Library
) -> None:
    session.add_all(
        [
            Chapter(series_id=library.series.id, number=Decimal("0")),
            Chapter(series_id=library.series.id, number=Decimal("10.1")),
        ]
    )
    await session.commit()

    zero = await session.scalar(select(Chapter).where(Chapter.number == Decimal("0")))
    found = await session.scalar(select(Chapter).where(Chapter.number == Decimal("10.1")))
    assert zero is not None
    assert found is not None
    assert found.number == Decimal("10.1")


async def test_volume_numbers_sort_as_numbers(session: AsyncSession, library: Library) -> None:
    session.add_all(
        Volume(edition_id=library.edition.id, number=Decimal(n)) for n in ("10", "2.5", "0")
    )
    await session.commit()

    assert await _numbers(session, Volume) == [Decimal(n) for n in ("0", "1", "2.5", "10")]


async def test_volume_keeps_its_metadata(session: AsyncSession, library: Library) -> None:
    volume = Volume(
        edition_id=library.edition.id,
        number=Decimal("2"),
        title="Vol. 2",
        release_date=date(2020, 7, 17),
        isbn="9784091234567",
        cover_url="https://example.test/2.jpg",
        synopsis="あらすじ",
    )
    session.add(volume)
    await session.commit()
    volume_id = volume.id
    session.expire_all()

    stored = await session.get(Volume, volume_id)
    assert stored is not None
    assert (stored.title, stored.release_date, stored.isbn) == (
        "Vol. 2",
        date(2020, 7, 17),
        "9784091234567",
    )
    assert (stored.cover_url, stored.synopsis) == ("https://example.test/2.jpg", "あらすじ")


async def test_series_stores_its_enums_as_plain_strings(session: AsyncSession) -> None:
    session.add(
        Series(title="Tower", format=Format.WEBTOON, reading_direction=ReadingDirection.VERTICAL)
    )
    await session.commit()

    stored = await session.scalar(select(Series))
    assert stored is not None
    assert (stored.format, stored.reading_direction) == (Format.WEBTOON, ReadingDirection.VERTICAL)
    raw = (await session.execute(text("SELECT format, reading_direction FROM series"))).one()
    assert tuple(raw) == ("webtoon", "vertical")
    assert [f.value for f in Format] == ["manga", "manhwa", "webtoon"]
    assert [d.value for d in ReadingDirection] == ["rtl", "ltr", "vertical"]
    table_sql = await session.scalar(text("SELECT sql FROM sqlite_master WHERE name = 'series'"))
    assert table_sql is not None
    assert "CHECK" not in table_sql


async def test_webtoon_series_works_without_volumes(session: AsyncSession) -> None:
    series = Series(
        title="Tower", format=Format.WEBTOON, reading_direction=ReadingDirection.VERTICAL
    )
    session.add(series)
    await session.flush()
    chapter = Chapter(series_id=series.id, number=Decimal("1"))
    session.add(chapter)
    await session.flush()
    session.add(Episode(series_id=series.id, number=1, season=None, chapter_id=chapter.id))
    await session.commit()

    assert await session.scalar(select(func.count()).select_from(Volume)) == 0
