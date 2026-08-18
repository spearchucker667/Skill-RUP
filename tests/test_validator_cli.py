import json
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


def test_schemas_directory_is_validated():
    """``all`` must meta-validate derived JSON Schema files under schemas/."""
    result = _run(["all", "."])
    assert result.returncode == 0, result.stdout + result.stderr
    for name in (
        "schemas/run-manifest.schema.json",
        "schemas/session-state.schema.json",
        "schemas/final-report.schema.json",
        "schemas/rollback.schema.json",
        "schemas/handoff.schema.json",
    ):
        assert name in result.stdout, f"Expected {name} to be validated; got:\n{result.stdout}"


def test_development_directory_not_ignored(tmp_path):
    """``all`` must no longer ignore JSON artifacts under development/."""
    dev = tmp_path / "development" / "source-audit"
    dev.mkdir(parents=True)
    manifest = {
        "run_id": "r1",
        "created_at": "2026-01-01T00:00:00Z",
        "protocol_version": "3.0.0",
        "phases_completed": [],
        "verification_status": "passed",
    }
    (dev / "run-manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

    result = _run(["all", str(tmp_path)])
    assert result.returncode == 0, result.stdout + result.stderr
    assert "development/source-audit/run-manifest.json" in result.stdout


def test_derived_artifacts_validated(tmp_path):
    """``all`` must validate run-manifest, session-state, final-report, rollback, and handoff."""
    (tmp_path / "run-manifest.json").write_text(
        json.dumps(
            {
                "run_id": "r1",
                "created_at": "2026-01-01T00:00:00Z",
                "protocol_version": "3.0.0",
                "phases_completed": ["discovery"],
                "verification_status": "passed",
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "session-state.json").write_text(
        json.dumps(
            {
                "run_id": "r1",
                "current_phase": "discovery",
                "timestamp": "2026-01-01T00:00:00Z",
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "RUP_FINAL_REPORT.json").write_text(
        json.dumps(
            {
                "summary": {"overall_status": "passed"},
                "phases_completed": ["discovery"],
                "metrics": {},
                "changes_summary": [],
                "handoff_instructions": "Handoff",
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "rollback.json").write_text(
        json.dumps({"trigger": "test", "steps": [], "status": "pending"}),
        encoding="utf-8",
    )
    (tmp_path / "handoff.json").write_text(
        json.dumps({"summary": "test", "next_actions": []}),
        encoding="utf-8",
    )

    result = _run(["all", str(tmp_path)])
    assert result.returncode == 0, result.stdout + result.stderr
    for name in ("run-manifest.json", "session-state.json", "RUP_FINAL_REPORT.json", "rollback.json", "handoff.json"):
        assert name in result.stdout, f"Expected {name} to appear in validation output"


def test_invalid_derived_artifact_fails(tmp_path):
    """A run-manifest.json missing required fields must be reported invalid."""
    (tmp_path / "run-manifest.json").write_text(
        json.dumps({"created_at": "2026-01-01T00:00:00Z"}), encoding="utf-8"
    )
    result = _run(["all", str(tmp_path)])
    assert result.returncode == 1, result.stdout + result.stderr
    assert "run-manifest.json" in result.stdout
    assert "Invalid" in result.stdout


def test_invalid_json_schema_fails(tmp_path):
    """``all`` must reject malformed JSON Schema documents under schemas/."""
    proto_dir = tmp_path / "protocol"
    proto_dir.mkdir()
    (proto_dir / "rup-schema.json").write_text("{}", encoding="utf-8")
    schemas_dir = tmp_path / "schemas"
    schemas_dir.mkdir()
    (schemas_dir / "invalid.schema.json").write_text(
        json.dumps({"type": "not_a_valid_type"}), encoding="utf-8"
    )

    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--schema",
            str(proto_dir / "rup-schema.json"),
            "all",
            str(tmp_path),
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 1, result.stdout + result.stderr
    assert "invalid.schema.json" in result.stdout
    assert "Invalid" in result.stdout
