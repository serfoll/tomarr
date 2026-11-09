from collections.abc import AsyncIterator
from pathlib import Path
from typing import cast

import pytest
from pydantic import BaseModel, ValidationError
from sqlalchemy import text

from tomarr.core.database import Database, create_database
from tomarr.core.migrations import upgrade_to_head
from tomarr.services.settings import SettingKey, SettingsRegistry, SettingsService


class ProwlarrSection(BaseModel):
    url: str
    api_key: str
    categories: list[int]


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


@pytest.fixture
def service(database: Database) -> SettingsService:
    return SettingsService(database.session_factory)


@pytest.fixture
def registry() -> SettingsRegistry:
    return SettingsRegistry()


async def assert_round_trip[T](service: SettingsService, key: SettingKey[T], value: T) -> None:
    await service.set(key, value)
    assert await service.get(key) == value


async def test_int_round_trip(service: SettingsService, registry: SettingsRegistry) -> None:
    await assert_round_trip(service, registry.declare("port", int, 8080), 9090)


async def test_bool_round_trip(service: SettingsService, registry: SettingsRegistry) -> None:
    key = registry.declare("enabled", bool, True)
    await assert_round_trip(service, key, False)


async def test_str_round_trip(service: SettingsService, registry: SettingsRegistry) -> None:
    await assert_round_trip(service, registry.declare("host", str, "localhost"), "tomarr.lan")


async def test_optional_str_set_to_none_is_stored_not_defaulted(
    service: SettingsService, registry: SettingsRegistry
) -> None:
    key = registry.declare("proxy", str | None, "http://proxy")

    await service.set(key, None)

    assert await service.get(key) is None


async def test_list_round_trip(service: SettingsService, registry: SettingsRegistry) -> None:
    key = registry.declare("tags", list[str], [])
    await assert_round_trip(service, key, ["manga", "webtoon"])


async def test_pydantic_model_round_trip(
    service: SettingsService, registry: SettingsRegistry
) -> None:
    default = ProwlarrSection(url="", api_key="", categories=[])
    key = registry.declare("prowlarr", ProwlarrSection, default)
    value = ProwlarrSection(url="http://prowlarr:9696", api_key="abc", categories=[7030, 7020])

    await service.set(key, value)

    stored = await service.get(key)
    assert isinstance(stored, ProwlarrSection)
    assert stored == value


async def test_get_returns_default_when_never_written(
    service: SettingsService, registry: SettingsRegistry
) -> None:
    key = registry.declare("port", int, 8080)

    assert await service.get(key) == 8080


async def test_second_set_overwrites_the_first(
    database: Database, service: SettingsService, registry: SettingsRegistry
) -> None:
    key = registry.declare("port", int, 8080)

    await service.set(key, 1)
    await service.set(key, 2)

    assert await service.get(key) == 2
    async with database.session_factory() as session:
        count = (await session.execute(text("SELECT count(*) FROM setting"))).scalar_one()
    assert count == 1


async def test_stored_value_that_no_longer_fits_raises_on_get(
    database: Database, service: SettingsService, registry: SettingsRegistry
) -> None:
    key = registry.declare("port", int, 8080)
    async with database.session_factory.begin() as session:
        await session.execute(
            text("INSERT INTO setting (key, value) VALUES ('port', :value)"),
            {"value": '"not a number"'},
        )

    with pytest.raises(ValidationError):
        await service.get(key)


async def test_set_with_wrong_type_raises_and_keeps_the_stored_value(
    service: SettingsService, registry: SettingsRegistry
) -> None:
    key = registry.declare("port", int, 8080)
    await service.set(key, 9090)

    with pytest.raises(ValidationError):
        await service.set(key, cast("int", "not a number"))

    assert await service.get(key) == 9090


async def test_value_survives_a_new_database_on_the_same_file(
    db_path: Path, service: SettingsService, registry: SettingsRegistry
) -> None:
    key = registry.declare("port", int, 8080)
    await service.set(key, 9090)

    reopened = create_database(db_path)
    try:
        assert await SettingsService(reopened.session_factory).get(key) == 9090
    finally:
        await reopened.dispose()


def test_registry_refuses_a_duplicate_name(registry: SettingsRegistry) -> None:
    registry.declare("port", int, 8080)

    with pytest.raises(ValueError, match="port"):
        registry.declare("port", str, "x")


def test_registry_lists_declared_keys(registry: SettingsRegistry) -> None:
    port = registry.declare("port", int, 8080)
    host = registry.declare("host", str, "localhost")

    assert registry.keys() == [port, host]


def test_registries_do_not_share_keys() -> None:
    first = SettingsRegistry()
    first.declare("port", int, 8080)

    assert SettingsRegistry().keys() == []
