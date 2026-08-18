"""
Provenance and lineage verification module for the RUP deterministic runtime.

This module is responsible for proving that the Skill-RUP downstream artifacts
originate from the pinned upstream RUP-Protocol commit.  It can:

* Compute SHA-256 and Git blob hashes for local files.
* Reconstruct the upstream canonical source tree (from a local checkout or by
  cloning the canonical repository at the pinned commit).
* Build a ``canonical-source-manifest.json`` that maps every upstream path/blob
  to its local destination path (if any).
* Build a ``transfer-manifest.json`` that records how each upstream source was
  transferred (exact copy, derived, translated, or omitted), the transformation
  tool used, destination hashes, parity tests, and rationale.
* Verify a transfer manifest by reconstructing the upstream tree and comparing
  recorded destination hashes to freshly-computed hashes.
"""
import hashlib
import json
import tempfile
import warnings
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .command_runner import run_command
from .source_authority import SOURCE_AUTHORITY

CANONICAL_RUP_REPO = SOURCE_AUTHORITY["canonical_repo"]
CANONICAL_RUP_COMMIT = SOURCE_AUTHORITY["canonical_commit"]
CANONICAL_PROTOCOL_VERSION = SOURCE_AUTHORITY["canonical_version"]

# Upstream RUP-Protocol paths that were copied or adapted into Skill-RUP.
# Keys are paths relative to the upstream repository root; values are the
# corresponding paths relative to the Skill-RUP repository root.
UPSTREAM_TO_LOCAL_MAP: Dict[str, str] = {
    "rup-protocol.yaml": "protocol/rup-protocol.yaml",
    "rup-schema.json": "protocol/rup-schema.json",
    "legacy/rup-protocol-v2.1.yaml": "protocol/legacy/rup-protocol-v2.1.yaml",
    "legacy/rup-protocol-v3.0.yaml": "protocol/legacy/rup-protocol-v3.0.yaml",
    "legacy/README.md": "protocol/legacy/README.md",
    "examples/discovery_output.json": "examples/discovery_output.json",
    "examples/execution_output.json": "examples/execution_output.json",
    "examples/plan_output.json": "examples/plan_output.json",
    "examples/verification_output.json": "examples/verification_output.json",
    "examples/README.md": "examples/README.md",
    "examples/rup_mock_walkthrough.md": "examples/rup_mock_walkthrough.md",
    "examples/mock_scenario_summary.json": "examples/mock_scenario_summary.json",
}

# Overrides for upstream files that are intentionally not verbatim copies.
# Each entry provides the transfer classification, the transformation that was
# applied, a human-readable rationale, and the tests that demonstrate parity
# with the canonical source intent.
_TRANSFER_OVERRIDES: Dict[str, Dict[str, Any]] = {
    "examples/verification_output.json": {
        "transfer_type": "derived",
        "transformation_tool": "manual/schema alignment",
        "rationale": (
            "Extended locally to include the prompt_injection_scan security gate "
            "and additional audit-trail metadata required by Skill-RUP's "
            "verification output schema while preserving the canonical example "
            "shape."
        ),
        "parity_tests": [
            "tests/test_verification.py::test_prompt_injection_scan_separate_from_sast",
            "tests/forward/test_verify.py::test_verify_execution",
        ],
    },
}

# Default parity tests for exact-copy transfers.
_DEFAULT_PARITY_TESTS: Dict[str, List[str]] = {
    "rup-protocol.yaml": [
        "tests/test_validator_cli.py::test_canonical_invocation_all",
    ],
    "rup-schema.json": [
        "tests/test_validator_cli.py::test_canonical_invocation_all",
    ],
    "legacy/rup-protocol-v2.1.yaml": [],
    "legacy/rup-protocol-v3.0.yaml": [],
    "legacy/README.md": [],
    "examples/discovery_output.json": [
        "tests/forward/test_discovery.py::test_discovery_execution",
    ],
    "examples/execution_output.json": [
        "tests/forward/test_execute.py::test_execute_execution",
    ],
    "examples/plan_output.json": [
        "tests/forward/test_plan.py::test_plan_execution",
    ],
    "examples/verification_output.json": [
        "tests/forward/test_verify.py::test_verify_execution",
    ],
    "examples/README.md": [],
    "examples/rup_mock_walkthrough.md": [],
    "examples/mock_scenario_summary.json": [],
}


