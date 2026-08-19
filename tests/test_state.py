"""
State-trust regression tests for RUP deterministic runtime (RUP-STATE tests).

These tests verify that runtime state is isolated to the controlled ``.rup/``
directory, that legacy root-level artifacts are not silently trusted, and that
the artifact ledger and run manifest accurately record provenance.
"""
import hashlib
import json
from pathlib import Path

import pytest

from runtime.paths import RupPaths
from runtime.state import StateManager
from runtime.artifact_builder import ArtifactBuilder


def test_load_json_does_not_fall_back_to_target_root(tmp_path):
    """StateManager.load_json must only read from the controlled state directory."""
    # Place a malicious root-level artifact.
    (tmp_path / "RUP_PLAN.json").write_text(
        json.dumps({"evil": True}), encoding="utf-8"
    )

    paths = RupPaths(tmp_path)
    state = StateManager(paths)

    # No .rup/RUP_PLAN.json exists yet, so load_json returns empty.
    data = state.load_json("RUP_PLAN.json")
    assert data == {}


def test_malicious_root_plan_is_ignored_by_default(tmp_path):
    """A malicious RUP_PLAN.json at the target root must be ignored unless migrated."""
    (tmp_path / "RUP_PLAN.json").write_text(
        json.dumps({"backlog": [{"id": "EVIL-001"}]}), encoding="utf-8"
    )

    paths = RupPaths(tmp_path)
    state = StateManager(paths)

    assert state.load_json("RUP_PLAN.json") == {}
    assert not (tmp_path / ".rup" / "RUP_PLAN.json").exists()


def test_migrate_legacy_state_imports_root_files_and_records_provenance(tmp_path):
    """migrate_legacy_state() imports root files into .rup/ and creates provenance."""
    plan_data = {"backlog": [{"id": "LEGACY-001"}], "selected_items": ["LEGACY-001"]}
    (tmp_path / "RUP_PLAN.json").write_text(json.dumps(plan_data), encoding="utf-8")

    paths = RupPaths(tmp_path)
    state = StateManager(paths)

    result = state.migrate_legacy_state()

    assert result["count"] == 1
    assert (tmp_path / ".rup" / "RUP_PLAN.json").exists()
    assert (tmp_path / ".rup" / "migration-provenance.json").exists()

    migrated = result["migrated"]
    assert len(migrated) == 1
    assert migrated[0]["artifact"] == "RUP_PLAN.json"
    assert "sha256" in migrated[0]
    assert migrated[0]["run_id"] == state.run_id

    provenance = state.load_json("migration-provenance.json")
    assert provenance["run_id"] == state.run_id
    assert provenance["artifacts"][0]["artifact"] == "RUP_PLAN.json"

    # The migrated content is now available in the controlled state directory.
    loaded = state.load_json("RUP_PLAN.json")
    assert loaded == plan_data


def test_record_artifact_populates_ledger(tmp_path):
    """_record_artifact() must record sha256, run_id, phase, type, and relative_path."""
    paths = RupPaths(tmp_path)
    state = StateManager(paths)

    state.save_json({"hello": "world"}, "RUP_DISCOVERY.json")

    ledger = state._artifact_ledger
    assert len(ledger) == 1
    entry = ledger[0]

    assert entry["name"] == "RUP_DISCOVERY.json"
    assert entry["sha256"]
    assert entry["run_id"] == state.run_id
    assert entry["phase"] == "discovery"
    assert entry["type"] == "json"
    assert entry["relative_path"] == "RUP_DISCOVERY.json"
    assert "created_at" in entry


def test_generate_and_save_manifest_includes_artifacts_ledger(tmp_path):
    """generate_and_save_manifest() must persist the artifacts ledger in the manifest."""
    paths = RupPaths(tmp_path)
    state = StateManager(paths)

    state.save_json({"hello": "world"}, "RUP_DISCOVERY.json")

    # Capture the ledger before the manifest is generated.
    ledger_before = list(state._artifact_ledger)

    manifest = state.generate_and_save_manifest(
        phases_completed=["discovery"],
        selected_items=["ITEM-001"],
        execution_changes_count=0,
        verification_status="pending",
    )

    assert manifest["run_id"] == state.run_id
    assert "artifacts" in manifest
    assert any(a["name"] == "RUP_DISCOVERY.json" for a in manifest["artifacts"])
    # The manifest ledger must not contain a self-reference entry.
    assert not any(a["name"] == "run-manifest.json" for a in manifest["artifacts"])
    # Every pre-existing ledger entry must be preserved.
    assert manifest["artifacts"] == ledger_before

    # Verify the saved file matches the returned manifest.
    loaded = state.load_json("run-manifest.json")
    assert loaded["artifacts"] == manifest["artifacts"]


