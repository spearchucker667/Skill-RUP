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
    
    assert (repo_dir / "RUP_PLAN.json").exists()
    assert (repo_dir / "RUP_PLAN.md").exists()
    
    paths = RupPaths(repo_dir)
    state = StateManager(paths)
    data = state.load_json("RUP_PLAN.json")
    
    assert "backlog" in data
    assert "selected_items" in data
    
    # Validate against schema
    script_path = Path(__file__).parent.parent.parent / "scripts" / "validate_rup.py"
    schema_path = Path(__file__).parent.parent.parent / "protocol" / "rup-schema.json"
    
    result = subprocess.run([
        "python3", str(script_path), 
        "--schema", str(schema_path),
        "output", str(repo_dir / "RUP_PLAN.json"), "plan"
    ], capture_output=True, text=True)
    
    assert result.returncode == 0, f"Schema validation failed: {result.stdout} {result.stderr}"
