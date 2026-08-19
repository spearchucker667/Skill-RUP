import subprocess
from pathlib import Path
from runtime.cli import run_discovery, run_plan
from runtime.state import StateManager
from runtime.paths import RupPaths

def test_plan_execution(tmp_path):
    # Setup mock repo
    repo_dir = tmp_path / "mock_repo"
    repo_dir.mkdir()
    (repo_dir / "main.py").write_text("print('hello')")

    # Run discovery first
    run_discovery(repo_dir)

    # Run plan
    run_plan(repo_dir)

    assert (repo_dir / ".rup" / "RUP_PLAN.json").exists()
    assert (repo_dir / ".rup" / "RUP_PLAN.md").exists()

    paths = RupPaths(repo_dir)
    state = StateManager(paths)
    data = state.load_json("RUP_PLAN.json")
    plan_state = state.load_json("plan-state.json")

    assert "backlog" in data
    assert "selected_items" in data
    assert "constraints" in plan_state
    assert plan_state["constraints"]["time_budget_minutes"] == 45
    assert plan_state["constraints"]["max_files"] == 20
    assert plan_state["constraints"]["risk_tolerance"] == "medium"

    md_text = (repo_dir / ".rup" / "RUP_PLAN.md").read_text(encoding="utf-8")
    assert "**Time Budget**: 45 minutes" in md_text

    # Validate against schema
    script_path = Path(__file__).parent.parent.parent / "scripts" / "validate_rup.py"
    schema_path = Path(__file__).parent.parent.parent / "protocol" / "rup-schema.json"

    result = subprocess.run([
        "python3", str(script_path),
        "--schema", str(schema_path),
        "output", str(repo_dir / ".rup" / "RUP_PLAN.json"), "plan"
    ], capture_output=True, text=True)

    assert result.returncode == 0, f"Schema validation failed: {result.stdout} {result.stderr}"


def test_plan_with_custom_constraints(tmp_path):
    """CLI planning flags must be persisted and rendered."""
    repo_dir = tmp_path / "custom_plan_repo"
    repo_dir.mkdir()
    (repo_dir / "main.py").write_text("print('hello')")

    run_discovery(repo_dir)
    run_plan(repo_dir, time_budget=10, max_files=3, risk_tolerance="low")

    paths = RupPaths(repo_dir)
    state = StateManager(paths)
    plan_state = state.load_json("plan-state.json")

    assert plan_state["constraints"] == {
        "time_budget_minutes": 10,
        "max_files": 3,
        "risk_tolerance": "low",
    }

    md_text = (repo_dir / ".rup" / "RUP_PLAN.md").read_text(encoding="utf-8")
    assert "**Time Budget**: 10 minutes" in md_text
    assert "**Max Files**: 3" in md_text
    assert "**Risk Tolerance**: low" in md_text
