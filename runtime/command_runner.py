"""
command_runner module for RUP deterministic runtime.
"""
import subprocess
from pathlib import Path
from typing import List, Optional, Tuple

def run_command(
    cmd: List[str], 
    cwd: Path, 
    timeout: int = 300, 
    env: Optional[dict] = None
) -> Tuple[int, str, str]:
    """
    Run a command deterministically and securely.
    - shell=False to prevent injection
    - explicit cwd required
    - timeout enforced
    """
    if not isinstance(cmd, list):
        raise TypeError("Command must be a list of strings (shell=False requirement).")
    
    if not cwd.is_absolute() or not cwd.exists() or not cwd.is_dir():
        raise ValueError(f"Invalid cwd: {cwd}")
        
    try:
        result = subprocess.run(
            cmd,
            cwd=cwd,
            timeout=timeout,
            capture_output=True,
            text=True,
            shell=False,
            env=env
        )
        return result.returncode, result.stdout, result.stderr
    except subprocess.TimeoutExpired as e:
        return 124, e.stdout.decode() if e.stdout else "", f"Command timed out after {timeout}s"
    except Exception as e:
        return 1, "", str(e)
