"""
Tests for runtime/workspace.py monorepo package graph (audit P1-11).
"""
import json
import subprocess
from pathlib import Path

import pytest

from runtime.workspace import (
    changed_packages,
    dependency_order,
    detect_workspace,
)


def _write_pkg(root: Path, rel: str, name: str, deps: dict | None = None) -> None:
    pkg_dir = root / rel
    pkg_dir.mkdir(parents=True, exist_ok=True)
    (pkg_dir / "package.json").write_text(
        json.dumps({"name": name, "version": "1.0.0", "dependencies": deps or {}}),
        encoding="utf-8",
    )
    (pkg_dir / "index.js").write_text("module.exports = 1;\n", encoding="utf-8")


def test_npm_workspaces_graph(tmp_path):
    """npm workspaces: packages enumerated with internal dependency edges."""
    _write_pkg(tmp_path, "packages/lib-a", "@acme/lib-a")
    _write_pkg(tmp_path, "packages/app-b", "@acme/app-b", {"@acme/lib-a": "workspace:*"})
    (tmp_path / "package.json").write_text(
        json.dumps({"name": "root", "workspaces": ["packages/*"]}),
        encoding="utf-8",
    )

    ws = detect_workspace(tmp_path)
    assert ws is not None
    assert ws["tool"] == "custom"
    assert {p["name"] for p in ws["packages"]} == {"@acme/lib-a", "@acme/app-b"}
    assert ws["graph"]["@acme/app-b"] == ["@acme/lib-a"]
    # External deps are pruned: nothing else points at lib-a.
    assert ws["graph"]["@acme/lib-a"] == []

    by_name = {p["name"]: p for p in ws["packages"]}
    assert by_name["@acme/app-b"]["path"] == "packages/app-b"
    assert by_name["@acme/lib-a"]["type"] == "lib"


def test_cargo_workspace_detection(tmp_path):
    """Cargo workspace members are enumerated with path dependencies."""
    (tmp_path / "crates" / "core").mkdir(parents=True)
    (tmp_path / "crates" / "svc").mkdir(parents=True)
    (tmp_path / "crates" / "core" / "Cargo.toml").write_text(
        '[package]\nname = "core"\nversion = "0.1.0"\n'
    )
    (tmp_path / "crates" / "svc" / "Cargo.toml").write_text(
        '[package]\nname = "svc"\nversion = "0.1.0"\n'
        '[dependencies]\ncore = { path = "../core" }\n'
    )
    (tmp_path / "Cargo.toml").write_text(
        '[workspace]\nmembers = ["crates/*"]\n'
    )

    ws = detect_workspace(tmp_path)
    assert ws is not None
    assert {p["name"] for p in ws["packages"]} == {"core", "svc"}
    assert ws["graph"]["svc"] == ["core"]
    assert next(p for p in ws["packages"] if p["name"] == "svc")["language"] == "rust"


def test_dependency_order_respects_graph():
    graph = {"b": ["a"], "c": ["a", "b"], "a": []}
    ordered = dependency_order(["a", "b", "c"], graph)
    assert ordered.index("a") < ordered.index("b") < ordered.index("c")


def test_dependency_order_breaks_cycle_with_warning():
    graph = {"x": ["y"], "y": ["x"]}
    with pytest.warns(RuntimeWarning, match="cycle"):
        ordered = dependency_order(["x", "y"], graph)
    assert set(ordered) == {"x", "y"}


def test_changed_packages_maps_files_to_packages(tmp_path):
    """Changed-package selection: only packages containing the diff are returned."""
    _write_pkg(tmp_path, "packages/a", "a")
    _write_pkg(tmp_path, "packages/b", "b")
    (tmp_path / "package.json").write_text(
        json.dumps({"name": "root", "workspaces": ["packages/*"]}),
        encoding="utf-8",
    )
    ws = detect_workspace(tmp_path)
    assert ws is not None

    subprocess.run(["git", "init", "--quiet", str(tmp_path)], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(tmp_path), "add", "."], check=True, capture_output=True)
    subprocess.run(
        ["git", "-C", str(tmp_path), "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-m", "init", "--quiet"],
        check=True,
        capture_output=True,
    )

    # No changes: empty set.
    assert changed_packages(tmp_path, ws) == []

    # Change inside package a only.
    (tmp_path / "packages" / "a" / "index.js").write_text("// changed\n", encoding="utf-8")
    assert changed_packages(tmp_path, ws) == ["a"]

    # Root-level change affects the whole workspace.
    (tmp_path / "README.md").write_text("root change\n", encoding="utf-8")
    assert changed_packages(tmp_path, ws) == ["all"]


def test_no_workspace_returns_none(tmp_path):
    assert detect_workspace(tmp_path) is None
