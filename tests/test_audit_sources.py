"""Tests for the provenance audit script."""
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).parent.parent / "scripts" / "audit_sources.py"
ROOT = Path(__file__).parent.parent


def _run(args):
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        capture_output=True,
        text=True,
        cwd=str(ROOT),
    )


def test_audit_sources_check_passes():
    """--check should validate transfer records and source-manifest consistency."""
    result = _run(["--check"])
    assert result.returncode == 0, result.stderr
    assert "PASS" in result.stdout


def test_audit_sources_check_fails_on_bad_source_manifest_hash(tmp_path):
    """A corrupted source-manifest.sha256 should fail the consistency check."""
    sha_path = ROOT / "provenance" / "source-manifest.sha256"
    original = sha_path.read_text(encoding="utf-8")
    try:
        sha_path.write_text("0" * 64 + "  canonical-source-manifest.json\n", encoding="utf-8")
        result = _run(["--check"])
        assert result.returncode == 1, result.stderr
        assert "source-manifest.sha256" in result.stderr.lower()
    finally:
        sha_path.write_text(original, encoding="utf-8")


def test_audit_sources_check_fails_on_commit_mismatch(tmp_path):
    """A source-manifest.json canonical_commit mismatch should fail --check."""
    source_path = ROOT / "provenance" / "source-manifest.json"
    sha_path = ROOT / "provenance" / "source-manifest.sha256"
    original_source = source_path.read_text(encoding="utf-8")
    original_sha = sha_path.read_text(encoding="utf-8")
    try:
        data = __import__("json").loads(original_source)
        data["canonical_commit"] = "deadbeef" * 5
        source_path.write_text(
            __import__("json").dumps(data, indent=2, sort_keys=False),
            encoding="utf-8",
        )
        result = _run(["--check"])
        assert result.returncode == 1, result.stderr
        assert "canonical_commit" in result.stderr.lower()
    finally:
        source_path.write_text(original_source, encoding="utf-8")
        sha_path.write_text(original_sha, encoding="utf-8")
