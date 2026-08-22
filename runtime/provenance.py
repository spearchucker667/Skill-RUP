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
import re
import tempfile
import warnings
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .command_runner import run_command
from .security import iter_jailed_files
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

# Curated rationale for upstream files that are intentionally not transferred
# into Skill-RUP (audit P1-4). Each entry classifies WHY the file was omitted
# and points to the downstream artifact (runtime module, workflow, reference,
# or capability ID) that preserves the upstream behavior:
#   - irrelevant_to_skill       : content has no bearing on the skill's operation
#   - represented_elsewhere     : behavior preserved in another downstream artifact
#   - agent_native              : behavior requires model/agent judgment
#   - runtime_translated        : behavior implemented in the deterministic runtime
#   - development_only          : upstream repo's own tooling/CI/tests, not protocol
#   - superseded                : replaced by a newer downstream implementation
#   - intentionally_not_supported: explicitly out of scope
_OMISSION_RATIONALE: Dict[str, Dict[str, Any]] = {
    # --- Upstream repository self-artifacts (not protocol content) ---
    ".github/workflows/ci.yml": {
        "rationale_class": "development_only",
        "rationale": "Upstream repository's own CI workflow; Skill-RUP maintains its own matrix CI.",
        "implemented_in": [".github/workflows/ci.yml"],
    },
    ".github/workflows/codeql.yml": {
        "rationale_class": "development_only",
        "rationale": "Upstream repository's own CodeQL workflow; Skill-RUP runs its own CodeQL.",
        "implemented_in": [".github/workflows/security-scan.yml"],
    },
    ".github/workflows/link-check.yml": {
        "rationale_class": "development_only",
        "rationale": "Upstream repository's own link-check workflow.",
        "implemented_in": ["scripts/check_docs.py"],
    },
    ".github/workflows/publish.yml": {
        "rationale_class": "development_only",
        "rationale": "Upstream repository's own publish workflow.",
        "implemented_in": [],
    },
    ".github/workflows/release-drafter.yml": {
        "rationale_class": "irrelevant_to_skill",
        "rationale": "Upstream repository's release-drafter automation, unrelated to runtime behavior.",
        "implemented_in": [],
    },
    ".github/workflows/supply-chain.yml": {
        "rationale_class": "development_only",
        "rationale": "Upstream repository's own supply-chain scan workflow.",
        "implemented_in": [".github/workflows/security-scan.yml"],
    },
    ".github/workflows/validate.yml": {
        "rationale_class": "development_only",
        "rationale": "Upstream repository's own validation workflow; equivalent gates live in Skill-RUP CI.",
        "implemented_in": [".github/workflows/ci.yml"],
    },
    ".github/dependabot.yml": {
        "rationale_class": "represented_elsewhere",
        "rationale": "Dependency-update automation is covered by the canonical dependency management guidance in the workflows and references.",
        "implemented_in": ["workflows/"],
    },
    ".github/release-drafter.yml": {
        "rationale_class": "irrelevant_to_skill",
        "rationale": "Upstream repository's release-drafter configuration, unrelated to runtime behavior.",
        "implemented_in": [],
    },
    ".github/FUNDING.yml": {
        "rationale_class": "irrelevant_to_skill",
        "rationale": "Upstream repository funding metadata, no runtime relevance.",
        "implemented_in": [],
    },
    ".github/copilot-instructions.md": {
        "rationale_class": "irrelevant_to_skill",
        "rationale": "Upstream editor-assistant instructions, no runtime relevance.",
        "implemented_in": [],
    },
    ".github/ISSUE_TEMPLATE/bug_report.md": {
        "rationale_class": "represented_elsewhere",
        "rationale": "The canonical bug report template is carried in rup-protocol.yaml (bug_fixes workstream) and the governance workflows.",
        "implemented_in": ["protocol/rup-protocol.yaml", "workflows/"],
    },
    ".github/ISSUE_TEMPLATE/feature_request.md": {
        "rationale_class": "represented_elsewhere",
        "rationale": "Feature request template content is preserved in the governance workflows and references.",
        "implemented_in": ["workflows/"],
    },
    ".github/ISSUE_TEMPLATE/config.yml": {
        "rationale_class": "irrelevant_to_skill",
        "rationale": "Upstream issue-template routing metadata, no runtime relevance.",
        "implemented_in": [],
    },
    ".github/pull_request_template.md": {
        "rationale_class": "represented_elsewhere",
        "rationale": "PR template guidance is preserved in the governance workflows.",
        "implemented_in": ["workflows/"],
    },
    ".github/SECURITY.md": {
        "rationale_class": "represented_elsewhere",
        "rationale": "Security policy content is generated by the runtime security workstream and documented in the security workflows.",
        "implemented_in": ["runtime/execution.py", "workflows/"],
    },
    ".github/CODEOWNERS": {
        "rationale_class": "represented_elsewhere",
        "rationale": "CODEOWNERS generation is implemented by the runtime governance workstream.",
        "implemented_in": ["runtime/execution.py"],
    },
    ".gitignore": {
        "rationale_class": "development_only",
        "rationale": "Upstream repository's own ignore rules; Skill-RUP maintains its own.",
        "implemented_in": [".gitignore"],
    },
    "AGENTS.md": {
        "rationale_class": "development_only",
        "rationale": "Upstream repository's own agent instructions, superseded by SKILL.md and AGENTS.md.",
        "implemented_in": ["SKILL.md", "AGENTS.md"],
    },
    "CODEOWNERS": {
        "rationale_class": "represented_elsewhere",
        "rationale": "CODEOWNERS generation is implemented by the runtime governance workstream.",
        "implemented_in": ["runtime/execution.py"],
    },
    "CONTRIBUTING.md": {
        "rationale_class": "represented_elsewhere",
        "rationale": "Contributing guidance is preserved in the documentation workflows and generated by the runtime documentation workstream.",
        "implemented_in": ["runtime/execution.py", "workflows/"],
    },
    "LICENSE": {
        "rationale_class": "represented_elsewhere",
        "rationale": "License handling is implemented by the runtime governance workstream; attribution is in THIRD_PARTY_NOTICES.md.",
        "implemented_in": ["runtime/execution.py", "THIRD_PARTY_NOTICES.md"],
    },
    "Makefile": {
        "rationale_class": "irrelevant_to_skill",
        "rationale": "Upstream build convenience wrapper; Skill-RUP uses documented script entry points.",
        "implemented_in": ["scripts/", "requirements-ci.txt"],
    },
    "README.md": {
        "rationale_class": "represented_elsewhere",
        "rationale": "Upstream repository README; the skill's operational projection lives in SKILL.md and this repository's README.md.",
        "implemented_in": ["SKILL.md", "README.md"],
    },
    "TODO.md": {
        "rationale_class": "development_only",
        "rationale": "Upstream repository's internal TODO list.",
        "implemented_in": [],
    },
    # --- Upstream governance template directory ---
    "governance/CODEOWNERS": {
        "rationale_class": "represented_elsewhere",
        "rationale": "Canonical governance guidance is preserved in the governance workflows.",
        "implemented_in": ["workflows/"],
    },
    "governance/CONTRIBUTING.md": {
        "rationale_class": "represented_elsewhere",
        "rationale": "Canonical governance guidance is preserved in the governance workflows.",
        "implemented_in": ["workflows/"],
    },
    "governance/templates/bug_report.md": {
        "rationale_class": "represented_elsewhere",
        "rationale": "Issue template guidance is preserved in the governance workflows and the canonical protocol.",
        "implemented_in": ["protocol/rup-protocol.yaml", "workflows/"],
    },
    "governance/templates/feature_request.md": {
        "rationale_class": "represented_elsewhere",
        "rationale": "Issue template guidance is preserved in the governance workflows.",
        "implemented_in": ["workflows/"],
    },
    # --- Upstream development tooling ---
    "package.json": {
        "rationale_class": "development_only",
        "rationale": "Upstream repository's own JavaScript manifest for its validator tooling.",
        "implemented_in": [],
    },
    "package-lock.json": {
        "rationale_class": "development_only",
        "rationale": "Upstream repository's own lockfile for its validator tooling.",
        "implemented_in": [],
    },
    "requirements.txt": {
        "rationale_class": "development_only",
        "rationale": "Upstream repository's own Python requirements; Skill-RUP pins its own in requirements-ci.txt.",
        "implemented_in": ["requirements-ci.txt"],
    },
    "ruff.toml": {
        "rationale_class": "development_only",
        "rationale": "Upstream repository's own lint configuration.",
        "implemented_in": [],
    },
    "tools/lint_docs.py": {
        "rationale_class": "development_only",
        "rationale": "Upstream documentation lint tool; Skill-RUP ships scripts/check_docs.py.",
        "implemented_in": ["scripts/check_docs.py"],
    },
    "tools/scripts/validate_rup.sh": {
        "rationale_class": "superseded",
        "rationale": "Replaced by the cross-platform scripts/validate_rup.py CLI.",
        "implemented_in": ["scripts/validate_rup.py"],
    },
    # --- Upstream self-run artifacts ---
    "runs/README.md": {
        "rationale_class": "irrelevant_to_skill",
        "rationale": "Upstream repository's self-run scratch output, not protocol content.",
        "implemented_in": [],
    },
    "runs/self-2026-01-26/discovery.json": {
        "rationale_class": "irrelevant_to_skill",
        "rationale": "Upstream repository's self-run scratch output, not protocol content.",
        "implemented_in": [],
    },
    "runs/self-2026-01-26/execution.json": {
        "rationale_class": "irrelevant_to_skill",
        "rationale": "Upstream repository's self-run scratch output, not protocol content.",
        "implemented_in": [],
    },
    "runs/self-2026-01-26/plan.json": {
        "rationale_class": "irrelevant_to_skill",
        "rationale": "Upstream repository's self-run scratch output, not protocol content.",
        "implemented_in": [],
    },
    "runs/self-2026-01-26/verification.json": {
        "rationale_class": "irrelevant_to_skill",
        "rationale": "Upstream repository's self-run scratch output, not protocol content.",
        "implemented_in": [],
    },
    # --- Upstream security folder ---
    "security/.gitkeep": {
        "rationale_class": "irrelevant_to_skill",
        "rationale": "Empty directory placeholder.",
        "implemented_in": [],
    },
    "security/SECURITY.md": {
        "rationale_class": "represented_elsewhere",
        "rationale": "Security policy content is generated by the runtime security workstream.",
        "implemented_in": ["runtime/execution.py", "workflows/"],
    },
    # --- Upstream test suite (repo self-tests, not protocol) ---
    "tests/test_links.py": {
        "rationale_class": "development_only",
        "rationale": "Upstream repository's own link tests; Skill-RUP has its own pytest suite.",
        "implemented_in": ["tests/", "scripts/check_docs.py"],
    },
    "tests/test_parity.py": {
        "rationale_class": "development_only",
        "rationale": "Upstream repository's own parity tests; Skill-RUP has its own capability/provenance checks.",
        "implemented_in": ["scripts/build_capability_map.py", "scripts/audit_sources.py"],
    },
    "tests/test_security.py": {
        "rationale_class": "development_only",
        "rationale": "Upstream repository's own security tests; Skill-RUP has its own security regression suite.",
        "implemented_in": ["tests/security/", "tests/test_security_scanning.py"],
    },
    "tests/test_validation.py": {
        "rationale_class": "development_only",
        "rationale": "Upstream repository's own validation tests; Skill-RUP has its own validator tests.",
        "implemented_in": ["tests/test_validator_cli.py"],
    },
    "tests/validation.test.js": {
        "rationale_class": "development_only",
        "rationale": "Upstream JavaScript validator test; the Python validator is authoritative in Skill-RUP.",
        "implemented_in": ["scripts/validate_rup.py", "scripts/validate_rup.js"],
    },
    # --- Upstream validators (superseded by the Skill-RUP validator) ---
    "validators/README.md": {
        "rationale_class": "represented_elsewhere",
        "rationale": "Validator usage is documented in scripts/README.md and the schema directory.",
        "implemented_in": ["scripts/README.md", "schemas/"],
    },
    "validators/validate_rup.js": {
        "rationale_class": "superseded",
        "rationale": "Replaced by the cross-platform scripts/validate_rup.py and the retained JS validator.",
        "implemented_in": ["scripts/validate_rup.py", "scripts/validate_rup.js"],
    },
    "validators/validate_rup.py": {
        "rationale_class": "superseded",
        "rationale": "Replaced by the reworked scripts/validate_rup.py CLI with schema drift checks.",
        "implemented_in": ["scripts/validate_rup.py"],
    },
}

