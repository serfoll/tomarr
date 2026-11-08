import logging
import os
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from tomarr.app import create_app
from tomarr.core.logging import close_logging

UVICORN_LOGGERS = ("uvicorn", "uvicorn.error", "uvicorn.access")


@pytest.fixture(autouse=True)
def isolated_environment(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    for name in [name for name in os.environ if name.startswith("TOMARR__")]:
        monkeypatch.delenv(name)
    monkeypatch.setenv("TOMARR_CONFIG_DIR", str(tmp_path))
    root = logging.getLogger()
    root_level = root.level
    saved = {
        name: (lg.level, lg.propagate, list(lg.handlers))
        for name in UVICORN_LOGGERS
        for lg in [logging.getLogger(name)]
    }
    yield
    close_logging()
    root.setLevel(root_level)
    for name, (level, propagate, handlers) in saved.items():
        lg = logging.getLogger(name)
        lg.setLevel(level)
        lg.propagate = propagate
        lg.handlers[:] = handlers


def test_lifespan_creates_config_and_log_file_and_releases_handlers(tmp_path: Path) -> None:
    root = logging.getLogger()
    handlers_before = list(root.handlers)

    with TestClient(create_app()) as client:
        assert (tmp_path / "config.toml").is_file()
        assert (tmp_path / "logs" / "tomarr.log").is_file()
        assert len(root.handlers) == len(handlers_before) + 2
        assert client.get("/api/v1/system/status").status_code == 200

    assert root.handlers == handlers_before


def test_lifespan_applies_log_level_from_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TOMARR__LOG__LEVEL", "debug")

    with TestClient(create_app()):
        assert logging.getLogger().level == logging.DEBUG


def test_lifespan_redacts_the_generated_api_key(tmp_path: Path) -> None:
    with TestClient(create_app()):
        config = (tmp_path / "config.toml").read_text(encoding="utf-8")
        apikey = next(
            line.split("=", 1)[1].strip().strip('"')
            for line in config.splitlines()
            if line.startswith("apikey")
        )
        logging.getLogger("tomarr.test").info("calling with %s", apikey)

    assert apikey not in (tmp_path / "logs" / "tomarr.log").read_text(encoding="utf-8")
