"""
Unit tests for the RUP execution phase.

These tests exercise RUP-EXEC-001..007 semantics in isolated temporary
repositories so they do not depend on the state of the Skill-RUP repository.
"""
import subprocess
from pathlib import Path

import pytest

from runtime.artifact_builder import ArtifactBuilder
from runtime.execution import ExecutionPhase
from runtime.paths import RupPaths
from runtime.state import StateManager


def _init_git(repo_dir: Path) -> None:
    subprocess.run(["git", "init", "--quiet", str(repo_dir)], check=True, capture_output=True)
    subprocess.run(
        ["git", "-C", str(repo_dir), "config", "user.email", "test@example.com"],
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "-C", str(repo_dir), "config", "user.name", "Test Runner"],
        check=True,
        capture_output=True,
    )


def _write_plan_and_discovery(
    repo_dir: Path, backlog: list, selected_items: list
) -> ExecutionPhase:
    paths = RupPaths(repo_dir)
    state = StateManager(paths)
    plan = {
        "backlog": backlog,
        "selected_items": selected_items,
        "execution_order": selected_items,
        "risk_analysis": {},
    }
    state.save_json(plan, "RUP_PLAN.json")

    discovery = {
        "repo_metadata": {
            "primary_language": "python",
            "name": repo_dir.name,
            "repo_type": "application",
        }
    }
    state.save_json(discovery, "RUP_DISCOVERY.json")

    builder = ArtifactBuilder(paths)
    return ExecutionPhase(repo_dir, StateManager(paths), builder)


def test_dirty_tracked_and_untracked_files_not_attributed_to_rup(tmp_path):
    """RUP-EXEC-005: pre-existing dirty files must not appear as RUP changes."""
    repo = tmp_path / "dirty_repo"
    repo.mkdir()
    src = repo / "src"
    src.mkdir()
    (src / "existing.py").write_text("# original\n")
    (repo / "untracked.txt").write_text("# untracked\n")

    _init_git(repo)
    subprocess.run(
        ["git", "-C", str(repo), "add", "src/existing.py"],
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "-C", str(repo), "commit", "-m", "init", "--quiet"],
        check=True,
        capture_output=True,
    )
    # Modify tracked file after baseline commit.
    (src / "existing.py").write_text("# modified by user\n")

    phase = _write_plan_and_discovery(
        repo,
        backlog=[
            {
                "id": "DOCS-001",
                "category": "docs",
                "title": "Missing README",
                "acceptance_criteria": [],
            }
        ],
        selected_items=["DOCS-001"],
    )
    data = phase.execute()

    change_paths = {c["file_path"] for c in data["changes"]}
    assert "src/existing.py" not in change_paths
    assert "untracked.txt" not in change_paths
    assert "README.md" in change_paths


def test_rup_only_changes_attributed_to_backlog_items(tmp_path):
    """RUP-EXEC-006: new RUP-generated files carry the causing backlog item id."""
    repo = tmp_path / "clean_repo"
    repo.mkdir()
    _init_git(repo)
    subprocess.run(
        ["git", "-C", str(repo), "commit", "--allow-empty", "-m", "init", "--quiet"],
        check=True,
        capture_output=True,
    )

    phase = _write_plan_and_discovery(
        repo,
        backlog=[
            {
                "id": "DOCS-001",
                "category": "docs",
                "title": "Missing README",
                "acceptance_criteria": [],
            }
        ],
        selected_items=["DOCS-001"],
    )
    data = phase.execute()

    readme_changes = [c for c in data["changes"] if c["file_path"] == "README.md"]
    assert len(readme_changes) == 1
    assert readme_changes[0]["backlog_item_id"] == "DOCS-001"


