import logging
import os
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from tomarr.app import create_app
from tomarr.core.config import load_settings
from tomarr.core.logging import close_logging

TESTS_DIR = Path(__file__).parent
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


@pytest.fixture
def api_key(tmp_path: Path) -> str:
    # Reads config.toml, writing the first-run file if the app has not started yet, so the
    # lifespan that follows loads the same key.
    return load_settings(tmp_path).auth.apikey


@pytest.fixture
def client() -> Iterator[TestClient]:
    with TestClient(create_app()) as test_client:
        yield test_client


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
