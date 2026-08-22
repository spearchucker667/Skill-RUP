import subprocess
from pathlib import Path
from runtime.cli import run_discovery, run_plan, run_execute, run_verify
from runtime.state import StateManager
from runtime.paths import RupPaths

def test_verify_execution(tmp_path):
    repo_dir = tmp_path / "mock_repo"
    repo_dir.mkdir()
    (repo_dir / "main.py").write_text("print('hello')")

    run_discovery(repo_dir)
    run_plan(repo_dir)
    # Trusted CI harness: opt out of the --sandbox required default.
    run_execute(repo_dir, sandbox="off", override_escalation=True)
    run_verify(repo_dir, sandbox="off")

    assert (repo_dir / ".rup" / "RUP_VERIFICATION.json").exists()
    assert (repo_dir / ".rup" / "RUP_VERIFICATION.md").exists()

    script_path = Path(__file__).parent.parent.parent / "scripts" / "validate_rup.py"
    schema_path = Path(__file__).parent.parent.parent / "protocol" / "rup-schema.json"

    result = subprocess.run([
        "python3", str(script_path),
        "--schema", str(schema_path),
        "output", str(repo_dir / ".rup" / "RUP_VERIFICATION.json"), "verification"
    ], capture_output=True, text=True)

    assert result.returncode == 0, f"Schema validation failed: {result.stdout} {result.stderr}"


def test_verify_run_id_is_preserved_with_resume(tmp_path):
    """RUP-VERIFY-009: run IDs persist across phase-only invocations when --resume is used."""
    repo_dir = tmp_path / "mock_repo"
    repo_dir.mkdir()
    (repo_dir / "main.py").write_text("print('hello')")

    run_discovery(repo_dir)
    discovery_state = StateManager(RupPaths(repo_dir)).load_json("session-state.json")

    run_plan(repo_dir, resume=True)
    run_execute(repo_dir, resume=True, sandbox="off", override_escalation=True)
    run_verify(repo_dir, resume=True, sandbox="off")
    verify_state = StateManager(RupPaths(repo_dir)).load_json("session-state.json")

    assert discovery_state["run_id"] == verify_state["run_id"]
    assert discovery_state["run_id"].startswith("rup-")


def test_verify_run_id_is_unique_without_resume(tmp_path):
    """RUP-VERIFY-010: phase-only invocations without --resume receive distinct run IDs."""
    repo_dir = tmp_path / "mock_repo"
    repo_dir.mkdir()
    (repo_dir / "main.py").write_text("print('hello')")

    run_discovery(repo_dir)
    discovery_state = StateManager(RupPaths(repo_dir)).load_json("session-state.json")

    run_plan(repo_dir)
    run_execute(repo_dir, sandbox="off", override_escalation=True)
    run_verify(repo_dir, sandbox="off")
    verify_state = StateManager(RupPaths(repo_dir)).load_json("session-state.json")

    assert discovery_state["run_id"] != verify_state["run_id"]
