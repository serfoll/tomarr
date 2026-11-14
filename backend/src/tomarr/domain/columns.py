from enum import StrEnum

from sqlalchemy import Enum


def _values(members: type[StrEnum]) -> list[str]:
    return [member.value for member in members]


def string_enum(enum_class: type[StrEnum]) -> Enum:
    """A StrEnum column stored as a plain string with no CHECK, since SQLite cannot alter one."""
    return Enum(enum_class, native_enum=False, create_constraint=False, values_callable=_values)
