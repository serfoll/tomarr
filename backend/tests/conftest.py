from pathlib import Path
from typing import Any

import pytest


@pytest.fixture(scope="module")
def vcr_cassette_dir() -> str:
    return str(Path(__file__).parent / "fixtures" / "cassettes")


@pytest.fixture
def vcr_config() -> dict[str, Any]:
    return {
        "filter_headers": ["authorization", "x-api-key", "x-goog-api-key"],
        "filter_query_parameters": ["apikey", "api_key", "key", "token"],
        "filter_post_data_parameters": ["apikey", "api_key", "key", "token"],
    }
