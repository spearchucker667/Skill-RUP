"""Tests for runtime security helpers."""
from pathlib import Path

import pytest

from runtime.security import enforce_path_jail, iter_jailed_files


def test_iter_jailed_files_includes_normal_files(tmp_path):
    (tmp_path / "a.py").write_text("x = 1\n", encoding="utf-8")
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "b.py").write_text("y = 2\n", encoding="utf-8")

    found = {str(p.relative_to(tmp_path)) for p in iter_jailed_files(tmp_path)}
    assert "a.py" in found
    assert "sub/b.py" in found


def test_iter_jailed_files_rejects_external_file_symlink(tmp_path):
    sentinel = tmp_path / ".." / "external_sentinel.txt"
    sentinel.write_text("secret\n", encoding="utf-8")
    (tmp_path / "leak.txt").symlink_to(sentinel)

    found = list(iter_jailed_files(tmp_path))
    assert not any("leak" in str(p) for p in found)


def test_iter_jailed_files_rejects_external_directory_symlink(tmp_path):
    external_dir = tmp_path / ".." / "external_dir"
    external_dir.mkdir(exist_ok=True)
    (external_dir / "inside.txt").write_text("secret\n", encoding="utf-8")
    (tmp_path / "link_dir").symlink_to(external_dir)

    found = list(iter_jailed_files(tmp_path))
    assert not any("link_dir" in str(p) for p in found)


def test_iter_jailed_files_honors_skip_parts(tmp_path):
    (tmp_path / "skip" / "ignored.py").parent.mkdir(parents=True)
    (tmp_path / "skip" / "ignored.py").write_text("x\n", encoding="utf-8")
    (tmp_path / "keep.py").write_text("y\n", encoding="utf-8")

    found = {str(p.relative_to(tmp_path)) for p in iter_jailed_files(tmp_path, skip_parts={"skip"})}
    assert "keep.py" in found
    assert "skip/ignored.py" not in found
