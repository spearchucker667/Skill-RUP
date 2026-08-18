"""
Tests for scripts/generate_workflows.py.

Covers:
- Canonical workflows are generated from protocol/rup-protocol.yaml.
- --check compares deterministic content and does not modify files.
- Generate mode writes missing/changed files and never deletes existing files.
"""
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parent.parent.resolve()
SCRIPT = REPO_ROOT / "scripts" / "generate_workflows.py"


def test_check_passes_on_existing_workflows():
    """H-13: --check must pass when canonical workflows match deterministic content."""
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--check"],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "PASS" in result.stdout


def test_check_reports_missing_workflow(tmp_path):
    """--check fails when a canonical workflow file is missing."""
    wf_dir = tmp_path / "workflows"
    wf_dir.mkdir()
    # Copy only a subset of the real workflows.
    real_wf_dir = REPO_ROOT / "workflows"
    for wf in ("1-discovery.md", "2-planning.md"):
        (wf_dir / wf).write_text((real_wf_dir / wf).read_text(encoding="utf-8"), encoding="utf-8")

    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--check", "--workflows-dir", str(wf_dir)],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
    )
    assert result.returncode == 1, result.stdout + result.stderr
    assert "Missing workflows" in result.stderr


def test_generate_writes_missing_file_without_deleting_others(tmp_path):
    """H-13: generate mode must write missing canonical files and never delete unrelated files."""
    wf_dir = tmp_path / "workflows"
    wf_dir.mkdir()
    real_wf_dir = REPO_ROOT / "workflows"

    # Start with all canonical workflows except one.
    canonical_files = {
        "1-discovery.md",
        "2-planning.md",
        "3-execution.md",
        "4-verification.md",
        "bug-fixes.md",
        "tests.md",
        "ci-cd.md",
        "docs.md",
        "governance.md",
        "security.md",
        "containers.md",
        "observability.md",
    }
    for wf in canonical_files - {"4-verification.md"}:
        (wf_dir / wf).write_text((real_wf_dir / wf).read_text(encoding="utf-8"), encoding="utf-8")

    # Add an extra non-canonical file that must survive.
    extra = wf_dir / "extra-legacy.md"
    extra.write_text("legacy content", encoding="utf-8")

    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--workflows-dir", str(wf_dir)],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert (wf_dir / "4-verification.md").exists()
    assert extra.exists()
    assert extra.read_text(encoding="utf-8") == "legacy content"


def test_generate_does_not_overwrite_unchanged_files(tmp_path):
    """Generate mode reports up-to-date when all canonical files already match."""
    wf_dir = tmp_path / "workflows"
    wf_dir.mkdir()
    real_wf_dir = REPO_ROOT / "workflows"

    # Copy all canonical workflow files verbatim.
    for wf_file in real_wf_dir.glob("*.md"):
        (wf_dir / wf_file.name).write_text(wf_file.read_text(encoding="utf-8"), encoding="utf-8")

    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--workflows-dir", str(wf_dir)],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "already up to date" in result.stdout


def test_no_duplicate_documentation_workflow():
    """The generator's canonical name for the documentation workstream is docs.md."""
    wf_dir = REPO_ROOT / "workflows"
    assert (wf_dir / "docs.md").exists()
    assert not (wf_dir / "documentation.md").exists()


def test_workflows_derived_from_protocol_phases():
    """Canonical phase workflow files correspond to protocol phases."""
    wf_dir = REPO_ROOT / "workflows"
    for expected in ("1-discovery.md", "2-planning.md", "3-execution.md", "4-verification.md"):
        assert (wf_dir / expected).exists()
        content = (wf_dir / expected).read_text(encoding="utf-8")
        assert "## Raw Protocol Data" in content
        assert "Must comply with `rup-schema.json`" in content
