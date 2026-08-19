"""Unit tests for runtime tooling detection."""
from pathlib import Path

from runtime.tool_detection import ToolDetector


def test_pyright_detected_separately_from_mypy(tmp_path):
    """RUP-TOOL-001: pyright-only configuration must report pyright, not mypy."""
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text("[tool.pyright]\ninclude = ['src']\n", encoding="utf-8")

    detector = ToolDetector(tmp_path)
    assert detector.detect_type_checker() == "pyright"


def test_mypy_detected_when_only_mypy_present(tmp_path):
    """RUP-TOOL-002: mypy-only configuration must report mypy."""
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text("[tool.mypy]\nstrict = true\n", encoding="utf-8")

    detector = ToolDetector(tmp_path)
    assert detector.detect_type_checker() == "mypy"
