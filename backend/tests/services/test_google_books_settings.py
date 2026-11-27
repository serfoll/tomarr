import pytest

from tomarr.core.database import Database
from tomarr.services.google_books_settings import GOOGLE_BOOKS_API_KEY
from tomarr.services.settings import SettingsService, registry


@pytest.fixture
def service(database: Database) -> SettingsService:
    return SettingsService(database.session_factory)


def test_the_key_is_declared_with_an_empty_default() -> None:
    declared_keys = registry.keys()
    declared = {key.name: key for key in declared_keys}

    assert declared["google_books.api_key"] is GOOGLE_BOOKS_API_KEY
    assert GOOGLE_BOOKS_API_KEY.default == ""


async def test_a_stored_key_comes_back(service: SettingsService) -> None:
    assert await service.get(GOOGLE_BOOKS_API_KEY) == ""

    await service.set(GOOGLE_BOOKS_API_KEY, "abc")

    assert await service.get(GOOGLE_BOOKS_API_KEY) == "abc"
