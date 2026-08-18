import subprocess
from pathlib import Path
from runtime.cli import run_discovery, run_plan, run_execute
from runtime.state import StateManager
from runtime.paths import RupPaths

def test_execute_execution(tmp_path):
    repo_dir = tmp_path / "mock_repo"
    repo_dir.mkdir()
    (repo_dir / "main.py").write_text("print('hello')")
    
    run_discovery(repo_dir)
    run_plan(repo_dir)
    run_execute(repo_dir)
    
    assert (repo_dir / "RUP_EXECUTION.json").exists()
    assert (repo_dir / "RUP_EXECUTION.md").exists()
    
    script_path = Path(__file__).parent.parent.parent / "scripts" / "validate_rup.py"
    schema_path = Path(__file__).parent.parent.parent / "protocol" / "rup-schema.json"
    
    result = subprocess.run([
        "python3", str(script_path), 
        "--schema", str(schema_path),
        "output", str(repo_dir / "RUP_EXECUTION.json"), "execution"
    ], capture_output=True, text=True)
    
    assert result.returncode == 0, f"Schema validation failed: {result.stdout} {result.stderr}"
