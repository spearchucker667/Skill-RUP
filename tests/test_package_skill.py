import subprocess
import sys
import uuid
import zipfile
from pathlib import Path

import pytest

SCRIPT = Path(__file__).parent.parent / "scripts" / "package_skill.py"
ROOT = Path(__file__).parent.parent


def _run(args, cwd=ROOT):
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        capture_output=True,
        text=True,
        cwd=str(cwd),
    )


def _unique_dist_path(prefix: str) -> Path:
    return ROOT / "dist" / "package-test" / f"{prefix}-{uuid.uuid4().hex[:8]}"


def test_package_cli_args():
    out = _unique_dist_path("rup-skill-v1.2.3") / "rup-skill-v1.2.3.zip"
    out.parent.mkdir(parents=True, exist_ok=True)
    result = _run(["--version", "1.2.3", "--output", str(out), "--root", str(ROOT)])
    assert result.returncode == 0, result.stdout + result.stderr
    assert out.exists()
    assert (out.with_suffix(out.suffix + ".sha256")).exists()


def test_package_rejects_invalid_version():
    result = _run(["--version", "not-a-version", "--output", "dist/x.zip"])
    assert result.returncode == 1
    assert "semantic" in result.stderr.lower() or "version" in result.stderr.lower()


def test_package_rejects_traversal(tmp_path):
    out = tmp_path.parent / "escaped.zip"
    result = _run(["--version", "1.0.0", "--output", str(out), "--root", str(ROOT)])
    assert result.returncode == 1
    assert "Output path must be inside" in result.stderr


def test_package_reproducible():
    base = _unique_dist_path("repro")
    base.mkdir(parents=True, exist_ok=True)
    out1 = base / "a.zip"
    out2 = base / "b.zip"
    r1 = _run(["--version", "3.0.0", "--output", str(out1), "--root", str(ROOT)])
    assert r1.returncode == 0, r1.stdout + r1.stderr
    r2 = _run(["--version", "3.0.0", "--output", str(out2), "--root", str(ROOT)])
    assert r2.returncode == 0, r2.stdout + r2.stderr
    sha1 = (out1.with_suffix(out1.suffix + ".sha256")).read_text().split()[0]
    sha2 = (out2.with_suffix(out2.suffix + ".sha256")).read_text().split()[0]
    assert sha1 == sha2


def test_package_top_level_rup_directory():
    out = _unique_dist_path("rup-skill-v3.0.0") / "rup-skill-v3.0.0.zip"
    out.parent.mkdir(parents=True, exist_ok=True)
    result = _run(["--version", "3.0.0", "--output", str(out), "--root", str(ROOT)])
    assert result.returncode == 0, result.stdout + result.stderr
    with zipfile.ZipFile(out, "r") as zf:
        names = zf.namelist()
        assert any(name.startswith("rup/") for name in names)
        assert "rup/SKILL.md" in names
        assert "rup/manifest.json" in names


def test_package_verify_command():
    out = _unique_dist_path("verify") / "rup-skill-v3.0.0.zip"
    out.parent.mkdir(parents=True, exist_ok=True)
    r = _run(["--version", "3.0.0", "--output", str(out), "--root", str(ROOT)])
    assert r.returncode == 0, r.stdout + r.stderr
    v = _run(["--verify", "--output", str(out)])
    assert v.returncode == 0, v.stdout + v.stderr
    assert "PASSED" in v.stdout


def test_package_manifest_hashes_match():
    out = _unique_dist_path("hashes") / "rup-skill-v3.0.0.zip"
    out.parent.mkdir(parents=True, exist_ok=True)
    r = _run(["--version", "3.0.0", "--output", str(out), "--root", str(ROOT)])
    assert r.returncode == 0, r.stdout + r.stderr
    with zipfile.ZipFile(out, "r") as zf:
        manifest = __import__("json").loads(zf.read("rup/manifest.json").decode("utf-8"))
        for arcname, expected_sha in manifest["files"].items():
            data = zf.read(arcname)
            actual = __import__("hashlib").sha256(data).hexdigest()
            assert actual == expected_sha, f"hash mismatch for {arcname}"


def test_package_rejects_symlinked_member(tmp_path):
    """RUP-SEC-001 packaging: a symlinked member must abort packaging."""
    import os as _os

    root = tmp_path / "skill_root"
    root.mkdir()
    (root / "SKILL.md").write_text("name: rup\n", encoding="utf-8")
    outside = tmp_path / "outside_secret.txt"
    outside.write_text("secret content", encoding="utf-8")
    try:
        _os.symlink(outside, root / "leak.txt")
    except (OSError, NotImplementedError, PermissionError):
        pytest.skip("Symlinks not supported on this platform")

    out = tmp_path / "dist" / "out.zip"
    result = _run(["--version", "1.0.0", "--output", str(out), "--root", str(root)])
    assert result.returncode == 1
    assert "symlink" in result.stderr.lower()
    assert not out.exists()


def test_verify_package_fails_on_extra_file():
    out = _unique_dist_path("extra") / "rup-skill-v3.0.0.zip"
    out.parent.mkdir(parents=True, exist_ok=True)
    r = _run(["--version", "3.0.0", "--output", str(out), "--root", str(ROOT)])
    assert r.returncode == 0, r.stdout + r.stderr
    # Inject an undeclared file without touching the external checksum sidecar.
    sha_path = out.with_suffix(out.suffix + ".sha256")
    sha_path.unlink()
    with zipfile.ZipFile(out, "a") as zf:
        zf.writestr("rup/extra-injected-file.txt", b"injected")
    v = _run(["--verify", "--output", str(out)])
    assert v.returncode == 1, v.stdout + v.stderr
    assert "member mismatch" in v.stderr.lower() or "extra" in v.stderr.lower()


def test_verify_package_fails_on_external_checksum_mismatch():
    out = _unique_dist_path("sha") / "rup-skill-v3.0.0.zip"
    out.parent.mkdir(parents=True, exist_ok=True)
    r = _run(["--version", "3.0.0", "--output", str(out), "--root", str(ROOT)])
    assert r.returncode == 0, r.stdout + r.stderr
    sha_path = out.with_suffix(out.suffix + ".sha256")
    sha_path.write_text("0" * 64 + f"  {out.name}\n", encoding="utf-8")
    v = _run(["--verify", "--output", str(out)])
    assert v.returncode == 1, v.stdout + v.stderr
    assert "sha-256 mismatch" in v.stderr.lower() or "external" in v.stderr.lower()
