"""Unit tests for the RUP reporting phase."""
import json
import shlex
from pathlib import Path

import pytest

from runtime.artifact_builder import ArtifactBuilder
from runtime.paths import RupPaths
from runtime.reporting import ReportingPhase
from runtime.state import StateManager


def _write_phase_states(
    repo_dir: Path,
    selected_items: list[str],
    verification_status: str,
    execution_state: dict | None = None,
) -> ReportingPhase:
    paths = RupPaths(repo_dir)
    state = StateManager(paths)

    state.save_json(
        {
            "repo_metadata": {"name": "test"},
            "risk_assessment": {
                "production_readiness_score": 60,
                "technical_debt_score": 40,
            },
        },
        "RUP_DISCOVERY.json",
    )
    state.save_json(
        {
            "backlog": [
                {
                    "id": "BUG-001",
                    "priority": "P0",
                    "title": "Bug fix",
                    "category": "bugs",
                    "estimated_effort_minutes": 30,
                }
            ],
            "selected_items": selected_items,
            "risk_analysis": {},
        },
        "RUP_PLAN.json",
    )
    state.save_json(
        {"changes": [], "commits": [], "local_verification": {}},
        "RUP_EXECUTION.json",
    )
    state.save_json(
        {
            "verification_results": {"overall_status": verification_status},
            "metrics": {},
            "audit_trail": [],
        },
        "RUP_VERIFICATION.json",
    )
    if execution_state is not None:
        state.save_json(execution_state, "execution-state.json")

    builder = ArtifactBuilder(paths, state=state)
    return ReportingPhase(repo_dir, StateManager(paths), builder)


def test_incomplete_selected_item_becomes_follow_up_and_blocks_readiness(tmp_path):
    """RUP-REPORT-001: selected items that did not complete must block submission."""
    repo = tmp_path / "report_repo"
    repo.mkdir()

    phase = _write_phase_states(
        repo,
        selected_items=["BUG-001"],
        verification_status="passed",
        execution_state={
            "recommendations": [
                {
                    "backlog_item_id": "BUG-001",
                    "subtype": "bug",
                    "disposition": "AGENT_ONLY",
                    "rationale": "Needs human judgment",
                }
            ],
            "dispositions": {"BUG-001": "AGENT_ONLY"},
            "per_item_completion": {"BUG-001": "AGENT_ONLY"},
            "rollback_operations": [],
        },
    )
    report = phase.execute()

    follow_up_ids = {f["id"] for f in report["followups"]}
    assert "BUG-001" in follow_up_ids
    assert report["summary"]["ready_for_submission"] is False


def test_completed_selected_item_does_not_block_readiness(tmp_path):
    """RUP-REPORT-002: completed selected items with passing verification are ready."""
    repo = tmp_path / "report_repo"
    repo.mkdir()

    phase = _write_phase_states(
        repo,
        selected_items=["BUG-001"],
        verification_status="passed",
        execution_state={
            "recommendations": [],
            "dispositions": {},
            "per_item_completion": {"BUG-001": "COMPLETE"},
            "rollback_operations": [],
        },
    )
    report = phase.execute()

    follow_up_ids = {f["id"] for f in report["followups"]}
    assert "BUG-001" not in follow_up_ids
    assert report["summary"]["ready_for_submission"] is True


def test_rollback_commands_quote_hostile_filenames(tmp_path):
    """RUP-REPORT-003: rollback commands must quote filenames containing shell metacharacters."""
    repo = tmp_path / "hostile_repo"
    repo.mkdir()
    paths = RupPaths(repo)
    state = StateManager(paths)

    state.save_json(
        {
            "repo_metadata": {"name": "test"},
            "risk_assessment": {
                "production_readiness_score": 60,
                "technical_debt_score": 40,
            },
        },
        "RUP_DISCOVERY.json",
    )
    state.save_json(
        {
            "backlog": [],
            "selected_items": [],
            "risk_analysis": {},
        },
        "RUP_PLAN.json",
    )
    state.save_json(
        {
            "changes": [
                {
                    "file_path": "$(touch PWNED).py",
                    "change_type": "create",
                    "rationale": "hostile create",
                },
                {
                    "file_path": "foo'; command; echo '.py",
                    "change_type": "modify",
                    "rationale": "hostile modify",
                },
            ],
            "commits": [],
            "local_verification": {},
        },
        "RUP_EXECUTION.json",
    )
    state.save_json(
        {
            "verification_results": {"overall_status": "failed"},
            "metrics": {},
            "audit_trail": [],
        },
        "RUP_VERIFICATION.json",
    )

    builder = ArtifactBuilder(paths, state=state)
    phase = ReportingPhase(repo, StateManager(paths), builder)
    report = phase.execute()

    commands = report["rollback_procedure"]["commands"]
    create_cmd = next(c for c in commands if c.startswith("rm"))
    modify_cmd = next(c for c in commands if c.startswith("git checkout"))

    assert shlex.quote("$(touch PWNED).py") in create_cmd
    assert shlex.quote("foo'; command; echo '.py") in modify_cmd
    assert "rm -f --" in create_cmd
    assert "git checkout --" in modify_cmd


