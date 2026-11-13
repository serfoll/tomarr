from decimal import Decimal

import pytest
from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from tests.helpers.library import Library, new_series
from tomarr.domain.alias import Alias
from tomarr.domain.chapter import Chapter, Episode
from tomarr.domain.edition import Edition
from tomarr.domain.external_id import Provider, SeriesExternalId, VolumeExternalId
from tomarr.domain.mapping import Mapping
from tomarr.domain.provenance import Provenance
from tomarr.domain.series import Series
from tomarr.domain.volume import Volume


def _duplicates(library: Library) -> dict[str, list[object]]:
    series_id, edition_id, volume_id = library.series.id, library.edition.id, library.volume.id
    return {
        "chapter": [
            Chapter(series_id=series_id, number=Decimal("5")),
            Chapter(series_id=series_id, number=Decimal("5")),
        ],
        "volume": [
            Volume(edition_id=edition_id, number=Decimal("1")),
        ],
        "alias": [
            Alias(series_id=series_id, name="Sousou no Frieren", provider=None),
            Alias(series_id=series_id, name="Sousou no Frieren", provider=Provider.ANILIST),
        ],
        "series external id": [
            SeriesExternalId(series_id=series_id, provider=Provider.ANILIST, value="1"),
            SeriesExternalId(series_id=series_id, provider=Provider.ANILIST, value="2"),
        ],
        "volume external id": [
            VolumeExternalId(volume_id=volume_id, provider=Provider.RAKUTEN, value="1"),
            VolumeExternalId(volume_id=volume_id, provider=Provider.RAKUTEN, value="2"),
        ],
        "episode with a season": [
            Episode(series_id=series_id, number=3, season=1, chapter_id=None),
            Episode(series_id=series_id, number=3, season=1, chapter_id=None),
        ],
        "episode without a season": [
            Episode(series_id=series_id, number=3, season=None, chapter_id=None),
            Episode(series_id=series_id, number=3, season=None, chapter_id=None),
        ],
        "episode in season 0 and without a season": [
            Episode(series_id=series_id, number=3, season=0, chapter_id=None),
            Episode(series_id=series_id, number=3, season=None, chapter_id=None),
        ],
    }


@pytest.mark.parametrize(
    "name",
    [
        "chapter",
        "volume",
        "alias",
        "series external id",
        "volume external id",
        "episode with a season",
        "episode without a season",
        "episode in season 0 and without a season",
    ],
)
async def test_unique_rows_are_refused(session: AsyncSession, library: Library, name: str) -> None:
    session.add_all(_duplicates(library)[name])

    with pytest.raises(IntegrityError, match="UNIQUE constraint failed"):
        await session.commit()


async def test_same_number_in_another_scope_is_allowed(
    session: AsyncSession, library: Library
) -> None:
    other = new_series("Other")
    session.add(other)
    await session.flush()
    other_edition = Edition(series_id=other.id, name="Japanese", language="ja", is_primary=True)
    session.add_all(
        [
            Chapter(series_id=other.id, number=Decimal("1")),
            other_edition,
            Edition(series_id=library.series.id, name="English", language="en", is_primary=False),
            Episode(series_id=library.series.id, number=3, season=1, chapter_id=None),
            Episode(series_id=library.series.id, number=3, season=2, chapter_id=None),
            Episode(series_id=library.series.id, number=3, season=None, chapter_id=None),
            Alias(series_id=library.series.id, name="Frieren", provider=None),
            Alias(series_id=other.id, name="Frieren", provider=None),
        ]
    )
    await session.flush()
    session.add(Volume(edition_id=other_edition.id, number=Decimal("1")))
    await session.commit()


async def test_a_second_primary_edition_is_refused(session: AsyncSession, library: Library) -> None:
    session.add(
        Edition(series_id=library.series.id, name="English", language="en", is_primary=True)
    )

    with pytest.raises(IntegrityError, match="UNIQUE constraint failed"):
        await session.commit()


async def test_any_number_of_other_editions_is_fine(
    session: AsyncSession, library: Library
) -> None:
    other = new_series("Other")
    session.add(other)
    await session.flush()
    session.add_all(
        [
            Edition(series_id=library.series.id, name=f"Extra {n}", language="en", is_primary=False)
            for n in range(3)
        ]
    )
    session.add(Edition(series_id=other.id, name="Japanese", language="ja", is_primary=True))
    await session.commit()


async def test_deleting_a_series_removes_everything_under_it(
    session: AsyncSession, library: Library
) -> None:
    series_id = library.series.id
    session.add_all(
        [
            Alias(series_id=series_id, name="Alias", provider=None),
            SeriesExternalId(series_id=series_id, provider=Provider.MANGADEX, value="x"),
            VolumeExternalId(volume_id=library.volume.id, provider=Provider.NDL, value="y"),
            Episode(series_id=series_id, number=1, season=None, chapter_id=library.chapter.id),
            Mapping(
                edition_id=library.edition.id,
                volume_id=library.volume.id,
                chapter_id=library.chapter.id,
                provenance=Provenance.USER,
                confidence=None,
                locked=False,
            ),
        ]
    )
    await session.commit()

    await session.execute(delete(Series))
    await session.commit()

    for model in (
        Edition,
        Volume,
        Chapter,
        Episode,
        Mapping,
        Alias,
        SeriesExternalId,
        VolumeExternalId,
    ):
        assert await session.scalar(select(func.count()).select_from(model)) == 0, model


async def test_deleting_a_chapter_clears_the_episode_link(
    session: AsyncSession, library: Library
) -> None:
    episode = Episode(
        series_id=library.series.id, number=1, season=None, chapter_id=library.chapter.id
    )
    session.add(episode)
    await session.commit()
    episode_id = episode.id

    await session.execute(delete(Chapter))
    await session.commit()
    session.expire_all()

    stored = await session.get(Episode, episode_id)
    assert stored is not None
    assert stored.chapter_id is None
