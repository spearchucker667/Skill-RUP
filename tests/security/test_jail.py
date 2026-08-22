import os
from pathlib import Path
import pytest
from runtime.security import enforce_path_jail, scrub_environment

def test_path_jail(tmp_path):
    repo_dir = tmp_path / "mock_repo"
    repo_dir.mkdir()
    
    # Valid
    assert enforce_path_jail(repo_dir, repo_dir / "src/main.py")
    
    # Invalid
    with pytest.raises(PermissionError):
        enforce_path_jail(repo_dir, tmp_path / "mock_repo_evil/src/main.py")


def test_scrub_environment_allows_pulumi_config_not_access_tokens():
    """RUP-SEC-002: Pulumi local-backend config passes through; cloud tokens do not."""
    env = {
        "PATH": "/usr/bin",
        "PULUMI_CONFIG_PASSPHRASE": "",
        "PULUMI_ACCESS_TOKEN": "secret",
    }
    scrubbed = scrub_environment(env)
    assert "PATH" in scrubbed
    assert "PULUMI_CONFIG_PASSPHRASE" in scrubbed
    assert "PULUMI_ACCESS_TOKEN" not in scrubbed