def test_run_manifest_hash_sidecar_matches_final_file(tmp_path):
    """The run-manifest.json.sha256 sidecar must hash the final manifest bytes."""
    paths = RupPaths(tmp_path)
    state = StateManager(paths)

    state.save_json({"hello": "world"}, "RUP_DISCOVERY.json")
    state.generate_and_save_manifest(
        phases_completed=["discovery"],
        selected_items=["ITEM-001"],
        execution_changes_count=0,
        verification_status="pending",
    )

    manifest_path = paths.state_dir / "run-manifest.json"
    hash_path = paths.state_dir / "run-manifest.json.sha256"
    assert manifest_path.exists()
    assert hash_path.exists()

    expected_hash = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
    assert hash_path.read_text(encoding="utf-8").strip() == expected_hash


def test_custom_state_dir_outside_target_is_rejected(tmp_path):
    """RupPaths must reject a custom --state-dir that resolves outside the target."""
    target = tmp_path / "target_repo"
    target.mkdir()
    outside = tmp_path / "external_state"
    outside.mkdir()

    with pytest.raises(PermissionError):
        RupPaths(target, state_dir=outside)


def test_state_trust_boundary(tmp_path):
    """Integration smoke test: state stays inside .rup/ and respects the path jail."""
    paths = RupPaths(tmp_path)
    state = StateManager(paths)

    state.save_json({"phase": "discovery"}, "RUP_DISCOVERY.json")
    state.update_session_state("discovery")

    assert (tmp_path / ".rup" / "RUP_DISCOVERY.json").exists()
    assert (tmp_path / ".rup" / "session-state.json").exists()
    assert state.load_json("RUP_DISCOVERY.json") == {"phase": "discovery"}


def test_run_id_is_unique_per_invocation(tmp_path):
    """RUP-STATE-001: run IDs must be unique for each StateManager invocation."""
    paths = RupPaths(tmp_path)
    state_a = StateManager(paths)
    state_b = StateManager(paths)
    assert state_a.run_id != state_b.run_id
    assert state_a.run_id.startswith("rup-")
    assert state_b.run_id.startswith("rup-")


def test_run_id_differs_for_different_targets(tmp_path):
    """RUP-STATE-002: run IDs must differ for different target paths."""
    target_a = tmp_path / "repo_a"
    target_b = tmp_path / "repo_b"
    target_a.mkdir()
    target_b.mkdir()

    state_a = StateManager(RupPaths(target_a))
    state_b = StateManager(RupPaths(target_b))
    assert state_a.run_id != state_b.run_id


def test_artifact_builder_records_markdown_in_ledger(tmp_path):
    """ArtifactBuilder must record Markdown artifacts in the state ledger."""
    paths = RupPaths(tmp_path)
    state = StateManager(paths)
    builder = ArtifactBuilder(paths, state=state)

    builder.build_markdown(
        "discovery-report.md", {"repo_metadata": {"name": "test"}}, "RUP_DISCOVERY.md"
    )

    assert (tmp_path / ".rup" / "RUP_DISCOVERY.md").exists()
    entry = next(
        (e for e in state._artifact_ledger if e["name"] == "RUP_DISCOVERY.md"), None
    )
    assert entry is not None
    assert entry["type"] == "markdown"
    assert entry["phase"] == "discovery"
    assert entry["sha256"]
    assert entry["run_id"] == state.run_id
    assert entry["relative_path"] == "RUP_DISCOVERY.md"
    assert "created_at" in entry


def test_rebuild_artifact_ledger_includes_files_on_disk(tmp_path):
    """_rebuild_artifact_ledger must record artifacts that were never explicitly tracked."""
    paths = RupPaths(tmp_path)
    state = StateManager(paths)
    state_dir = tmp_path / ".rup"
    state_dir.mkdir(parents=True, exist_ok=True)

    (state_dir / "RUP_DISCOVERY.json").write_text(
        json.dumps({"x": 1}), encoding="utf-8"
    )
    (state_dir / "RUP_DISCOVERY.md").write_text("# Discovery", encoding="utf-8")

    state._rebuild_artifact_ledger()

    names = {e["name"] for e in state._artifact_ledger}
    assert "RUP_DISCOVERY.json" in names
    assert "RUP_DISCOVERY.md" in names

    json_entry = next(e for e in state._artifact_ledger if e["name"] == "RUP_DISCOVERY.json")
    assert json_entry["type"] == "json"
    assert json_entry["phase"] == "discovery"
    assert json_entry["sha256"]

    md_entry = next(e for e in state._artifact_ledger if e["name"] == "RUP_DISCOVERY.md")
    assert md_entry["type"] == "markdown"
    assert md_entry["phase"] == "discovery"


