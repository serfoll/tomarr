import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from tomarr.openapi import main

BACKEND_DIR = Path(__file__).parent.parent


def dump(capsys: pytest.CaptureFixture[str]) -> str:
    main()
    return capsys.readouterr().out


def test_main_writes_the_schema_as_json_and_nothing_else(
    capsys: pytest.CaptureFixture[str],
) -> None:
    schema = json.loads(dump(capsys))

    assert schema["openapi"].startswith("3.")
    assert {"/api/v1/system/status", "/api/v1/auth/login", "/api/v1/commands/events"} <= set(
        schema["paths"]
    )


def test_output_ends_with_a_single_newline(capsys: pytest.CaptureFixture[str]) -> None:
    output = dump(capsys)

    assert output.endswith("}\n")


def test_output_is_identical_between_calls(capsys: pytest.CaptureFixture[str]) -> None:
    assert dump(capsys) == dump(capsys)


def test_module_run_as_a_script_prints_the_same_schema(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    expected = dump(capsys)

    result = subprocess.run(
        [sys.executable, "-m", "tomarr.openapi"],
        cwd=BACKEND_DIR,
        env={**os.environ, "TOMARR_CONFIG_DIR": str(tmp_path / "script-config")},
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout == expected
