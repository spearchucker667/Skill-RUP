"""
Security module for RUP deterministic runtime.
Implements adversarial prompt injection defense, path jail enforcement, and safe parsing.
"""
import re
from pathlib import Path
from typing import List, Dict, Any, Iterator, Optional, Set
import yaml
import json

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
    max_bytes: int = MAX_FILE_BYTES,
    skip_parts: Optional[Set[str]] = None,
) -> Iterator[Path]:
    """Yield regular files under ``root`` whose resolved real path stays inside ``root``.

    Symlinks are followed only after the resolved target is confirmed to be
    contained within ``root.resolve()``. Broken symlinks and traversal attempts
    are skipped.
    """
    root_resolved = root.resolve()
    skip_parts = skip_parts or set()

    for entry in root_resolved.rglob("*"):
        try:
            if skip_parts and any(part in entry.parts for part in skip_parts):
                continue
            if entry.is_symlink():
                target = entry.resolve(strict=True)
                enforce_path_jail(root_resolved, target)
            if not entry.is_file():
                continue
            if entry.stat().st_size > max_bytes:
                continue
        except (OSError, ValueError, PermissionError):
            continue
        yield entry


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

