import pytest

from tomarr.commands.registry import CommandRegistry


async def noop(payload: dict[str, object]) -> dict[str, object] | None:
    return None


async def other(payload: dict[str, object]) -> dict[str, object] | None:
    return payload


def test_get_returns_the_registered_handler() -> None:
    registry = CommandRegistry()
    registry.register("refresh", noop)
    registry.register("scan", other)

    assert registry.get("refresh") is noop
    assert registry.get("scan") is other


def test_registering_a_type_twice_raises() -> None:
    registry = CommandRegistry()
    registry.register("refresh", noop)

    with pytest.raises(ValueError, match="refresh"):
        registry.register("refresh", other)

    assert registry.get("refresh") is noop


def test_unknown_type_raises_key_error() -> None:
    registry = CommandRegistry()

    with pytest.raises(KeyError, match="missing"):
        registry.get("missing")