def compute_sha256(file_path: Path) -> str:
    """Compute SHA-256 hash of a file deterministically."""
    h = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def compute_git_blob_sha(file_path: Path, cwd: Optional[Path] = None) -> str:
    """Compute Git blob SHA (100%% equivalent to ``git hash-object``).

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


def clone_upstream_commit(
    repo_url: str,
    commit: str,
    dest_dir: Path,
) -> Path:
    """Clone ``repo_url`` at ``commit`` into ``dest_dir`` and return ``dest_dir``.

    Performs a shallow fetch of the exact pinned commit and checks it out.
    The destination directory must already exist and be empty.
    """
    dest_dir = dest_dir.resolve()
    if not dest_dir.exists():
        dest_dir.mkdir(parents=True)
    if any(dest_dir.iterdir()):
        raise ValueError(f"Destination directory is not empty: {dest_dir}")

    for cmd in (
        ["git", "init"],
        ["git", "remote", "add", "origin", repo_url],
        ["git", "fetch", "--depth", "1", "origin", commit],
        ["git", "checkout", "FETCH_HEAD"],
    ):
        rc, stdout, stderr = run_command(cmd, cwd=dest_dir)
        if rc != 0:
            raise RuntimeError(
                f"Git command failed while cloning upstream: {' '.join(cmd)}\n"
                f"stdout: {stdout}\nstderr: {stderr}"
            )

    rc, head, _ = run_command(["git", "rev-parse", "HEAD"], cwd=dest_dir)
    if rc != 0 or head.strip() != commit:
        raise RuntimeError(
            f"Upstream checkout did not produce expected commit: {commit}"
        )

    return dest_dir


def enumerate_git_tree(repo_path: Path, ref: str = "HEAD") -> List[Dict[str, Any]]:
    """Return a sorted list of blob entries for ``ref`` in the git repo at ``repo_path``.

    Each entry is a dict with ``mode``, ``type``, ``sha`` (git blob SHA),
    ``size_bytes``, and ``path`` (relative to repo root).
    """
    repo_path = repo_path.resolve()
    rc, stdout, stderr = run_command(
        ["git", "ls-tree", "-r", "-l", "-z", ref],
        cwd=repo_path,
    )
    if rc != 0:
        raise RuntimeError(f"git ls-tree failed: {stderr}")

    entries: List[Dict[str, Any]] = []
    if not stdout:
        return entries

    # git ls-tree -l -z emits records separated by NUL.  Each record is:
    # "<mode> <type> <sha>\t<size>\t<path>"
    for record in stdout.split("\0"):
        if not record:
            continue
        meta, size_path = record.split("\t", 1)
        size_str, path = size_path.split("\t", 1)
        mode, obj_type, sha = meta.split(" ", 2)
        try:
            size = int(size_str)
        except ValueError:
            size = -1
        entries.append(
            {
                "mode": mode,
                "type": obj_type,
                "sha": sha,
                "size_bytes": size,
                "path": path,
            }
        )

    entries.sort(key=lambda e: e["path"])
    return entries


def _read_upstream_file(upstream_dir: Path, path: str) -> bytes:
    """Read a file from the upstream checkout, guarding against traversal."""
    upstream_dir = upstream_dir.resolve()
    target = (upstream_dir / path).resolve()
    # Ensure the resolved path is still inside the upstream checkout.
    target.relative_to(upstream_dir)
    return target.read_bytes()


def build_canonical_source_manifest(
    skill_root: Path,
    upstream_dir: Path,
    canonical_commit: str = CANONICAL_RUP_COMMIT,
) -> Dict[str, Any]:
    """Build the canonical-source manifest.

    The manifest enumerates every blob in the pinned upstream repository tree
    and records the upstream git blob SHA, SHA-256, size, and the local
    destination path (if the file was transferred into Skill-RUP).
    """
    skill_root = skill_root.resolve()
    upstream_dir = upstream_dir.resolve()

    rc, head, _ = run_command(["git", "rev-parse", "HEAD"], cwd=upstream_dir)
    if rc != 0 or head.strip() != canonical_commit:
        warnings.warn(
            f"Upstream HEAD ({head.strip()}) does not match canonical commit "
            f"({canonical_commit}); using the requested checkout anyway.",
            RuntimeWarning,
        )

    tree = enumerate_git_tree(upstream_dir)
    files: List[Dict[str, Any]] = []

    for entry in tree:
        path = entry["path"]
        data = _read_upstream_file(upstream_dir, path)
        source_sha256 = hashlib.sha256(data).hexdigest()
        destination_path = UPSTREAM_TO_LOCAL_MAP.get(path)

        record: Dict[str, Any] = {
            "source_path": path,
            "source_git_blob_sha": entry["sha"],
            "source_sha256": source_sha256,
            "size_bytes": entry["size_bytes"],
            "destination_path": destination_path,
        }
        files.append(record)

    return {
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "canonical_repository": CANONICAL_RUP_REPO,
        "canonical_commit": canonical_commit,
        "canonical_protocol_version": CANONICAL_PROTOCOL_VERSION,
        "source_root": str(upstream_dir),
        "total_files": len(files),
        "files": files,
    }


def build_transfer_manifest(
    skill_root: Path,
    canonical_manifest: Dict[str, Any],
) -> Dict[str, Any]:
    """Build the transfer manifest from a canonical-source manifest.

    For every upstream file the manifest records whether and how the content
    arrived in the Skill-RUP repository, including destination hashes and the
    rationale for any transformation or omission.
    """
    skill_root = skill_root.resolve()
    transfers: List[Dict[str, Any]] = []

    for entry in canonical_manifest["files"]:
        source_path = entry["source_path"]
        destination_path = entry.get("destination_path")
        record: Dict[str, Any] = {
            "source_path": source_path,
            "source_git_blob_sha": entry["source_git_blob_sha"],
            "source_sha256": entry["source_sha256"],
        }

        if destination_path is None:
            record.update(
                {
                    "destination_path": None,
                    "transfer_type": "omitted",
                    "transformation_tool": None,
                    "destination_sha256": None,
                    "destination_git_blob_sha": None,
                    "parity_tests": [],
                    "rationale": "Not used as an authoritative source in the Skill-RUP downstream package.",
                }
            )
            transfers.append(record)
            continue

        dest_file = skill_root / destination_path
        if not dest_file.exists():
            record.update(
                {
                    "destination_path": destination_path,
                    "transfer_type": "omitted",
                    "transformation_tool": None,
                    "destination_sha256": None,
                    "destination_git_blob_sha": None,
                    "parity_tests": [],
                    "rationale": "Mapped to a local destination path but the file does not exist in this checkout.",
                }
            )
            transfers.append(record)
            continue

        dest_sha256 = compute_sha256(dest_file)
        dest_git_blob = compute_git_blob_sha(dest_file, cwd=skill_root)

        override = _TRANSFER_OVERRIDES.get(source_path, {})
        if dest_git_blob == entry["source_git_blob_sha"]:
            transfer_type = "exact_copy"
            tool = None
            rationale = "Copied verbatim from the canonical upstream source."
            parity_tests = _DEFAULT_PARITY_TESTS.get(source_path, [])
        else:
            transfer_type = override.get("transfer_type", "derived")
            tool = override.get("transformation_tool")
            rationale = override.get(
                "rationale",
                "Adapted from the canonical upstream source for the Skill-RUP implementation.",
            )
            parity_tests = override.get("parity_tests", _DEFAULT_PARITY_TESTS.get(source_path, []))

        record.update(
            {
                "destination_path": destination_path,
                "transfer_type": transfer_type,
                "transformation_tool": tool,
                "destination_sha256": dest_sha256,
                "destination_git_blob_sha": dest_git_blob,
                "parity_tests": parity_tests,
                "rationale": rationale,
            }
        )
        transfers.append(record)

    return {
        "generated_at": canonical_manifest["generated_at"],
        "canonical_repository": canonical_manifest["canonical_repository"],
        "canonical_commit": canonical_manifest["canonical_commit"],
        "canonical_protocol_version": canonical_manifest["canonical_protocol_version"],
        "total_transfers": len(transfers),
        "transfers": transfers,
    }


def verify_transfer_manifest(
    skill_root: Path,
    transfer_manifest: Dict[str, Any],
    upstream_dir: Path,
) -> Dict[str, Any]:
    """Verify a transfer manifest by reconstructing the upstream tree.

    For every transfer with a destination, the function recomputes the
    destination hashes and compares them to the values recorded in the manifest.
    It also confirms that the recorded source git blob SHA matches the upstream
    tree.  Returns a report dict with ``valid``, ``checked``, ``passed``,
    ``failed``, and ``failures``.
    """
    skill_root = skill_root.resolve()
    upstream_dir = upstream_dir.resolve()

    upstream_tree = {
        e["path"]: e["sha"] for e in enumerate_git_tree(upstream_dir)
    }

    failures: List[Dict[str, Any]] = []
    checked = 0
    passed = 0

    for transfer in transfer_manifest.get("transfers", []):
        destination_path = transfer.get("destination_path")
        source_path = transfer["source_path"]
        if destination_path is None:
            continue

        checked += 1
        dest_file = skill_root / destination_path
        if not dest_file.exists():
            failures.append(
                {
                    "source_path": source_path,
                    "destination_path": destination_path,
                    "reason": "Destination file is missing",
                }
            )
            continue

        expected_source_blob = upstream_tree.get(source_path)
        recorded_source_blob = transfer["source_git_blob_sha"]
        if expected_source_blob is None:
            failures.append(
                {
                    "source_path": source_path,
                    "destination_path": destination_path,
                    "reason": "Source path not found in reconstructed upstream tree",
                }
            )
            continue
        if expected_source_blob != recorded_source_blob:
            failures.append(
                {
                    "source_path": source_path,
                    "destination_path": destination_path,
                    "reason": (
                        f"Recorded source git blob {recorded_source_blob} does not "
                        f"match reconstructed upstream blob {expected_source_blob}"
                    ),
                }
            )
            continue

        dest_sha256 = compute_sha256(dest_file)
        dest_git_blob = compute_git_blob_sha(dest_file, cwd=skill_root)

        if dest_sha256 != transfer.get("destination_sha256"):
            failures.append(
                {
                    "source_path": source_path,
                    "destination_path": destination_path,
                    "reason": "Destination SHA-256 does not match recorded value",
                    "recorded": transfer.get("destination_sha256"),
                    "actual": dest_sha256,
                }
            )
            continue

        if dest_git_blob != transfer.get("destination_git_blob_sha"):
            failures.append(
                {
                    "source_path": source_path,
                    "destination_path": destination_path,
                    "reason": "Destination git blob SHA does not match recorded value",
                    "recorded": transfer.get("destination_git_blob_sha"),
                    "actual": dest_git_blob,
                }
            )
            continue

        passed += 1

    return {
        "valid": len(failures) == 0,
        "checked": checked,
        "passed": passed,
        "failed": len(failures),
        "failures": failures,
    }


class ProvenanceManager:
    """High-level provenance helper for the RUP runtime."""

    def __init__(self, repo_root: Path):
        self.repo_root = repo_root.resolve()

    def generate_source_manifest(self) -> Dict[str, Any]:
        """Generate a complete source manifest with SHA-256 and Git blob SHAs.

        .. deprecated::
            This method enumerates the local Skill-RUP repository and labels it
            as canonical, which is the bug that C-02 fixes.  It is kept for
            backwards compatibility but new code should use
            :func:`build_canonical_source_manifest` together with
            :func:`build_transfer_manifest`.
        """
        manifest_files = []
        for p in sorted(self.repo_root.rglob("*")):
            if not p.is_file():
                continue
            if any(
                part in p.parts
                for part in [".git", ".venv", "__pycache__", ".reference", "dist", "build"]
            ):
                continue

            rel = p.relative_to(self.repo_root)
            manifest_files.append(
                {
                    "path": str(rel),
                    "sha256": compute_sha256(p),
                    "git_blob_sha": compute_git_blob_sha(p, cwd=self.repo_root),
                    "size_bytes": p.stat().st_size,
                }
            )

        return {
            "canonical_repository": CANONICAL_RUP_REPO,
            "canonical_commit": CANONICAL_RUP_COMMIT,
            "protocol_version": CANONICAL_PROTOCOL_VERSION,
            "total_files": len(manifest_files),
            "files": manifest_files,
        }

    def verify_against_canonical_commit(
        self,
        transfer_manifest: Dict[str, Any],
        upstream_dir: Optional[Path] = None,
    ) -> Dict[str, Any]:
        """Verify ``transfer_manifest`` against the pinned canonical commit.

        If ``upstream_dir`` is not provided, the canonical repository is cloned
        to a temporary directory and cleaned up after verification.
        """
        temp_dir: Optional[tempfile.TemporaryDirectory] = None
        try:
            if upstream_dir is None:
                temp_dir = tempfile.TemporaryDirectory()
                upstream_dir = clone_upstream_commit(
                    CANONICAL_RUP_REPO,
                    CANONICAL_RUP_COMMIT,
                    Path(temp_dir.name),
                )
            return verify_transfer_manifest(
                self.repo_root,
                transfer_manifest,
                upstream_dir,
            )
        finally:
            if temp_dir is not None:
                temp_dir.cleanup()
