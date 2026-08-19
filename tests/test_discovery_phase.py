"""Unit tests for the RUP discovery phase."""
from pathlib import Path

from runtime.artifact_builder import ArtifactBuilder
from runtime.discovery import DiscoveryPhase
from runtime.paths import RupPaths
from runtime.state import StateManager


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
