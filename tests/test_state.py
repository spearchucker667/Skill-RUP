"""
State-trust regression tests for RUP deterministic runtime (RUP-STATE tests).

These tests verify that runtime state is isolated to the controlled ``.rup/``
directory, that legacy root-level artifacts are not silently trusted, and that
the artifact ledger and run manifest accurately record provenance.
"""
import json
from pathlib import Path

import pytest

from runtime.paths import RupPaths
from runtime.state import StateManager


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

    # Capture the ledger before the manifest is generated; the manifest itself
    # is recorded afterward and must not appear in its own artifacts list.
    ledger_before = list(state._artifact_ledger)

    manifest = state.generate_and_save_manifest(
        phases_completed=["discovery"],
        selected_items=["ITEM-001"],
        execution_changes_count=0,
        verification_status="pending",
    )

    assert manifest["run_id"] == state.run_id
    assert "artifacts" in manifest
    assert manifest["artifacts"] == ledger_before
    assert any(a["name"] == "RUP_DISCOVERY.json" for a in manifest["artifacts"])

    # Verify the saved file matches the returned manifest.
    loaded = state.load_json("run-manifest.json")
    assert loaded["artifacts"] == manifest["artifacts"]


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
