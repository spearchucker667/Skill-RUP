from pathlib import Path
import pytest
from runtime.security import enforce_path_jail

def test_path_jail(tmp_path):
    repo_dir = tmp_path / "mock_repo"
    repo_dir.mkdir()
    
    # Valid
    assert enforce_path_jail(repo_dir, repo_dir / "src/main.py")
    
    # Invalid
    with pytest.raises(PermissionError):
        enforce_path_jail(repo_dir, tmp_path / "mock_repo_evil/src/main.py")
