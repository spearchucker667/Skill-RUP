"""
Regression tests for the provenance and source-transfer subsystem.

These tests avoid external network dependencies by constructing local git
repositories that act as the canonical upstream source.
"""
import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent.resolve()
sys.path.insert(0, str(ROOT))

from runtime.provenance import (
    CANONICAL_RUP_COMMIT,
    build_canonical_source_manifest,
    build_transfer_manifest,
    clone_upstream_commit,
    compute_git_blob_sha,
    compute_sha256,
    enumerate_git_tree,
    verify_transfer_manifest,
    ProvenanceManager,
)
from runtime.command_runner import run_command


def _git_init_with_commit(repo: Path, files: dict, message: str = "initial") -> None:
    """Create a git repo at ``repo`` with the given ``files`` (rel_path -> bytes)."""
    repo.mkdir(parents=True, exist_ok=True)
    for cmd in (
        ["git", "init"],
        ["git", "config", "user.email", "test@example.com"],
        ["git", "config", "user.name", "Test User"],
    ):
        rc, _, err = run_command(cmd, cwd=repo)
        if rc != 0:
            raise RuntimeError(f"git setup failed: {cmd}: {err}")
    for rel_path, content in files.items():
        target = repo / rel_path
        target.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(content, str):
            content = content.encode("utf-8")
        target.write_bytes(content)
    rc, _, err = run_command(["git", "add", "."], cwd=repo)
    if rc != 0:
        raise RuntimeError(f"git add failed: {err}")
    rc, _, err = run_command(["git", "commit", "-m", message], cwd=repo)
    if rc != 0:
        raise RuntimeError(f"git commit failed: {err}")


@pytest.fixture
def upstream_repo(tmp_path: Path):
    """A local upstream repository with a small canonical source tree."""
    repo = tmp_path / "upstream"
    files = {
        "rup-protocol.yaml": "protocol: v3.0.0\n",
        "rup-schema.json": '{"$schema": "test"}\n',
        "legacy/README.md": "# Legacy\n",
        "examples/discovery_output.json": "{}\n",
        "examples/verification_output.json": "{}\n",
        "foreign/boilerplate.md": "# Foreign\n",
    }
    _git_init_with_commit(repo, files)
    return repo


@pytest.fixture
def skill_root(tmp_path: Path, upstream_repo: Path):
    """A Skill-RUP-like tree containing transferred files."""
    skill = tmp_path / "skill"
    skill.mkdir()
    # Exact copies from upstream.
    (skill / "protocol").mkdir()
    (skill / "protocol" / "rup-protocol.yaml").write_bytes(
        (upstream_repo / "rup-protocol.yaml").read_bytes()
    )
    (skill / "protocol" / "legacy").mkdir(parents=True, exist_ok=True)
    (skill / "protocol" / "legacy" / "README.md").write_bytes(
        (upstream_repo / "legacy" / "README.md").read_bytes()
    )
    (skill / "examples").mkdir(parents=True, exist_ok=True)
    (skill / "examples" / "discovery_output.json").write_bytes(
        (upstream_repo / "examples" / "discovery_output.json").read_bytes()
    )
    (skill / "examples" / "verification_output.json").write_bytes(
        (upstream_repo / "examples" / "verification_output.json").read_bytes()
    )
    # Derived copy (modified schema).
    (skill / "protocol" / "rup-schema.json").write_text(
        '{"$schema": "test", "extended": true}\n'
    )
    return skill


def test_compute_git_blob_sha_matches_git_hash_object(tmp_path: Path):
    f = tmp_path / "sample.txt"
    f.write_text("hello provenance")
    expected = compute_git_blob_sha(f, cwd=tmp_path)
    rc, out, _ = run_command(["git", "hash-object", str(f)], cwd=tmp_path)
    assert rc == 0
    assert expected == out.strip()


def test_compute_sha256_matches_python_hashlib(tmp_path: Path):
    f = tmp_path / "sample.txt"
    f.write_text("hello provenance")
    expected = hashlib.sha256(f.read_bytes()).hexdigest()
    assert compute_sha256(f) == expected


def test_enumerate_git_tree_returns_sorted_blob_entries(upstream_repo: Path):
    entries = enumerate_git_tree(upstream_repo)
    paths = [e["path"] for e in entries]
    assert paths == sorted(paths)
    assert all(e["type"] == "blob" for e in entries)
    assert set(paths) == {
        "rup-protocol.yaml",
        "rup-schema.json",
        "legacy/README.md",
        "examples/discovery_output.json",
        "examples/verification_output.json",
        "foreign/boilerplate.md",
    }
    for entry in entries:
        assert len(entry["sha"]) == 40
        assert isinstance(entry["size_bytes"], int)
        assert entry["size_bytes"] >= 0


