"""
Tests for runtime/tool_resolution.py offline JS tool resolution (audit P1-18).
"""
import shutil
from pathlib import Path

import pytest

import runtime.tool_resolution as tr


def test_prefers_local_node_modules_bin(tmp_path):
    """The package-local .bin shim wins over every other resolution path."""
    bin_dir = tmp_path / "node_modules" / ".bin"
    bin_dir.mkdir(parents=True)
    shim = bin_dir / "eslint"
    shim.write_text("#!/bin/sh\nexit 0\n")
    shim.chmod(0o755)

    cmd = tr.resolve_js_tool(tmp_path, "eslint", ["."])
    assert cmd[0] == str(shim)
    assert cmd[1:] == ["."]


def test_windows_cmd_shim_preferred(monkeypatch, tmp_path):
    """On Windows the .cmd shim is the local candidate."""
    monkeypatch.setattr("runtime.tool_resolution._windows", lambda: True)
    bin_dir = tmp_path / "node_modules" / ".bin"
    bin_dir.mkdir(parents=True)
    (bin_dir / "jest.cmd").write_text("@echo off\n")

    cmd = tr.resolve_js_tool(tmp_path, "jest")
    assert cmd[0] == str(bin_dir / "jest.cmd")
    assert cmd[1:] == []


def test_npm_lockfile_uses_npm_exec_offline(tmp_path):
    (tmp_path / "package-lock.json").write_text("{}")
    cmd = tr.resolve_js_tool(tmp_path, "tsc", ["--noEmit"])
    assert cmd == ["npm", "exec", "--offline", "--", "tsc", "--noEmit"]


def test_pnpm_lockfile_uses_pnpm_exec(tmp_path):
    (tmp_path / "pnpm-lock.yaml").write_text("lockfileVersion: '9.0'")
    cmd = tr.resolve_js_tool(tmp_path, "vitest", ["run"])
    assert cmd == ["pnpm", "exec", "vitest", "run"]


def test_yarn_lockfile_uses_yarn_exec(tmp_path):
    (tmp_path / "yarn.lock").write_text("# yarn lockfile")
    cmd = tr.resolve_js_tool(tmp_path, "mocha")
    assert cmd == ["yarn", "exec", "mocha"]


def test_no_lockfile_falls_back_to_npx_no_install(monkeypatch, tmp_path):
    monkeypatch.setattr(tr.shutil, "which", lambda name: "/usr/bin/npx" if name == "npx" else None)
    cmd = tr.resolve_js_tool(tmp_path, "eslint", ["."])
    assert cmd == ["npx", "--no-install", "eslint", "."]


def test_no_lockfile_without_npx_uses_bare_tool(monkeypatch, tmp_path):
    monkeypatch.setattr(tr.shutil, "which", lambda name: None)
    cmd = tr.resolve_js_tool(tmp_path, "tsc", ["--noEmit"])
    assert cmd == ["tsc", "--noEmit"]
