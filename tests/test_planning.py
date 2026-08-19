"""
Unit tests for the RUP planning phase.

These tests exercise constraint persistence, max-files enforcement, and
risk-tolerance filtering in isolation.
"""
import subprocess
from pathlib import Path

import pytest

from runtime.artifact_builder import ArtifactBuilder
from runtime.paths import RupPaths
from runtime.planning import PlanningPhase
from runtime.state import StateManager


def _make_phase(
    repo_dir: Path,
    gaps: list,
    time_budget: int = 45,
    max_files: int = 20,
    risk_tolerance: str = "medium",
) -> PlanningPhase:
    """Create a PlanningPhase with a synthetic discovery state."""
    repo_dir.mkdir(parents=True, exist_ok=True)
    paths = RupPaths(repo_dir)
    state = StateManager(paths)
    discovery = {
        "repo_metadata": {
            "name": repo_dir.name,
            "primary_language": "python",
            "repo_type": "application",
        },
        "languages": [],
        "tooling": {},
        "gaps": gaps,
        "risk_assessment": {},
    }
    state.save_json(discovery, "RUP_DISCOVERY.json")
    builder = ArtifactBuilder(paths, state=state)
    return PlanningPhase(
        repo_dir,
        state,
        builder,
        time_budget_minutes=time_budget,
        max_files=max_files,
        risk_tolerance=risk_tolerance,
    )


def _gap(
    gid: str,
    severity: str,
    category: str,
    effort: str,
    files: list,
    title: str = "",
) -> dict:
    return {
        "id": gid,
        "severity": severity,
        "category": category,
        "effort_estimate": effort,
        "files_affected": files,
        "title": title or gid,
        "description": "",
        "impact": "",
        "suggested_fix": "",
    }


def test_constraints_persisted_and_rendered(tmp_path):
    """H-03: planning constraints must be persisted and rendered in RUP_PLAN.md."""
    phase = _make_phase(
        tmp_path / "constraints_repo",
        gaps=[_gap("DOCS-001", "medium", "docs", "small", [], "Missing README")],
        time_budget=30,
        max_files=5,
        risk_tolerance="low",
    )
    phase.execute()

    plan_state = phase.state_manager.load_json("plan-state.json")
    assert plan_state["constraints"] == {
        "time_budget_minutes": 30,
        "max_files": 5,
        "risk_tolerance": "low",
    }

    md_path = phase.state_manager.paths.get_state_path("RUP_PLAN.md")
    assert md_path.exists()
    md_text = md_path.read_text(encoding="utf-8")
    assert "30 minutes" in md_text
    assert "**Max Files**: 5" in md_text
    assert "**Risk Tolerance**: low" in md_text


def test_max_files_limits_selection(tmp_path):
    """H-01: max-files must limit the number of files selected for the run."""
    phase = _make_phase(
        tmp_path / "maxfiles_repo",
        gaps=[
            _gap("TEST-001", "high", "tests", "medium", ["a.py", "b.py"]),
            _gap("DOCS-001", "medium", "docs", "small", ["c.py"]),
            _gap("DOCS-002", "medium", "docs", "small", ["d.py"]),
        ],
        time_budget=100,
        max_files=3,
    )
    plan_data = phase.execute()

    selected = set(plan_data["selected_items"])
    assert "TEST-001" in selected
    # Only one of the two one-file docs items should fit after TEST-001.
    assert len(selected) == 2
    assert selected.issubset({"TEST-001", "DOCS-001", "DOCS-002"})


def test_risk_tolerance_filters_selection(tmp_path):
    """H-02: low risk tolerance must exclude medium/high risk items."""
    phase = _make_phase(
        tmp_path / "risk_repo",
        gaps=[
            # P1 + large effort => risk medium
            _gap("TEST-001", "high", "tests", "large", ["tests/"]),
            # P2 + small effort => risk low
            _gap("DOCS-001", "medium", "docs", "small", []),
        ],
        time_budget=100,
        max_files=20,
        risk_tolerance="low",
    )
    plan_data = phase.execute()

    selected = set(plan_data["selected_items"])
    assert "DOCS-001" in selected
    assert "TEST-001" not in selected


