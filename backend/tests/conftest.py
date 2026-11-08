from pathlib import Path

import pytest

TESTS_DIR = Path(__file__).parent


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
