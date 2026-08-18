import subprocess
from pathlib import Path
from runtime.cli import run_discovery, run_plan, run_execute, run_verify, run_report
from runtime.state import StateManager
from runtime.paths import RupPaths

def test_report_execution(tmp_path):
    repo_dir = tmp_path / "mock_repo"
    repo_dir.mkdir()
    (repo_dir / "main.py").write_text("print('hello')")
    
    # Run the full sequence
    run_discovery(repo_dir)
    run_plan(repo_dir)
    run_execute(repo_dir)
    run_verify(repo_dir)
    run_report(repo_dir)
    
    assert (repo_dir / ".rup" / "RUP_FINAL_REPORT.json").exists()
    assert (repo_dir / ".rup" / "RUP_FINAL_REPORT.md").exists()
    
    paths = RupPaths(repo_dir)
    state = StateManager(paths)
    data = state.load_json("RUP_FINAL_REPORT.json")
    
    assert data["summary"]["overall_status"] == "failed"
    assert "discovery" in data["phases_completed"]
    
    # Note: validate_rup.py does not explicitly export a 'report' subcommand type 
    # to test against the schema. Validation logic covers discovery/plan/exec/verify.
    # The presence of the files and correct JSON formatting via StateManager is sufficient.
    pass