def test_plan_output_validates_against_schema(tmp_path):
    """The generated RUP_PLAN.json must validate against the canonical schema."""
    phase = _make_phase(
        tmp_path / "schema_repo",
        gaps=[_gap("DOCS-001", "medium", "docs", "small", [], "Missing README")],
        time_budget=15,
        max_files=2,
        risk_tolerance="high",
    )
    phase.execute()

    script_path = Path(__file__).parent.parent / "scripts" / "validate_rup.py"
    schema_path = Path(__file__).parent.parent / "protocol" / "rup-schema.json"
    result = subprocess.run(
        [
            "python3",
            str(script_path),
            "--schema",
            str(schema_path),
            "output",
            str(phase.state_manager.paths.get_state_path("RUP_PLAN.json")),
            "plan",
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, f"Schema validation failed: {result.stdout} {result.stderr}"


def test_p0_exceeding_max_files_is_escalated(tmp_path):
    """RUP-PLAN-001: P0 items that exceed max-files must escalate, not bypass constraints."""
    phase = _make_phase(
        tmp_path / "p0_maxfiles_repo",
        gaps=[_gap("BUG-001", "critical", "bugs", "small", [f"f{i}.py" for i in range(30)])],
        time_budget=100,
        max_files=5,
        risk_tolerance="low",
    )
    plan_data = phase.execute()
    plan_state = phase.state_manager.load_json("plan-state.json")

    assert "BUG-001" not in plan_data["selected_items"]
    assert "BUG-001" in plan_state.get("selected_for_escalation", [])
    assert plan_state.get("requires_explicit_override") is True


def test_p0_exceeding_time_budget_is_escalated(tmp_path):
    """RUP-PLAN-002: P0 items that exceed time budget must escalate."""
    phase = _make_phase(
        tmp_path / "p0_time_repo",
        gaps=[_gap("BUG-001", "critical", "bugs", "large", ["a.py"])],
        time_budget=10,
        max_files=20,
        risk_tolerance="high",
    )
    plan_data = phase.execute()
    plan_state = phase.state_manager.load_json("plan-state.json")

    assert "BUG-001" not in plan_data["selected_items"]
    assert "BUG-001" in plan_state.get("selected_for_escalation", [])


def test_p0_above_risk_tolerance_is_escalated(tmp_path):
    """RUP-PLAN-003: P0 items above risk tolerance must escalate."""
    phase = _make_phase(
        tmp_path / "p0_risk_repo",
        gaps=[_gap("BUG-001", "critical", "bugs", "large", ["a.py"])],
        time_budget=100,
        max_files=20,
        risk_tolerance="low",
    )
    plan_data = phase.execute()
    plan_state = phase.state_manager.load_json("plan-state.json")

    assert "BUG-001" not in plan_data["selected_items"]
    assert "BUG-001" in plan_state.get("selected_for_escalation", [])


def test_fallback_item_respects_time_budget(tmp_path):
    """RUP-PLAN-004: fallback selection must also respect time budget."""
    phase = _make_phase(
        tmp_path / "fallback_time_repo",
        gaps=[_gap("DOCS-001", "medium", "docs", "large", ["a.py"])],
        time_budget=10,
        max_files=20,
        risk_tolerance="high",
    )
    plan_data = phase.execute()
    plan_state = phase.state_manager.load_json("plan-state.json")

    assert plan_data["selected_items"] == []
    assert plan_state.get("selected_for_escalation", []) == []


def test_dependency_cycle_raises_planning_error(tmp_path):
    """RUP-PLAN-005: cyclic dependencies among selected items must fail planning."""
    from runtime.planning import PlanningError

    phase = _make_phase(
        tmp_path / "cycle_repo",
        gaps=[
            {
                "id": "A-001",
                "severity": "high",
                "category": "ci",
                "effort_estimate": "small",
                "files_affected": [],
                "title": "A",
                "description": "",
                "impact": "",
                "suggested_fix": "",
            },
            {
                "id": "B-001",
                "severity": "high",
                "category": "tests",
                "effort_estimate": "small",
                "files_affected": [],
                "title": "B",
                "description": "",
                "impact": "",
                "suggested_fix": "",
            },
        ],
        time_budget=100,
        max_files=20,
        risk_tolerance="high",
    )
    # Manually inject cyclic dependencies after backlog generation by patching
    # the discovery gaps before execution.
    discovery = phase.state_manager.load_json("RUP_DISCOVERY.json")
    discovery["gaps"][0]["dependencies"] = ["B-001"]
    discovery["gaps"][1]["dependencies"] = ["A-001"]
    phase.state_manager.save_json(discovery, "RUP_DISCOVERY.json")

    with pytest.raises(PlanningError):
        phase.execute()
