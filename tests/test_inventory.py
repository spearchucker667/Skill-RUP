"""
Tests for runtime/inventory.py language classification and lockfile gap logic.
"""
from pathlib import Path

from runtime.inventory import InventoryManager


def _build_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    return repo


def test_executable_language_percentages_exclude_data_files(tmp_path):
    """RUP-INV-001: percentages are computed only over executable languages."""
    repo = _build_repo(tmp_path)
    (repo / "main.py").write_text("print('hello')\n" * 10, encoding="utf-8")
    (repo / "README.md").write_text("# Title\n" * 50, encoding="utf-8")
    (repo / "package-lock.json").write_text('{"a": "b"}\n' * 30, encoding="utf-8")
    (repo / "poetry.lock").write_text("[[package]]\n", encoding="utf-8")

    inv = InventoryManager(repo).analyze_inventory()

    names = {lang["name"] for lang in inv["languages"]}
    assert "python" in names
    assert "json" not in names
    assert "markdown" not in names
    assert inv["primary_language"] == "python"

    python_entry = next(lang for lang in inv["languages"] if lang["name"] == "python")
    assert python_entry["percentage"] == 100.0
    assert python_entry["lockfile_present"] is True


def test_unknown_language_when_only_data_files(tmp_path):
    """RUP-INV-002: repos with only data/markup files classify as unknown."""
    repo = _build_repo(tmp_path)
    (repo / "README.md").write_text("# Title\n" * 20, encoding="utf-8")
    (repo / "config.yaml").write_text("key: value\n" * 20, encoding="utf-8")

    inv = InventoryManager(repo).analyze_inventory()

    assert inv["primary_language"] == "unknown"
    assert len(inv["languages"]) == 1
    assert inv["languages"][0]["name"] == "unknown"


def test_broad_executable_language_support(tmp_path):
    """RUP-INV-003: additional executable languages are detected."""
    repo = _build_repo(tmp_path)
    (repo / "App.kt").write_text("fun main() {}\n" * 5, encoding="utf-8")
    (repo / "script.swift").write_text("print(\"hi\")\n" * 5, encoding="utf-8")

    inv = InventoryManager(repo).analyze_inventory()
    names = {lang["name"] for lang in inv["languages"]}
    assert "kotlin" in names
    assert "swift" in names
