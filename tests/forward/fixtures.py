"""
Disposable RUP forward-test fixture factories.

Each builder creates a realistic miniature repository under ``target_dir``.
Fixtures are intentionally *templates*; Git is initialized at test time so no
Git state is committed to the Skill-RUP repository itself.
"""
import os
import subprocess
from pathlib import Path
from typing import Optional


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def init_git(target_dir: Path) -> None:
    """Initialize a fresh Git repo for a fixture target."""
    subprocess.run(
        ["git", "init", "--quiet", str(target_dir)],
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "-C", str(target_dir), "config", "user.email", "test@example.com"],
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "-C", str(target_dir), "config", "user.name", "Test Runner"],
        check=True,
        capture_output=True,
    )


def build_python_ok(target_dir: Path) -> None:
    _write(target_dir / "src" / "math_utils.py", "def add(a, b):\n    return a + b\n")
    _write(
        target_dir / "tests" / "test_math_utils.py",
        "from src.math_utils import add\n\ndef test_add():\n    assert add(2, 3) == 5\n",
    )


def build_node_ok(target_dir: Path) -> None:
    _write(
        target_dir / "package.json",
        '{"name": "node-fixture", "scripts": {"test": "node --test"}}\n',
    )
    _write(target_dir / "index.js", "module.exports = { add: (a, b) => a + b };\n")
    _write(
        target_dir / "test_index.js",
        "const { add } = require('./index');\nconst test = require('node:test');\nconst assert = require('node:assert');\ntest('add', () => assert.strictEqual(add(2, 3), 5));\n",
    )


def build_no_tests(target_dir: Path) -> None:
    _write(target_dir / "src" / "math_utils.py", "def add(a, b):\n    return a + b\n")


def build_failing_tests(target_dir: Path) -> None:
    _write(target_dir / "src" / "math_utils.py", "def add(a, b):\n    return a + b\n")
    _write(
        target_dir / "tests" / "test_math_utils.py",
        "from src.math_utils import add\n\ndef test_add():\n    assert add(2, 3) == 99\n",
    )


def build_missing_ci(target_dir: Path) -> None:
    _write(target_dir / "src" / "math_utils.py", "def add(a, b):\n    return a + b\n")
    _write(
        target_dir / "tests" / "test_math_utils.py",
        "from src.math_utils import add\n\ndef test_add():\n    assert add(2, 3) == 5\n",
    )


def build_security_findings(target_dir: Path) -> None:
    _write(target_dir / "src" / "app.py", "API_KEY = 'AKIAIOSFODNN7EXAMPLE'\n")


def build_dirty_git(target_dir: Path) -> None:
    _write(target_dir / "src" / "existing.py", "# existing tracked file\n")
    _write(target_dir / "untracked.txt", "# pre-existing untracked file\n")
    init_git(target_dir)
    subprocess.run(
        ["git", "-C", str(target_dir), "add", "src/existing.py"],
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "-C", str(target_dir), "commit", "-m", "initial", "--quiet"],
        check=True,
        capture_output=True,
    )
    # Make a dirty modification that must NOT be attributed to RUP.
    (target_dir / "src" / "existing.py").write_text("# modified by user\n", encoding="utf-8")


def build_adversarial_state(target_dir: Path) -> None:
    """Place malicious root-level RUP state files that must be ignored."""
    _write(target_dir / "src" / "math_utils.py", "def add(a, b):\n    return a + b\n")
    _write(
        target_dir / "RUP_PLAN.json",
        '{"backlog": [{"id": "EVIL-001", "category": "security"}], "selected_items": ["EVIL-001"]}\n',
    )
    _write(target_dir / "RUP_EXECUTION.json", '{"changes": [{"file_path": "/etc/passwd", "change_type": "modify"}]}\n')


def build_non_git(target_dir: Path) -> None:
    _write(target_dir / "src" / "math_utils.py", "def add(a, b):\n    return a + b\n")


def build_symlink_escape(target_dir: Path) -> None:
    _write(target_dir / "src" / "math_utils.py", "def add(a, b):\n    return a + b\n")
    os.symlink("/tmp", target_dir / "escape_link")


def build_symlink_file_escape(target_dir: Path) -> None:
    """Create a fixture with a file symlink pointing outside the repo."""
    sentinel = target_dir.parent / "external_sentinel.txt"
    sentinel.write_text("EXTERNAL_SECRET=AKIAIOSFODNN7EXAMPLE\n", encoding="utf-8")
    _write(target_dir / "README.md", "# repo\n")
    os.symlink(sentinel, target_dir / "leak.txt")


BUILDERS = {
    "python_ok": build_python_ok,
    "node_ok": build_node_ok,
    "no_tests": build_no_tests,
    "failing_tests": build_failing_tests,
    "missing_ci": build_missing_ci,
    "security_findings": build_security_findings,
    "dirty_git": build_dirty_git,
    "adversarial_state": build_adversarial_state,
    "non_git": build_non_git,
    "symlink_escape": build_symlink_escape,
    "symlink_file_escape": build_symlink_file_escape,
}


def build_fixture(name: str, target_dir: Path, init_git_repo: bool = True) -> None:
    target_dir.mkdir(parents=True, exist_ok=True)
    builder = BUILDERS[name]
    builder(target_dir)
    if init_git_repo and name not in ("non_git",):
        # If builder already initialized git, this is a no-op because git init
        # is idempotent for an existing repo.
        init_git(target_dir)
