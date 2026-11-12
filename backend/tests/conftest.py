import logging
import os
from collections.abc import AsyncIterator, Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from tomarr.app import create_app
from tomarr.core.config import load_settings
from tomarr.core.database import Database, create_database
from tomarr.core.logging import close_logging
from tomarr.core.migrations import upgrade_to_head

TESTS_DIR = Path(__file__).parent
UVICORN_LOGGERS = ("uvicorn", "uvicorn.error", "uvicorn.access")


class HiddenStr(str):
    """A string whose repr hides the value, so a failing test cannot print it."""

    def __repr__(self) -> str:
        return "<hidden>"


@pytest.fixture(autouse=True)
def isolated_environment(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    for name in [name for name in os.environ if name.startswith("TOMARR__")]:
        monkeypatch.delenv(name)
    monkeypatch.setenv("TOMARR_CONFIG_DIR", str(tmp_path))
    # The default is the checkout's frontend/dist, so a local build would change what tests see.
    monkeypatch.setenv("TOMARR_STATIC_DIR", str(tmp_path / "no-build"))
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


@pytest.fixture
def api_key(tmp_path: Path) -> str:
    # Reads config.toml, writing the first-run file if the app has not started yet, so the
    # lifespan that follows loads the same key.
    return HiddenStr(load_settings(tmp_path).auth.apikey)


@pytest.fixture
def client() -> Iterator[TestClient]:
    with TestClient(create_app()) as test_client:
        yield test_client


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


@pytest.fixture(scope="module")
def vcr_cassette_dir(request: pytest.FixtureRequest) -> str:
    # Keyed by the module path under tests/, not the bare basename, because mirrored
    # test paths repeat basenames (tests/parser/test_volume.py, tests/domain/test_volume.py).
    module = request.path.relative_to(TESTS_DIR).with_suffix("")
    return str(TESTS_DIR / "fixtures" / "cassettes" / module)


@pytest.fixture
def vcr_config() -> dict[str, list[str]]:
    return {
        "filter_headers": ["authorization", "x-api-key", "x-goog-api-key"],
        "filter_query_parameters": ["apikey", "api_key", "key", "token"],
        "filter_post_data_parameters": ["apikey", "api_key", "key", "token"],
    }
