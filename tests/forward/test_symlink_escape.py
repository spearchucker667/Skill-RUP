"""Forward tests for symlink jail enforcement."""
from pathlib import Path

import pytest

from runtime.cli import run_full_lifecycle
from tests.forward.fixtures import build_fixture


def test_lifecycle_does_not_read_external_symlink_target(tmp_path):
    repo = tmp_path / "symlink_escape_repo"
    build_fixture("symlink_file_escape", repo)

    rc = run_full_lifecycle(repo, max_files=5)
    # Lifecycle may fail for other reasons; the important invariant is that the
    # external sentinel is never reported as a finding.
    assert rc in (0, 1)

    discovery_path = repo / ".rup" / "RUP_DISCOVERY.json"
    assert discovery_path.exists()
    text = discovery_path.read_text(encoding="utf-8")
    assert "EXTERNAL_SECRET" not in text
    assert "AKIAIOSFODNN7EXAMPLE" not in text

    verification_path = repo / ".rup" / "RUP_VERIFICATION.json"
    if verification_path.exists():
        text = verification_path.read_text(encoding="utf-8")
        assert "EXTERNAL_SECRET" not in text
        assert "AKIAIOSFODNN7EXAMPLE" not in text
