"""
Provenance and lineage verification module for RUP deterministic runtime.
"""
import hashlib
import json
from pathlib import Path
from typing import Dict, Any, List, Optional
from .command_runner import run_command

def compute_sha256(file_path: Path) -> str:
    """Compute SHA-256 hash of a file deterministically."""
    h = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()

def compute_git_blob_sha(file_path: Path, cwd: Optional[Path] = None) -> str:
    """Compute Git blob SHA (100% equivalent to git hash-object).

    SHA-1 is used here only to reproduce Git's object identifier for
    provenance/lineage comparison, not for any security purpose.
    """
    try:
        data = file_path.read_bytes()
        header = f"blob {len(data)}\0".encode("ascii")
        return hashlib.sha1(header + data, usedforsecurity=False).hexdigest()
    except Exception:
        if cwd is None:
            cwd = file_path.parent
        rc, stdout, _ = run_command(["git", "hash-object", str(file_path)], cwd=cwd)
        if rc == 0 and stdout.strip():
            return stdout.strip()
        return "UNKNOWN"

class ProvenanceManager:
    def __init__(self, repo_root: Path):
        self.repo_root = repo_root

    def generate_source_manifest(self) -> Dict[str, Any]:
        """Generate a complete source manifest with SHA-256 and Git blob SHAs."""
        manifest_files = []
        for p in sorted(self.repo_root.rglob("*")):
            if not p.is_file():
                continue
            if any(part in p.parts for part in [".git", ".venv", "__pycache__", ".reference", "dist", "build"]):
                continue

            rel = p.relative_to(self.repo_root)
            manifest_files.append({
                "path": str(rel),
                "sha256": compute_sha256(p),
                "git_blob_sha": compute_git_blob_sha(p, cwd=self.repo_root),
                "size_bytes": p.stat().st_size
            })

        return {
            "canonical_repository": "https://github.com/spearchucker667/RUP-Protocol",
            "canonical_commit": "c3d6f70375db15d53db2fba76d70b5b7c9cf98bb",
            "protocol_version": "3.0.0",
            "total_files": len(manifest_files),
            "files": manifest_files
        }

