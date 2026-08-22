"""
Security module for RUP deterministic runtime.
Implements adversarial prompt injection defense, path jail enforcement, jailed
file I/O primitives, sandbox detection, and safe parsing.

The target repository is treated as an untrusted trust domain. Every read and
write of repository content must go through the jailed primitives in this
module so that file or directory symlinks cannot redirect I/O outside the
target (RUP-SEC-001).
"""
import json
import os
import re
import shutil
import tempfile
import warnings
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional, Set, Tuple

import yaml

MAX_FILE_BYTES = 5 * 1024 * 1024
MAX_YAML_ALIASES = 50

PROMPT_INJECTION_PATTERNS = [
    re.compile(r"(?i)\bignore\s+(?:all\s+)?(?:previous|prior)\s+(?:instructions|directives|prompts)\b"),
    re.compile(r"(?i)\bsystem\s+prompt\s+override\b"),
    re.compile(r"(?i)\bdisregard\s+(?:all\s+)?(?:rules|instructions|directives)\b"),
    re.compile(r"(?i)\byou\s+are\s+now\s+(?:unconstrained|in\s+dan\s+mode|unrestricted)\b"),
    re.compile(r"(?i)\bexfiltrate\s+(?:secrets|keys|tokens|passwords)\b"),
    re.compile(r"(?i)\b(?:curl|wget)\s+-[a-zA-Z]*\s*https?://"),
    re.compile(r"(?i)\b(?:eval|exec)\s*\(\s*(?:base64_decode|atob|Buffer\.from)\b"),
    re.compile(r"(?i)\b(?:cat\s+/etc/(?:passwd|shadow)|printenv\s*>)\b"),
]

# Environment variables preserved when scrubbing the subprocess environment
# (RUP-SEC-002). Everything else -- including credentials, tokens, and CI
# secrets -- is dropped before target-controlled commands execute.
_ENV_ALLOWLIST = {
    "PATH",
    "HOME",
    "USERPROFILE",
    "TEMP",
    "TMP",
    "SystemRoot",
    "SystemDrive",
    "ComSpec",
    "ProgramFiles",
    "ProgramFiles(X86)",
    "ProgramData",
    "ALLUSERSPROFILE",
    "OS",
    "LANG",
    "LC_ALL",
    "LC_CTYPE",
    "LC_MESSAGES",
    "NUMBER_OF_PROCESSORS",
    "PROCESSOR_ARCHITECTURE",
    "PROCESSOR_IDENTIFIER",
    "PROCESSOR_LEVEL",
    "PROCESSOR_REVISION",
}

# Prefix allowlists for benign configuration. These never carry credentials and
# are required for npm/pnpm/yarn to function in CI environments and for Pulumi
# local-file-backend passphrase handling (PULUMI_CONFIG_PASSPHRASE) without
# exposing cloud access tokens (PULUMI_ACCESS_TOKEN).
_ENV_PREFIX_ALLOWLIST = ("NPM_CONFIG_", "YARN_", "PNPM_", "COREPACK_", "PULUMI_CONFIG_")


class LimitedAliasLoader(yaml.SafeLoader):
    """SafeLoader with alias expansion limits to prevent YAML bombs."""
    def __init__(self, stream):
        super().__init__(stream)
        self._alias_count = 0

    def compose_node(self, parent, index):
        if self.check_event(yaml.AliasEvent):
            self._alias_count += 1
            if self._alias_count > MAX_YAML_ALIASES:
                raise yaml.YAMLError(f"YAML aliases exceed limit ({MAX_YAML_ALIASES}).")
        return super().compose_node(parent, index)


def enforce_path_jail(root: Path, target: Path) -> Path:
    """Ensure target path is within root, resolving symlinks safely."""
    resolved_root = root.resolve()
    resolved_target = target.resolve()
    try:
        resolved_target.relative_to(resolved_root)
    except ValueError:
        raise PermissionError(f"Path traversal detected: {target} escapes {root}")
    return resolved_target


