"""Unit tests for the RUP discovery phase."""
from pathlib import Path

from runtime.artifact_builder import ArtifactBuilder
from runtime.discovery import DiscoveryPhase
from runtime.paths import RupPaths
from runtime.state import StateManager


def test_discovery_emits_monorepo_field(tmp_path):
    """RUP-MONO-001: discovery reports the canonical workspace package graph."""
    repo = tmp_path / "mono_disc"
    (repo / "packages" / "a").mkdir(parents=True)
    (repo / "packages" / "b").mkdir(parents=True)
    (repo / "packages" / "a" / "package.json").write_text('{"name": "a"}', encoding="utf-8")
    (repo / "packages" / "b" / "package.json").write_text('{"name": "b"}', encoding="utf-8")
    (repo / "package.json").write_text('{"name": "root", "workspaces": ["packages/*"]}', encoding="utf-8")

    paths = RupPaths(repo)
    state = StateManager(paths)
    builder = ArtifactBuilder(paths, state=state)
    phase = DiscoveryPhase(repo, state, builder)

    result = phase.execute()

    mono = result["monorepo"]
    assert mono is not None
    assert mono["is_monorepo"] is True
    assert {p["name"] for p in mono["packages"]} == {"a", "b"}
    assert all("path" in p and "language" in p and "type" in p for p in mono["packages"])
    # tooling carries the same canonical shape for tooling.monorepo consumers.
    assert result["tooling"]["monorepo"]["is_monorepo"] is True


def test_no_lockfile_finding_for_unsupported_ecosystem(tmp_path):
    """RUP-DISC-001: languages without lockfile models must not produce SEC lockfile findings."""
    repo = tmp_path / "kotlin_repo"
    repo.mkdir()
    src = repo / "src" / "main" / "kotlin"
    src.mkdir(parents=True)
    (src / "App.kt").write_text("fun main() {}", encoding="utf-8")

    paths = RupPaths(repo)
    state = StateManager(paths)
    builder = ArtifactBuilder(paths, state=state)
    phase = DiscoveryPhase(repo, state, builder)

    result = phase.execute()

    lockfile_gaps = [
        g for g in result.get("gaps", [])
        if g.get("category") == "security" and "Lockfile" in g.get("title", "")
    ]
    assert lockfile_gaps == []
