from dataclasses import dataclass
from typing import Generic, TypeVar

from pydantic import TypeAdapter
from sqlalchemy.dialects.sqlite import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from typing_extensions import TypeForm

from tomarr.domain.setting import Setting

# Covariant so the registry can hold every key as SettingKey[object]. Pyright infers a PEP 695
# dataclass as invariant, and that syntax cannot declare covariance.
T_co = TypeVar("T_co", covariant=True)


@dataclass(frozen=True)
class SettingKey(Generic[T_co]):  # noqa: UP046
    name: str
    # TypeForm, not type[T_co]: type[T] rejects `str | None` and other typing forms.
    type: TypeForm[T_co]
    default: T_co


class SettingsRegistry:
    def __init__(self) -> None:
        self._keys: dict[str, SettingKey[object]] = {}

    def declare[T](self, name: str, type: TypeForm[T], default: T) -> SettingKey[T]:
        if name in self._keys:
            raise ValueError(f"Setting {name!r} is already declared.")
        key = SettingKey(name, type, default)
        self._keys[name] = key
        return key

    def keys(self) -> list[SettingKey[object]]:
        return list(self._keys.values())


registry = SettingsRegistry()


class SettingsService:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def get[T](self, key: SettingKey[T]) -> T:
        async with self._session_factory() as session:
            row = await session.get(Setting, key.name)
        if row is None:
            return key.default
        return TypeAdapter(key.type).validate_python(row.value)

    async def set[T](self, key: SettingKey[T], value: T) -> None:
        adapter = TypeAdapter(key.type)
        stored = adapter.dump_python(adapter.validate_python(value), mode="json")
        statement = insert(Setting).values(key=key.name, value=stored)
        statement = statement.on_conflict_do_update(
            index_elements=[Setting.key], set_={"value": statement.excluded.value}
        )
        async with self._session_factory.begin() as session:
            await session.execute(statement)