def iter_jailed_files(
    root: Path,
    skip_dirnames: Optional[Set[str]] = None,
) -> Iterator[Path]:
    """Yield regular files under ``root`` whose resolved real path stays inside it.

    - Symbolic links to files outside ``root`` (or to non-files) are never
      yielded; a warning is emitted so the omission is visible.
    - Symbolic links whose target resolves inside ``root`` are yielded as their
      resolved target path, so the walker never reads through a link.
    - Symbolic-linked directories are never traversed (directory symlinks are
      out of scope and rejected conservatively).
    - Files are deduplicated by resolved path so a file reachable through both
      a link and its real path is yielded once.
    """
    resolved_root = root.resolve()
    seen: Set[Path] = set()
    for dirpath, dirnames, filenames in os.walk(resolved_root, followlinks=False):
        dirpath = Path(dirpath)
        dirnames[:] = [
            d
            for d in dirnames
            if not (dirpath / d).is_symlink()
            and (skip_dirnames is None or d not in skip_dirnames)
        ]
        for fname in filenames:
            candidate = dirpath / fname
            try:
                if candidate.is_symlink():
                    resolved = candidate.resolve(strict=True)
                    enforce_path_jail(resolved_root, resolved)
                    if not resolved.is_file():
                        continue
                    candidate = resolved
                if candidate in seen:
                    continue
                seen.add(candidate)
                yield candidate
            except (PermissionError, OSError) as e:
                warnings.warn(
                    f"Skipping path outside jail or unreadable: {candidate} ({e})",
                    RuntimeWarning,
                    stacklevel=2,
                )
                continue


def open_jailed_read(
    root: Path,
    target: Path,
    mode: str = "r",
    encoding: Optional[str] = None,
    errors: Optional[str] = None,
):
    """Open ``target`` for reading only if it resolves inside ``root``.

    Raises :class:`PermissionError` when the final path or any parent component
    is a symlink escaping ``root``.
    """
    resolved_root = root.resolve()
    resolved = target.resolve()
    try:
        resolved.relative_to(resolved_root)
    except ValueError:
        raise PermissionError(f"Path traversal detected: {target} escapes {root}")
    if not resolved.is_file():
        raise FileNotFoundError(f"Not a regular file inside jail: {target}")
    return open(resolved, mode, encoding=encoding, errors=errors)


def read_jailed_text(
    root: Path,
    target: Path,
    encoding: str = "utf-8",
    errors: str = "ignore",
    max_bytes: Optional[int] = None,
) -> str:
    """Read a repository file as text through the jailed reader."""
    with open_jailed_read(root, target, encoding=encoding, errors=errors) as f:
        content = f.read()
    if max_bytes is not None and len(content.encode("utf-8")) > max_bytes:
        raise ValueError(f"File too large: {target}")
    return content


def atomic_jailed_write(root: Path, target: Path, content: str, encoding: str = "utf-8") -> None:
    """Atomically write ``content`` to ``target``, refusing symlink escapes.

    The parent chain is resolved and verified against ``root``, and writing
    *through* an existing symlink at the final path is refused outright. The
    write itself is atomic (tempfile + ``os.replace``) in the resolved parent
    directory.
    """
    resolved_root = root.resolve()
    if target.is_symlink():
        raise PermissionError(f"Refusing to write through symlink: {target}")

    resolved_parent = target.parent.resolve()
    try:
        resolved_parent.relative_to(resolved_root)
    except ValueError:
        raise PermissionError(f"Path traversal detected: {target} escapes {root}")

    final = resolved_parent / target.name
    if final.is_symlink():
        raise PermissionError(f"Refusing to write through symlink: {final}")

    final.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_path = tempfile.mkstemp(dir=final.parent, prefix=".rup_w_", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding=encoding) as f:
            f.write(content)
        os.replace(temp_path, final)
    except Exception:
        if os.path.exists(temp_path):
            os.unlink(temp_path)
        raise


def jailed_mkdir(
    root: Path,
    target: Path,
    parents: bool = True,
    exist_ok: bool = True,
) -> None:
    """Create a directory inside ``root``, refusing symlink escapes."""
    resolved_root = root.resolve()
    resolved = target.resolve()
    try:
        resolved.relative_to(resolved_root)
    except ValueError:
        raise PermissionError(f"Path traversal detected: {target} escapes {root}")
    resolved.mkdir(parents=parents, exist_ok=exist_ok)


def jailed_unlink(root: Path, target: Path) -> None:
    """Remove ``target`` only when it resolves inside ``root``.

    Symlinks pointing outside the jail are refused (removing a link through a
    redirected parent would delete an external file).
    """
    resolved_root = root.resolve()
    if not target.exists() and not target.is_symlink():
        return
    resolved = target.resolve()
    try:
        resolved.relative_to(resolved_root)
    except ValueError:
        raise PermissionError(f"Path traversal detected: {target} escapes {root}")
    target.unlink()


def safe_load_yaml(file_path: Path, max_bytes: int = MAX_FILE_BYTES):
    """Load YAML with file size and alias expansion guardrails."""
    if file_path.stat().st_size > max_bytes:
        raise ValueError(f"File too large: {file_path}")
    with open(file_path, "r", encoding="utf-8") as f:
        # LimitedAliasLoader inherits from yaml.SafeLoader and prevents both
        # arbitrary object construction and YAML alias bombs.
        return yaml.load(f, Loader=LimitedAliasLoader)  # nosec B506


