"""Version consistency tests.

The repository has a single source of truth (the VERSION file). These tests
prove that every artifact carrying a version agrees with it.
"""
import json
import zipfile
from pathlib import Path

import yaml

import runtime

ROOT = Path(__file__).parent.parent


def test_version_file_matches_runtime():
    """runtime.__version__ must agree with the repository VERSION file."""
    expected = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
    assert runtime.__version__ == expected


def test_skill_metadata_version_matches_version_file():
    """SKILL.md front-matter metadata.version must agree with VERSION."""
    expected = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
    skill_text = (ROOT / "SKILL.md").read_text(encoding="utf-8")
    front_matter = skill_text.split("---", 2)[1]
    skill = yaml.safe_load(front_matter)
    assert skill["metadata"]["version"] == expected


def test_packaged_manifest_version_matches_version_file():
    """A packaged skill manifest must report the same version as VERSION."""
    expected = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
    out = ROOT / "dist" / "package-test" / "version-consistency.zip"
    out.parent.mkdir(parents=True, exist_ok=True)
    result = __import__("subprocess").run(
        [
            __import__("sys").executable,
            str(ROOT / "scripts" / "package_skill.py"),
            "--version",
            expected,
            "--output",
            str(out),
            "--root",
            str(ROOT),
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    with zipfile.ZipFile(out) as zf:
        manifest = json.loads(zf.read("rup/manifest.json").decode("utf-8"))
    assert manifest["version"] == expected