def test_reporting_consumes_execution_state_rollback_operations(tmp_path):
    """RUP-REPORT-005: the report consumes the structured rollback operations as
    the single source of truth instead of reconstructing from raw changes."""
    repo = tmp_path / "rollback_sot_repo"
    repo.mkdir()
    paths = RupPaths(repo)
    state = StateManager(paths)

    state.save_json(
        {
            "repo_metadata": {"name": "test"},
            "risk_assessment": {
                "production_readiness_score": 60,
                "technical_debt_score": 40,
            },
        },
        "RUP_DISCOVERY.json",
    )
    state.save_json({"backlog": [], "selected_items": [], "risk_analysis": {}}, "RUP_PLAN.json")
    # RUP_EXECUTION.json has conflicting raw changes; execution-state.json is
    # authoritative and must win.
    state.save_json(
        {
            "changes": [{"file_path": "WRONG.md", "change_type": "create", "rationale": "stale"}],
            "commits": [],
            "local_verification": {},
        },
        "RUP_EXECUTION.json",
    )
    state.save_json(
        {
            "rollback_operations": [
                {"op": "remove_file", "path": "README.md", "backlog_item_id": "DOCS-001"},
                {"op": "restore_content", "path": "src/app.py", "backlog_item_id": "FIX-002"},
            ],
        },
        "execution-state.json",
    )
    state.save_json(
        {"verification_results": {"overall_status": "passed"}, "metrics": {}, "audit_trail": []},
        "RUP_VERIFICATION.json",
    )

    builder = ArtifactBuilder(paths, state=state)
    phase = ReportingPhase(repo, StateManager(paths), builder)
    report = phase.execute()

    rb = report["rollback_procedure"]
    assert [op["path"] for op in rb["operations"]] == ["README.md", "src/app.py"]
    joined = "\n".join(rb["commands"])
    assert "README.md" in joined and "src/app.py" in joined
    assert "WRONG.md" not in joined
    # Rendered commands are derived from the ops, not raw shell reconstruction.
    assert any(cmd.startswith("rm -f --") for cmd in rb["commands"])
    assert any(cmd.startswith("git checkout --") for cmd in rb["commands"])


def test_reporting_includes_readiness_debt_deltas_and_completed_count(tmp_path):
    """RUP-REPORT-004: final metrics reflect post-execution state and true completion count."""
    repo = tmp_path / "delta_repo"
    repo.mkdir()

    phase = _write_phase_states(
        repo,
        selected_items=["BUG-001"],
        verification_status="passed",
        execution_state={
            "recommendations": [],
            "dispositions": {},
            "per_item_completion": {"BUG-001": "COMPLETE"},
            "rollback_operations": [],
        },
    )
    report = phase.execute()

    metrics = report["metrics"]
    assert "readiness_before" in metrics
    assert "readiness_after" in metrics
    assert "readiness_delta" in metrics
    assert "debt_before" in metrics
    assert "debt_after" in metrics
    assert "debt_delta" in metrics
    assert report["summary"]["total_items_processed"] == 1
    assert "reporting" in report["phases_completed"]


def test_missing_execution_state_blocks_readiness(tmp_path):
    """RUP-REPORT-005: missing execution-state.json makes selected items incomplete."""
    repo = tmp_path / "missing_state_repo"
    repo.mkdir()

    phase = _write_phase_states(
        repo,
        selected_items=["BUG-001"],
        verification_status="passed",
        execution_state=None,
    )
    report = phase.execute()

    assert report["summary"]["ready_for_submission"] is False
    assert any(f["id"] == "BUG-001" and f["reason"] == "incomplete" for f in report["followups"])


def test_escalated_items_block_readiness(tmp_path):
    """RUP-REPORT-006: escalated P0 items must block submission."""
    repo = tmp_path / "escalated_repo"
    repo.mkdir()

    phase = _write_phase_states(
        repo,
        selected_items=[],
        verification_status="passed",
        execution_state={
            "recommendations": [],
            "dispositions": {},
            "per_item_completion": {},
            "rollback_operations": [],
        },
    )
    # Inject an escalated item into the plan state sidecar.
    plan = phase.state_manager.load_json("RUP_PLAN.json")
    plan["backlog"].append({
        "id": "BUG-001",
        "priority": "P0",
        "title": "Big bug",
        "category": "bugs",
        "estimated_effort_minutes": 30,
    })
    phase.state_manager.save_json(plan, "RUP_PLAN.json")

    plan_state = phase.state_manager.load_json("plan-state.json") or {}
    plan_state["selected_for_escalation"] = ["BUG-001"]
    phase.state_manager.save_json(plan_state, "plan-state.json")

    report = phase.execute()

    assert report["summary"]["ready_for_submission"] is False
    assert any(f["id"] == "BUG-001" and f["reason"] == "escalated" for f in report["followups"])
