"""
Secret scanning and deterministic redaction for RUP runtime.
"""
import re
from pathlib import Path
from typing import List, Dict, Any, Tuple

SECRET_PATTERNS: List[Tuple[str, str, re.Pattern]] = [
    ("AWS Access Key", "high", re.compile(r"\b(AKIA|ASIA)[0-9A-Z]{16}\b")),
    ("GitHub Personal Access Token", "critical", re.compile(r"\b(ghp_[0-9a-zA-Z]{36}|github_pat_[0-9a-zA-Z_]{82})\b")),
    ("GitLab Personal Access Token", "critical", re.compile(r"\bglpat-[0-9A-Za-z_\-]{20}\b")),
    ("npm Access Token", "high", re.compile(r"\bnpm_[0-9a-zA-Z]{36}\b")),
    ("PyPI Upload Token", "high", re.compile(r"\bpypi-AgEIcHlwaS5vcmc[A-Za-z0-9_\-]{50,}\b")),
    ("Stripe Live Secret Key", "critical", re.compile(r"\b(sk|rk)_live_[0-9a-zA-Z]{24,}\b")),
    ("Google API Key", "high", re.compile(r"\bAIza[0-9A-Za-z_\-]{35}\b")),
    ("Private Key", "critical", re.compile(r"-----BEGIN (?:RSA |EC |DSA |OPENSSH |PGP )?PRIVATE KEY-----")),
    ("Generic Secret Assignment", "medium", re.compile(r"(?i)(api[_-]?key|secret|password|access[_-]?token|auth[_-]?token)\s*[:=]\s*['\"]([a-zA-Z0-9_\-\.]{16,})['\"]")),
    ("JSON Web Token", "medium", re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b")),
    ("Slack Token", "high", re.compile(r"\bxox[baprs]-[0-9]{12}-[0-9]{12}-[a-zA-Z0-9]{24}\b")),
    ("Generic High-Entropy Hex String", "low", re.compile(r"(?i)(?:api_key|token|secret)['\"]?\s*[:=]\s*['\"]([0-9a-f]{32,64})['\"]")),
]

def scan_secrets(content: str) -> List[Dict[str, Any]]:
    """Scan string content for exposed secrets."""
    findings = []
    for name, severity, pattern in SECRET_PATTERNS:
        for match in pattern.finditer(content):
            start, end = match.span()
            # Calculate line number
            line_num = content[:start].count('\n') + 1
            snippet = content[max(0, start - 10):min(len(content), end + 10)]
            findings.append({
                "type": name,
                "severity": severity,
                "line": line_num,
                "matched_sample": f"{snippet[:6]}...[REDACTED]"
            })
    return findings

def redact_secrets(content: str, mask: str = "[REDACTED]") -> str:
    """Deterministically redact all known secret patterns from string content."""
    redacted = content
    for _, _, pattern in SECRET_PATTERNS:
        redacted = pattern.sub(mask, redacted)
    return redacted

def scan_file_for_secrets_status(
    file_path: Path, max_bytes: int = 1024 * 1024
) -> Tuple[List[Dict[str, Any]], str]:
    """Scan one file and report a per-file status alongside findings.

    Status is one of:
      - "scanned"  : content read and scanned
      - "too_large": skipped because the file exceeds ``max_bytes``
      - "error"    : could not be read/scanned
      - "missing"  : path does not exist or is not a regular file

    The caller must never treat an empty finding list as ``clean`` when the
    status is not "scanned" (audit P1-20: fail closed, not silent).
    """
    if not file_path.exists() or not file_path.is_file():
        return [], "missing"
    try:
        if file_path.stat().st_size > max_bytes:
            return [], "too_large"
        content = file_path.read_text(encoding="utf-8", errors="ignore")
        findings = scan_secrets(content)
        for f in findings:
            f["file"] = str(file_path)
        return findings, "scanned"
    except Exception:
        return [], "error"


def scan_file_for_secrets(file_path: Path, max_bytes: int = 1024 * 1024) -> List[Dict[str, Any]]:
    """Scan a local file for secret patterns safely (backwards-compatible).

    Returns findings only; for structured coverage status use
    :func:`scan_file_for_secrets_status`.
    """
    findings, _ = scan_file_for_secrets_status(file_path, max_bytes=max_bytes)
    return findings

