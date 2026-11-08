from pathlib import Path


def test_cassette_dir_is_per_test_module(vcr_cassette_dir: str) -> None:
    expected = Path(__file__).parent / "fixtures" / "cassettes" / "test_conftest"

    assert Path(vcr_cassette_dir) == expected