def safe_load_json(file_path: Path, max_bytes: int = MAX_FILE_BYTES) -> Any:
    """Load JSON with file size guardrails."""
    if file_path.stat().st_size > max_bytes:
        raise ValueError(f"File too large: {file_path}")
    with open(file_path, "r", encoding="utf-8") as f:
        return json.load(f)


def check_prompt_injection(content: str) -> bool:
    """Check for adversarial prompt injection patterns."""
    for pattern in PROMPT_INJECTION_PATTERNS:
        if pattern.search(content):
            return True
    return False


def scan_content_for_threats(content: str) -> List[Dict[str, Any]]:
    """Scan content and return structured list of detected adversarial patterns."""
    threats = []
    for pattern in PROMPT_INJECTION_PATTERNS:
        for match in pattern.finditer(content):
            start = match.start()
            line_num = content[:start].count('\n') + 1
            threats.append({
                "type": "Prompt Injection / Adversarial Instruction",
                "severity": "critical",
                "line": line_num,
                "pattern": pattern.pattern
            })
    return threats


def scan_repository_for_threats(root: Path) -> List[Dict[str, Any]]:
    """Scan a repository tree for adversarial instruction patterns (RUP-SEC-002).

    Uses the jailed walker so symlinked external files are never read. The
    result feeds the pre-execution trust gate: target-controlled commands must
    not run before this scan completes.
    """
    findings: List[Dict[str, Any]] = []
    for p in iter_jailed_files(root):
        try:
            content = read_jailed_text(root, p)
        except (OSError, PermissionError, ValueError) as e:
            warnings.warn(
                f"Threat scan could not read {p}: {e}", RuntimeWarning, stacklevel=2
            )
            continue
        for threat in scan_content_for_threats(content):
            threat["file"] = str(p)
            findings.append(threat)
    return findings


def scrub_environment(env: Optional[Dict[str, str]]) -> Dict[str, str]:
    """Return a scrubbed environment containing only allowlisted variables.

    Used before executing target-controlled commands so repository code cannot
    read host credentials or CI secrets (RUP-SEC-002).
    """
    base = dict(os.environ) if env is None else dict(env)
    scrubbed: Dict[str, str] = {}
    for key, value in base.items():
        upper = key.upper()
        if (
            key in _ENV_ALLOWLIST
            or upper in _ENV_ALLOWLIST
            or key.startswith(_ENV_PREFIX_ALLOWLIST)
            or upper.startswith(_ENV_PREFIX_ALLOWLIST)
        ):
            scrubbed[key] = value
    return scrubbed


def detect_sandbox() -> bool:
    """Heuristically detect whether the runtime is inside a sandbox/container.

    Returns True when any of these hold:

    - ``RUP_SANDBOXED`` is set to a truthy value,
    - a container marker file (Docker/Podman) is present,
    - ``bwrap`` or ``firejail`` is available on PATH.

    This is deliberately conservative: an undetected sandbox refuses execution
    gates under ``--sandbox required`` rather than silently proceeding.
    """
    if os.getenv("RUP_SANDBOXED", "").lower() in ("1", "true", "yes", "on"):
        return True
    for marker in ("/.dockerenv", "/run/.containerenv"):
        if Path(marker).exists():
            return True
    for tool in ("bwrap", "firejail"):
        if shutil.which(tool) is not None:
            return True
    return False


def execution_gate_status(
    allow_exec: bool,
    sandbox: str,
    threat_findings: List[Dict[str, Any]],
) -> Tuple[bool, Optional[str]]:
    """Decide whether target-controlled commands may execute.

    Returns ``(allowed, reason)``. A refusal is always accompanied by a
    human-readable reason suitable for the CLI, verification audit trail, and
    execution state.

    - Adversarial content blocks execution unless ``--allow-exec`` is supplied.
    - ``--sandbox required`` blocks execution when no sandbox is detected.
    - ``--sandbox preferred`` proceeds with a warning when no sandbox is
      detected.
    - ``--sandbox off`` proceeds without a sandbox check (trusted environments).
    """
    if threat_findings and not allow_exec:
        return (
            False,
            "Adversarial instruction patterns detected in target content; "
            "refusing to execute target-controlled commands (use --allow-exec to override).",
        )
    if sandbox == "required" and not detect_sandbox():
        return (
            False,
            "No sandbox detected and --sandbox required; refusing to execute "
            "target-controlled commands (run inside a sandbox or use --sandbox off).",
        )
    if sandbox == "preferred" and not detect_sandbox():
        return (
            True,
            "No sandbox detected (--sandbox preferred); executing target-controlled "
            "commands without isolation.",
        )
    return True, None