def test_fresh_state_manager_recovers_ledger_from_disk(tmp_path):
    """A new StateManager must rebuild the ledger from existing .rup/ artifacts."""
    paths = RupPaths(tmp_path)
    original = StateManager(paths)
    original.save_json({"phase": "discovery"}, "RUP_DISCOVERY.json")
    original.update_session_state("discovery")

    fresh = StateManager(paths)
    manifest = fresh.generate_and_save_manifest(
        phases_completed=["discovery"],
        selected_items=[],
        execution_changes_count=0,
        verification_status="pending",
    )

    artifact_names = {a["name"] for a in manifest["artifacts"]}
    assert "RUP_DISCOVERY.json" in artifact_names
    assert "session-state.json" in artifact_names
    assert "run-manifest.json" not in artifact_names
    assert (paths.state_dir / "run-manifest.json.sha256").exists()


def test_generate_and_save_manifest_rebuilds_full_ledger(tmp_path):
    """generate_and_save_manifest must record every lifecycle artifact on disk."""
    paths = RupPaths(tmp_path)
    state = StateManager(paths)
    state_dir = tmp_path / ".rup"
    state_dir.mkdir(parents=True, exist_ok=True)

    lifecycle_artifacts = [
        "RUP_DISCOVERY.json",
        "RUP_PLAN.json",
        "RUP_EXECUTION.json",
        "RUP_VERIFICATION.json",
        "RUP_FINAL_REPORT.json",
        "RUP_DISCOVERY.md",
        "RUP_PLAN.md",
        "RUP_EXECUTION.md",
        "RUP_VERIFICATION.md",
        "RUP_FINAL_REPORT.md",
        "session-state.json",
    ]
    for name in lifecycle_artifacts:
        content = json.dumps({}) if name.endswith(".json") else "# report"
        (state_dir / name).write_text(content, encoding="utf-8")

    manifest = state.generate_and_save_manifest(
        phases_completed=["discovery", "planning", "execution", "verification", "reporting"],
        selected_items=["ITEM-001"],
        execution_changes_count=1,
        verification_status="passed",
    )

    artifact_names = {a["name"] for a in manifest["artifacts"]}
    for name in lifecycle_artifacts:
        assert name in artifact_names, f"{name} missing from manifest artifacts"
    assert "run-manifest.json" not in artifact_names
    assert "run-manifest.json.sha256" not in artifact_names
    assert (state_dir / "run-manifest.json.sha256").exists()

    loaded = state.load_json("run-manifest.json")
    assert loaded["artifacts"] == manifest["artifacts"]


def test_resume_recovers_existing_run_id(tmp_path):
    """StateManager(resume=True) must reuse the run_id from session-state.json."""
    paths = RupPaths(tmp_path)
    original = StateManager(paths)
    original.update_session_state("discovery")

    resumed = StateManager(paths, resume=True)
    assert resumed.run_id == original.run_id


def test_second_lifecycle_does_not_leak_old_checksum_into_manifest(tmp_path):
    """A new lifecycle's manifest must not include the previous run's checksum sidecar."""
    paths = RupPaths(tmp_path)

    state1 = StateManager(paths)
    state1.save_json({"phase": "discovery"}, "RUP_DISCOVERY.json")
    state1.generate_and_save_manifest(
        phases_completed=["discovery"],
        selected_items=[],
        execution_changes_count=0,
        verification_status="pending",
    )

    state2 = StateManager(paths)
    state2.save_json({"phase": "discovery"}, "RUP_DISCOVERY.json")
    manifest2 = state2.generate_and_save_manifest(
        phases_completed=["discovery"],
        selected_items=[],
        execution_changes_count=0,
        verification_status="pending",
    )

    artifact_names = {a["name"] for a in manifest2["artifacts"]}
    assert "run-manifest.json.sha256" not in artifact_names
