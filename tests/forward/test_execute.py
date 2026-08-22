import subprocess
from pathlib import Path
from runtime.cli import run_discovery, run_plan, run_execute, run_rollback
from runtime.state import StateManager
from runtime.paths import RupPaths

def test_cli_rollback_removes_executed_changes(tmp_path):
    """RUP-EXEC-004: the rollback CLI applies the structured operations end-to-end."""
    repo_dir = tmp_path / "rollback_mock_repo"
    repo_dir.mkdir()
    (repo_dir / "main.py").write_text("print('hello')\n")
    subprocess.run(["git", "init", "--quiet", str(repo_dir)], check=True, capture_output=True)
    subprocess.run(
        ["git", "-C", str(repo_dir), "-c", "user.email=t@t", "-c", "user.name=t", "add", "."],
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "-C", str(repo_dir), "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-m", "init", "--quiet"],
        check=True,
        capture_output=True,
    )

    run_discovery(repo_dir)
    run_plan(repo_dir)
    run_execute(repo_dir, sandbox="off", override_escalation=True)

    created_before = {
        p.relative_to(repo_dir).as_posix()
        for p in repo_dir.rglob("*")
        if p.is_file() and ".rup" not in p.parts
    }
    assert "README.md" in created_before

    rc = run_rollback(repo_dir)
    assert rc == 0

    created_after = {
        p.relative_to(repo_dir).as_posix()
        for p in repo_dir.rglob("*")
        if p.is_file() and ".rup" not in p.parts
    }
    # Every file RUP created is gone; user files (main.py) remain.
    assert "README.md" not in created_after
    assert "main.py" in created_after

    # Second rollback is a no-op.
    assert run_rollback(repo_dir) == 0


def test_execute_execution(tmp_path):
    repo_dir = tmp_path / "mock_repo"
    repo_dir.mkdir()
    (repo_dir / "main.py").write_text("print('hello')")
    
    run_discovery(repo_dir)
    run_plan(repo_dir)
    # Trusted CI harness: opt out of the --sandbox required default.
    run_execute(repo_dir, sandbox="off", override_escalation=True)
    
    assert (repo_dir / ".rup" / "RUP_EXECUTION.json").exists()
    assert (repo_dir / ".rup" / "RUP_EXECUTION.md").exists()
    
    script_path = Path(__file__).parent.parent.parent / "scripts" / "validate_rup.py"
    schema_path = Path(__file__).parent.parent.parent / "protocol" / "rup-schema.json"
    
    result = subprocess.run([
        "python3", str(script_path), 
        "--schema", str(schema_path),
        "output", str(repo_dir / ".rup" / "RUP_EXECUTION.json"), "execution"
    ], capture_output=True, text=True)
    
    assert result.returncode == 0, f"Schema validation failed: {result.stdout} {result.stderr}"
