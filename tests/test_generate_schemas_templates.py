"""Regression tests for scripts/generate_schemas_templates.py."""
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "generate_schemas_templates.py"
SCHEMA = ROOT / "schemas" / "capability-lineage.schema.json"


def test_check_passes_on_matching_schema():
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--check"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr


def test_check_fails_on_stale_schema():
    original = SCHEMA.read_text(encoding="utf-8")
    try:
        SCHEMA.write_text(original.replace("verification_level", "stale_field"), encoding="utf-8")
        result = subprocess.run(
            [sys.executable, str(SCRIPT), "--check"],
            capture_output=True,
            text=True,
        )
        assert result.returncode != 0, result.stdout
        assert "mismatch" in result.stderr.lower() or "stale_field" in result.stderr
    finally:
        SCHEMA.write_text(original, encoding="utf-8")
