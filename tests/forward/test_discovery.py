import json
from pathlib import Path
from runtime.cli import run_discovery
from runtime.state import StateManager
from runtime.paths import RupPaths

def test_discovery_execution(tmp_path):
    """Test that discovery runs end-to-end and creates the required schema-valid artifact."""
    # Setup a mock target directory
    repo_dir = tmp_path / "mock_repo"
    repo_dir.mkdir()
    
    # Add a mock python file to trigger python detection
    (repo_dir / "main.py").write_text("print('hello')")
    (repo_dir / "requirements.txt").write_text("pytest==7.0.0")
    
    # Run the discovery phase CLI
    run_discovery(repo_dir)
    
    # Verify the artifacts were generated in .rup/ directory
    assert (repo_dir / ".rup" / "RUP_DISCOVERY.json").exists()
    assert (repo_dir / ".rup" / "RUP_DISCOVERY.md").exists()
    
    # Load and verify the contents
    paths = RupPaths(repo_dir)
    state = StateManager(paths)
    data = state.load_json("RUP_DISCOVERY.json")
    
    assert data["repo_metadata"]["primary_language"] == "python"
    assert data["repo_metadata"]["name"] == "mock_repo"
    assert data["repo_metadata"]["file_count"] == 2  # main.py and requirements.txt
    assert "pytest" not in data["tooling"] # we didn't add pytest.ini
    
    # Let's ensure the validator script can parse it
    import subprocess
    script_path = Path(__file__).parent.parent.parent / "scripts" / "validate_rup.py"
    schema_path = Path(__file__).parent.parent.parent / "protocol" / "rup-schema.json"
    
    result = subprocess.run([
        "python3", str(script_path), 
        "--schema", str(schema_path),
        "output", str(repo_dir / ".rup" / "RUP_DISCOVERY.json"), "discovery"
    ], capture_output=True, text=True)
    
    assert result.returncode == 0, f"Schema validation failed: {result.stdout} {result.stderr}"