# Overrides for upstream files that are intentionally not verbatim copies.
# Each entry provides the transfer classification, the transformation that was
# applied, a human-readable rationale, and the tests that demonstrate parity
# with the canonical source intent.
_TRANSFER_OVERRIDES: Dict[str, Dict[str, Any]] = {
    "rup-schema.json": {
        "transfer_type": "derived",
        "transformation_tool": "manual/schema alignment",
        "rationale": (
            "Extended locally to add execution output rollback fields, "
            "prompt_injection_scan security results, and additional tool/reason "
            "metadata required by Skill-RUP while preserving the canonical "
            "RUP-Protocol validation contract."
        ),
        "parity_tests": [
            "tests/test_validator_cli.py::test_canonical_invocation_all",
            "tests/test_verification.py::test_prompt_injection_scan_separate_from_sast",
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
    """Compute the Git blob SHA for ``file_path``.

    SHA-1 is used here only to reproduce Git's object identifier for
    provenance/lineage comparison, not for any security purpose.

    Inside a Git worktree, ``git hash-object --path`` is authoritative because
    it applies path-specific clean filters such as CRLF normalization. Raw-byte
    hashing is the deterministic fallback for files outside a worktree.
    """
    if cwd is not None:
        resolved_cwd = cwd.resolve()
        try:
            relative_path = file_path.resolve().relative_to(resolved_cwd)
        except ValueError:
            relative_path = None

        if relative_path is not None:
            rc, inside_worktree, _ = run_command(
                ["git", "rev-parse", "--is-inside-work-tree"],
                cwd=resolved_cwd,
            )
            if rc == 0 and inside_worktree.strip() == "true":
                git_path = relative_path.as_posix()
                rc, stdout, _ = run_command(
                    ["git", "hash-object", "--path", git_path, git_path],
                    cwd=resolved_cwd,
                )
                if rc == 0 and stdout.strip():
                    return stdout.strip()

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

    # ``git ls-tree -r -l -z`` emits records separated by NUL.  The format is
    # ``<mode> <type> <sha> [<size>]\t<path>``; ``size`` is present for blobs
    # when ``-l`` is used and omitted for submodule/commit entries.
    record_re = re.compile(
        r"^(?P<mode>\d+) (?P<type>\w+) (?P<sha>[0-9a-f]{40})(?:\s+(?P<size>-|\d+))?\t(?P<path>.+)$"
    )
    for record in stdout.split("\0"):
        if not record:
            continue
        match = record_re.match(record)
        if not match:
            warnings.warn(
                f"Could not parse git ls-tree record: {record!r}", RuntimeWarning
            )
            continue
        size_str = match.group("size")
        try:
            size = int(size_str) if size_str is not None and size_str != "-" else -1
        except ValueError:
            size = -1
        entries.append(
            {
                "mode": match.group("mode"),
                "type": match.group("type"),
                "sha": match.group("sha"),
                "size_bytes": size,
                "path": match.group("path"),
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
        "source_root": CANONICAL_RUP_REPO,
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
            omission = _OMISSION_RATIONALE.get(
                source_path,
                {
                    "rationale_class": "irrelevant_to_skill",
                    "rationale": "Not used as an authoritative source in the Skill-RUP downstream package.",
                    "implemented_in": [],
                },
            )
            record.update(
                {
                    "destination_path": None,
                    "transfer_type": "omitted",
                    "transformation_tool": None,
                    "destination_sha256": None,
                    "destination_git_blob_sha": None,
                    "parity_tests": [],
                    "rationale_class": omission["rationale_class"],
                    "rationale": omission["rationale"],
                    "implemented_in": omission["implemented_in"],
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
                    "rationale_class": "unaccounted",
                    "rationale": "Mapped to a local destination path but the file does not exist in this checkout.",
                    "implemented_in": [],
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
                "Adapted and extended locally from the canonical upstream source for the Skill-RUP implementation.",
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
                "rationale_class": transfer_type,
                "rationale": rationale,
                "implemented_in": [destination_path],
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
    omitted = 0
    exact_copies = 0
    derived = 0
    translated = 0

    transfers = transfer_manifest.get("transfers", [])
    recorded_source_paths = {t["source_path"] for t in transfers}
    upstream_paths = set(upstream_tree.keys())

    # Full coverage: every upstream path must be accounted for and no phantom
    # source paths may appear in the manifest. Unaccounted paths are reported
    # separately from transferred passes; they never increase any pass count.
    unaccounted = len(upstream_paths - recorded_source_paths) + len(
        recorded_source_paths - upstream_paths
    )
    for missing in upstream_paths - recorded_source_paths:
        failures.append(
            {
                "source_path": missing,
                "reason": "Upstream path missing from transfer manifest",
            }
        )
    for extra in recorded_source_paths - upstream_paths:
        failures.append(
            {
                "source_path": extra,
                "reason": "Transfer manifest contains path not in upstream tree",
            }
        )

    for transfer in transfers:
        destination_path = transfer.get("destination_path")
        source_path = transfer["source_path"]
        recorded_source_blob = transfer.get("source_git_blob_sha")
        expected_source_blob = upstream_tree.get(source_path)

        if expected_source_blob is None:
            # Already recorded as a coverage failure above.
            continue

        if recorded_source_blob != expected_source_blob:
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

        # Source identity is verified for omitted records as well as transferred
        # records; an omitted upstream file must still be the file we think it is.
        checked += 1
        if destination_path is None:
            # A justified omission is provenance completeness, not a transfer
            # pass: it can never increase the transferred/parity-passed count
            # (audit P1-3).
            omitted += 1
            continue

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
        transfer_type = transfer.get("transfer_type", "derived")
        if transfer_type == "exact_copy":
            exact_copies += 1
        elif transfer_type == "translated":
            translated += 1
        else:
            derived += 1

    return {
        "valid": len(failures) == 0,
        "upstream_files": len(upstream_paths),
        "checked": checked,
        "passed": passed,
        "exact_copies": exact_copies,
        "derived": derived,
        "translated": translated,
        "omitted_with_justification": omitted,
        "unaccounted": unaccounted,
        # Canonical parity is never auto-claimed; the runtime verifies hashes,
        # while behavioral parity requires the semantic tests per capability.
        "semantic_parity_verified": 0,
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
        skip_dirs = {".git", ".venv", "__pycache__", ".reference", "dist", "build"}
        for p in sorted(
            iter_jailed_files(self.repo_root, skip_dirnames=skip_dirs),
            key=lambda path: str(path),
        ):
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
