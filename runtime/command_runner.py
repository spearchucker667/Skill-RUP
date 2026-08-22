"""
command_runner module for RUP deterministic runtime.

Executes subprocesses with ``shell=False`` and applies the RUP-SEC-002 command
policy: a scrubbed environment allowlist (target code cannot read host
credentials), bounded captured output, and secret redaction of captured
stdout/stderr before they enter runtime artifacts.
"""
import subprocess  # nosec B404
from pathlib import Path
from typing import List, Optional, Tuple, Union

from .redaction import redact_secrets
from .security import scrub_environment

# Default cap on captured stdout/stderr per stream (bytes).
DEFAULT_MAX_OUTPUT_BYTES = 512 * 1024


def _decode_output(value: Union[str, bytes, None]) -> str:
    """Decode subprocess output safely whether text=True or not."""
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return str(value)


def _bound_output(value: str, max_bytes: int) -> str:
    """Truncate captured output at ``max_bytes`` with an explicit marker."""
    encoded = value.encode("utf-8", errors="replace")
    if len(encoded) <= max_bytes:
        return value
    return (
        encoded[:max_bytes].decode("utf-8", errors="replace")
        + f"\n[...truncated at {max_bytes} bytes...]\n"
    )


def run_command(
    cmd: List[str],
    cwd: Path,
    timeout: int = 300,
    env: Optional[dict] = None,
    *,
    scrub_env: bool = True,
    redact_output: bool = True,
    max_output_bytes: int = DEFAULT_MAX_OUTPUT_BYTES,
) -> Tuple[int, str, str]:
    """
    Run a command deterministically and securely.
    - shell=False to prevent injection
    - explicit cwd required
    - timeout enforced
    - scrubbed environment allowlist (RUP-SEC-002)
    - bounded captured output
    - secret-redacted stdout/stderr
    """
    if not isinstance(cmd, list):
        raise TypeError("Command must be a list of strings (shell=False requirement).")

    for item in cmd:
        if not isinstance(item, str):
            raise TypeError(f"All command arguments must be strings (got {type(item).__name__}).")

    if not cwd.is_absolute() or not cwd.exists() or not cwd.is_dir():
        raise ValueError(f"Invalid cwd: {cwd}")

    effective_env = scrub_environment(env) if scrub_env else (dict(env) if env is not None else None)

    try:
        result = subprocess.run(  # nosec B603
            cmd,
            cwd=cwd,
            timeout=timeout,
            capture_output=True,
            text=True,
            shell=False,
            env=effective_env,
        )
        stdout = _bound_output(result.stdout or "", max_output_bytes)
        stderr = _bound_output(result.stderr or "", max_output_bytes)
        if redact_output:
            stdout = redact_secrets(stdout)
            stderr = redact_secrets(stderr)
        return result.returncode, stdout, stderr
    except subprocess.TimeoutExpired as e:
        stdout = _bound_output(_decode_output(e.stdout), max_output_bytes)
        stderr = _bound_output(_decode_output(e.stderr), max_output_bytes)
        if redact_output:
            stdout = redact_secrets(stdout)
            stderr = redact_secrets(stderr)
        return 124, stdout, stderr or f"Command timed out after {timeout}s"
    except FileNotFoundError as e:
        return 127, "", f"Executable not found: {e}"
    except Exception as e:
        return 1, "", str(e)
