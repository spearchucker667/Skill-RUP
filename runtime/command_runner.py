"""
command_runner module for RUP deterministic runtime.
"""
import os
import subprocess  # nosec B404
from pathlib import Path
from typing import List, Optional, Tuple, Union


# Environment variables allowed to pass through to subprocesses by default.
# The list is intentionally narrow: it preserves tooling and locale essentials
# while stripping host secrets, cloud credentials, and agent-specific state.
_ENV_ALLOWLIST = {
    "PATH",
    "HOME",
    "USER",
    "SHELL",
    "LANG",
    "LC_ALL",
    "LC_CTYPE",
    "LC_MESSAGES",
    "TERM",
    "TERMINFO",
    "TMPDIR",
    "TEMP",
    "TMP",
    "CI",
    "GITHUB_ACTIONS",
    "GITHUB_WORKFLOW",
    "GITHUB_RUN_ID",
    "PYTHONNOUSERSITE",
    "PYTHONDONTWRITEBYTECODE",
    "PYTEST_CURRENT_TEST",
}

DEFAULT_MAX_OUTPUT_BYTES = 5 * 1024 * 1024


def _decode_output(value: Union[str, bytes, None]) -> str:
    """Decode subprocess output safely whether text=True or not."""
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return str(value)


def _scrubbed_env(env: Optional[dict]) -> dict:
    """Return a scrubbed environment dictionary.

    When ``env`` is None, build one from the current environment using the
    allowlist. When ``env`` is provided, trust the caller and return it as-is.
    """
    if env is not None:
        return env
    return {k: v for k, v in os.environ.items() if k in _ENV_ALLOWLIST}


def _truncate(text: str, max_bytes: int) -> str:
    """Truncate a string so its UTF-8 encoding does not exceed ``max_bytes``."""
    encoded = text.encode("utf-8")
    if len(encoded) <= max_bytes:
        return text
    truncated = encoded[:max_bytes]
    # Drop a trailing partial codepoint to stay valid UTF-8.
    while truncated and truncated[-1] & 0xC0 == 0x80:
        truncated = truncated[:-1]
    return truncated.decode("utf-8", errors="ignore") + "\n[output truncated]"


def run_command(
    cmd: List[str],
    cwd: Path,
    timeout: int = 300,
    env: Optional[dict] = None,
    max_output_bytes: int = DEFAULT_MAX_OUTPUT_BYTES,
) -> Tuple[int, str, str]:
    """
    Run a command deterministically and securely.
    - shell=False to prevent injection
    - explicit cwd required
    - timeout enforced
    - environment is scrubbed to an allowlist by default
    - stdout/stderr is capped to max_output_bytes
    """
    if not isinstance(cmd, list):
        raise TypeError("Command must be a list of strings (shell=False requirement).")

    for item in cmd:
        if not isinstance(item, str):
            raise TypeError(f"All command arguments must be strings (got {type(item).__name__}).")

    if not cwd.is_absolute() or not cwd.exists() or not cwd.is_dir():
        raise ValueError(f"Invalid cwd: {cwd}")

    effective_env = _scrubbed_env(env)

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
        stdout = _truncate(result.stdout, max_output_bytes)
        stderr = _truncate(result.stderr, max_output_bytes)
        return result.returncode, stdout, stderr
    except subprocess.TimeoutExpired as e:
        stdout = _truncate(_decode_output(e.stdout), max_output_bytes)
        stderr = _truncate(_decode_output(e.stderr), max_output_bytes)
        return 124, stdout, stderr or f"Command timed out after {timeout}s"
    except FileNotFoundError as e:
        return 127, "", f"Executable not found: {e}"
    except Exception as e:
        return 1, "", str(e)