def test_build_canonical_source_manifest_maps_known_files(
    skill_root: Path, upstream_repo: Path
):
    manifest = build_canonical_source_manifest(skill_root, upstream_repo)
    by_path = {e["source_path"]: e for e in manifest["files"]}

    assert by_path["rup-protocol.yaml"]["destination_path"] == "protocol/rup-protocol.yaml"
    assert by_path["legacy/README.md"]["destination_path"] == "protocol/legacy/README.md"
    assert by_path["examples/discovery_output.json"]["destination_path"] == "examples/discovery_output.json"
    assert by_path["examples/verification_output.json"]["destination_path"] == "examples/verification_output.json"
    assert by_path["foreign/boilerplate.md"]["destination_path"] is None

    for entry in manifest["files"]:
        assert len(entry["source_git_blob_sha"]) == 40
        assert len(entry["source_sha256"]) == 64


def test_build_transfer_manifest_exact_copy(skill_root: Path, upstream_repo: Path):
    canonical = build_canonical_source_manifest(skill_root, upstream_repo)
    transfer = build_transfer_manifest(skill_root, canonical)
    by_path = {t["source_path"]: t for t in transfer["transfers"]}

    proto = by_path["rup-protocol.yaml"]
    assert proto["transfer_type"] == "exact_copy"
    assert proto["transformation_tool"] is None
    assert proto["destination_sha256"] == proto["source_sha256"]
    assert proto["destination_git_blob_sha"] == proto["source_git_blob_sha"]
    assert proto["rationale"] == "Copied verbatim from the canonical upstream source."


def test_build_transfer_manifest_derived(skill_root: Path, upstream_repo: Path):
    canonical = build_canonical_source_manifest(skill_root, upstream_repo)
    transfer = build_transfer_manifest(skill_root, canonical)
    by_path = {t["source_path"]: t for t in transfer["transfers"]}

    schema = by_path["rup-schema.json"]
    assert schema["transfer_type"] == "derived"
    assert schema["destination_sha256"] != schema["source_sha256"]
    assert schema["destination_git_blob_sha"] != schema["source_git_blob_sha"]
    assert "extended locally" in schema["rationale"].lower()


def test_build_transfer_manifest_omits_unmapped_files(
    skill_root: Path, upstream_repo: Path
):
    canonical = build_canonical_source_manifest(skill_root, upstream_repo)
    transfer = build_transfer_manifest(skill_root, canonical)
    by_path = {t["source_path"]: t for t in transfer["transfers"]}

    foreign = by_path["foreign/boilerplate.md"]
    assert foreign["transfer_type"] == "omitted"
    assert foreign["destination_path"] is None
    assert foreign["destination_sha256"] is None


def test_verify_transfer_manifest_passes_for_exact_copies(
    skill_root: Path, upstream_repo: Path
):
    canonical = build_canonical_source_manifest(skill_root, upstream_repo)
    transfer = build_transfer_manifest(skill_root, canonical)
    report = verify_transfer_manifest(skill_root, transfer, upstream_repo)

    assert report["valid"] is True
    assert report["failed"] == 0
    assert report["passed"] == report["checked"]


def test_verify_transfer_manifest_fails_on_tampered_destination(
    skill_root: Path, upstream_repo: Path
):
    canonical = build_canonical_source_manifest(skill_root, upstream_repo)
    transfer = build_transfer_manifest(skill_root, canonical)

    # Tamper with an exact-copy file after the manifest was built.
    target = skill_root / "protocol" / "rup-protocol.yaml"
    target.write_text("tampered\n")

    report = verify_transfer_manifest(skill_root, transfer, upstream_repo)
    assert report["valid"] is False
    assert report["failed"] >= 1
    failure_paths = {f["destination_path"] for f in report["failures"]}
    assert "protocol/rup-protocol.yaml" in failure_paths


def test_provenance_manager_verify_against_canonical_commit(
    skill_root: Path, upstream_repo: Path
):
    canonical = build_canonical_source_manifest(skill_root, upstream_repo)
    transfer = build_transfer_manifest(skill_root, canonical)
    manager = ProvenanceManager(skill_root)
    report = manager.verify_against_canonical_commit(transfer, upstream_dir=upstream_repo)
    assert report["valid"] is True


def test_clone_upstream_commit_clones_and_checks_out_commit(
    tmp_path: Path, upstream_repo: Path
):
    # Make the upstream repo accessible as a remote by creating a bare clone.
    bare = tmp_path / "upstream.git"
    rc, _, err = run_command(
        ["git", "clone", "--bare", str(upstream_repo), str(bare)], cwd=tmp_path
    )
    if rc != 0:
        raise RuntimeError(f"bare clone failed: {err}")

    dest = tmp_path / "cloned"
    rc, head, _ = run_command(["git", "rev-parse", "HEAD"], cwd=upstream_repo)
    commit = head.strip()

    result = clone_upstream_commit(str(bare), commit, dest)
    assert result == dest
    rc, cloned_head, _ = run_command(["git", "rev-parse", "HEAD"], cwd=dest)
    assert cloned_head.strip() == commit


def test_audit_sources_check_mode():
    """Smoke-test the audit_sources.py --check mode against the real manifests."""
    script = ROOT / "scripts" / "audit_sources.py"
    result = subprocess.run(
        [sys.executable, str(script), "--check"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=180,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "PASS" in result.stdout