def test_tautological_tests_are_not_generated(tmp_path):
    """RUP-EXEC-001: ws_tests must never emit assert-True placeholder tests."""
    repo = tmp_path / "tests_repo"
    repo.mkdir()
    _init_git(repo)
    subprocess.run(
        ["git", "-C", str(repo), "commit", "--allow-empty", "-m", "init", "--quiet"],
        check=True,
        capture_output=True,
    )

    phase = _write_plan_and_discovery(
        repo,
        backlog=[
            {
                "id": "TEST-001",
                "category": "tests",
                "title": "Missing Test Framework",
                "acceptance_criteria": [
                    "Test framework configuration and baseline test runner are established"
                ],
            }
        ],
        selected_items=["TEST-001"],
    )
    data = phase.execute()

    for change in data["changes"]:
        assert "test_sanity" not in change.get("file_path", "")
        assert "assert True" not in change.get("rationale", "")

    # No generated Python test file should contain a tautology.
    for test_file in repo.rglob("*.py"):
        assert "assert True" not in test_file.read_text()


def test_truncated_license_is_not_generated(tmp_path):
    """RUP-EXEC-001: LICENSE must contain the complete Apache-2.0 text if created."""
    repo = tmp_path / "license_repo"
    repo.mkdir()
    _init_git(repo)
    subprocess.run(
        ["git", "-C", str(repo), "commit", "--allow-empty", "-m", "init", "--quiet"],
        check=True,
        capture_output=True,
    )

    phase = _write_plan_and_discovery(
        repo,
        backlog=[
            {
                "id": "GOV-002",
                "category": "governance",
                "title": "Missing Open Source License",
                "acceptance_criteria": [],
            }
        ],
        selected_items=["GOV-002"],
    )
    data = phase.execute()

    license_changes = [c for c in data["changes"] if c["file_path"] == "LICENSE"]
    if license_changes:
        content = (repo / "LICENSE").read_text()
        assert "Version 2.0, January 2004" in content
        assert "END OF TERMS AND CONDITIONS" in content
        assert len(content) > 5000
    else:
        # A recommendation is acceptable only when the full text is unavailable.
        recommendations = [
            c for c in data["changes"] if c["change_type"] == "recommendation"
        ]
        assert any("license" in c.get("rationale", "").lower() for c in recommendations)


def test_rollback_procedure_contains_expected_lists(tmp_path):
    """RUP-EXEC-004: rollback procedure must list created/modified/deleted/renamed/config files."""
    repo = tmp_path / "rollback_repo"
    repo.mkdir()
    _init_git(repo)
    subprocess.run(
        ["git", "-C", str(repo), "commit", "--allow-empty", "-m", "init", "--quiet"],
        check=True,
        capture_output=True,
    )

    phase = _write_plan_and_discovery(
        repo,
        backlog=[
            {
                "id": "DOCS-001",
                "category": "docs",
                "title": "Missing README",
                "acceptance_criteria": [],
            }
        ],
        selected_items=["DOCS-001"],
    )
    data = phase.execute()

    rb = data["rollback_procedure"]
    assert isinstance(rb["created"], list)
    assert isinstance(rb["modified"], list)
    assert isinstance(rb["deleted"], list)
    assert isinstance(rb["renamed"], list)
    assert isinstance(rb["config_changed"], list)
    assert "README.md" in rb["created"]
    assert any("README.md" in cmd for cmd in rb["commands"])


def test_non_selected_backlog_item_does_not_produce_changes(tmp_path):
    """RUP-EXEC-006: unselected backlog items must not generate or own changes."""
    repo = tmp_path / "selective_repo"
    repo.mkdir()
    _init_git(repo)
    subprocess.run(
        ["git", "-C", str(repo), "commit", "--allow-empty", "-m", "init", "--quiet"],
        check=True,
        capture_output=True,
    )

    phase = _write_plan_and_discovery(
        repo,
        backlog=[
            {
                "id": "DOCS-001",
                "category": "docs",
                "title": "Missing README",
                "acceptance_criteria": [],
            },
            {
                "id": "DOCS-002",
                "category": "docs",
                "title": "Missing CONTRIBUTING",
                "acceptance_criteria": [],
            },
        ],
        selected_items=["DOCS-001"],
    )
    data = phase.execute()

    assert not any(c["backlog_item_id"] == "DOCS-002" for c in data["changes"])
    assert not any(c["file_path"] == "CONTRIBUTING.md" for c in data["changes"])
    assert any(c["file_path"] == "README.md" for c in data["changes"])
