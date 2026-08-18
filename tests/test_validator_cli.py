import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).parent.parent / "scripts" / "validate_rup.py"
SCHEMA = Path(__file__).parent.parent / "protocol" / "rup-schema.json"


def _run(args, cwd=None):
    return subprocess.run(
        [sys.executable, str(SCRIPT), "--schema", str(SCHEMA), *args],
        capture_output=True,
        text=True,
        cwd=str(cwd or Path(__file__).parent.parent),
    )


def test_canonical_invocation_all():
    """Canonical form: schema before subcommand."""
    result = _run(["all", "."])
    assert result.returncode == 0, result.stdout + result.stderr
    assert "PASS" in result.stdout or "Valid" in result.stdout or "files" in result.stdout


def test_backwards_compatible_invocation_all():
    """Compatibility form: schema after subcommand positional args."""
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "all", ".", "--schema", str(SCHEMA)],
        capture_output=True,
        text=True,
        cwd=str(Path(__file__).parent.parent),
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_empty_directory_fails_without_allow_empty(tmp_path):
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "all", str(tmp_path), "--schema", str(SCHEMA)],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 1
    assert "FAIL/EMPTY" in result.stdout or "FAIL/EMPTY" in result.stderr


def test_empty_directory_allowed_with_flag(tmp_path):
    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "all",
            str(tmp_path),
            "--schema",
            str(SCHEMA),
            "--allow-empty",
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_schema_after_output_subcommand(tmp_path):
    sample = tmp_path / "sample_discovery.json"
    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "sample",
            "discovery",
            "-o",
            str(sample),
            "--schema",
            str(SCHEMA),
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert sample.exists()
