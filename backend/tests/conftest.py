from pathlib import Path
from typing import Any

import pytest


@pytest.fixture(scope="module")
def vcr_cassette_dir() -> str:
    return str(Path(__file__).parent / "fixtures" / "cassettes")


@pytest.fixture
def vcr_config() -> dict[str, Any]:
    return {}
