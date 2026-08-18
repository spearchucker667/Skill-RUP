"""
command_runner module for RUP deterministic runtime.
"""
import subprocess  # nosec B404
from pathlib import Path
from typing import List, Optional, Tuple, Union


def _decode_output(value: Union[str, bytes, None]) -> str:
    """Decode subprocess output safely whether text=True or not."""
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return str(value)


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

    for item in cmd:
        if not isinstance(item, str):
            raise TypeError(f"All command arguments must be strings (got {type(item).__name__}).")

    if not cwd.is_absolute() or not cwd.exists() or not cwd.is_dir():
        raise ValueError(f"Invalid cwd: {cwd}")

    try:
        result = subprocess.run(  # nosec B603
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
        stdout = _decode_output(e.stdout)
        stderr = _decode_output(e.stderr)
        return 124, stdout, stderr or f"Command timed out after {timeout}s"
    except FileNotFoundError as e:
        return 127, "", f"Executable not found: {e}"
    except Exception as e:
        return 1, "", str(e)
