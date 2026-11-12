from pathlib import Path

from tomarr.core.config import static_dir


def test_cassette_dir_is_per_test_module(vcr_cassette_dir: str) -> None:
    expected = Path(__file__).parent / "fixtures" / "cassettes" / "test_conftest"

    assert Path(vcr_cassette_dir) == expected


def test_no_test_serves_the_checkout_build_unless_it_asks_for_one() -> None:
    assert not static_dir().exists()
