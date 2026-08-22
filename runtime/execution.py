"""
Execution phase module for RUP deterministic runtime.
Implements canonical Phase 3 Execution per RUP-EXEC-001..007:
- Subtype-aware workstream dispatch (bug, test_framework, linter, type_checker,
  secret_exposure, security_policy, lockfile, ci, readme, contributing,
  codeowners, license, container, iac, observability)
- Baseline Git status capture and RUP-only change attribution
- Genuine remediation of planned backlog items
- Per-item local verification & change tracking
- Rollback procedure generation
- Exclusion of .rup/ state from repository diffs
"""
import hashlib
import json
import os
import re
import shlex
import sys
import tempfile
import warnings
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from .artifact_builder import ArtifactBuilder
from .command_runner import run_command
from .rollback import render_rollback_commands
from .security import (
    atomic_jailed_write,
    execution_gate_status,
    jailed_mkdir,
    jailed_unlink,
    open_jailed_read,
    read_jailed_text,
    scan_repository_for_threats,
)
from .state import StateManager
from .tool_detection import ToolDetector
from .tool_resolution import resolve_js_tool
from .workspace import changed_packages, dependency_order, detect_workspace

RISK_RANK = {"low": 0, "medium": 1, "high": 2}


class BaselineDirtyRefusal(Exception):
    """Raised when a handler attempts to overwrite a path that was modified in
    the working tree at baseline capture (RUP-EXEC-005). RUP never mutates
    pre-existing user changes; the item is surfaced as AGENT_ONLY instead.
    """


class ExecutionPhase:
    def __init__(
        self,
        target_dir: Path,
        state_manager: StateManager,
        artifact_builder: ArtifactBuilder,
        allow_exec: bool = False,
        sandbox: str = "off",
        override_escalation: bool = False,
        workspace: Optional[str] = None,
        changed_only: bool = False,
    ):
        self.target_dir = target_dir
        self.state_manager = state_manager
        self.artifact_builder = artifact_builder
        self.tool_detector = ToolDetector(target_dir)
        self.allow_exec = allow_exec
        self.sandbox = sandbox
        self.override_escalation = override_escalation
        # Monorepo scoping (audit P1-11): restrict execution to a named package
        # or to packages containing changes, with per-package tooling.
        self.workspace = workspace
        self.changed_only = changed_only
        # Current handler write root: the repository root for unscoped runs, or
        # the scoped package directory (per-package remediation writes).
        self._work_dir = target_dir
        # Transactional rollback state (RUP-EXEC-004/005): baseline dirty paths
        # and content-addressed backups of every pre-write file state.
        self._baseline_dirty_paths: Set[str] = set()
        self._backups: Dict[str, str] = {}
        self._baseline_snapshot: Dict[str, Any] = {
            "is_git": False,
            "head": None,
            "files": {},
        }
        # Discovery metadata (repo_metadata) loaded by execute(); initialized
        # empty so workstream handlers can degrade gracefully in unit tests.
        self.discovery_data: Dict[str, Any] = {}

    # ------------------------------------------------------------------
    # Jailed target I/O helpers (RUP-SEC-001 write side)
    # ------------------------------------------------------------------
    def _capture_content_baseline(self) -> Dict[str, Any]:
        """Capture HEAD and per-path content hashes of baseline-dirty paths.

        Runs before any mutation so rollback knows exactly what the working
        tree looked like at baseline and which paths are user-owned.
        """
        snapshot: Dict[str, Any] = {"is_git": False, "head": None, "files": {}}
        rc, stdout, _ = run_command(["git", "rev-parse", "--is-inside-work-tree"], cwd=self.target_dir)
        if rc == 0 and stdout.strip() == "true":
            snapshot["is_git"] = True
            rc2, head, _ = run_command(["git", "rev-parse", "HEAD"], cwd=self.target_dir)
            if rc2 == 0:
                snapshot["head"] = head.strip()

        dirty_paths: Set[str] = set()
        for entry in self._git_status_entries():
            for p in (entry["path"], entry.get("old_path")):
                if not p or p in dirty_paths:
                    continue
                dirty_paths.add(p)
                abs_path = self.target_dir / p
                try:
                    with open_jailed_read(self.target_dir, abs_path, "rb") as f:
                        data = f.read()
                    snapshot["files"][p] = {
                        "exists": True,
                        "sha256": hashlib.sha256(data).hexdigest(),
                    }
                except (FileNotFoundError, PermissionError):
                    snapshot["files"][p] = {"exists": False, "sha256": None}

        self._baseline_dirty_paths = dirty_paths
        self._baseline_snapshot = snapshot
        return snapshot

    def _refuse_dirty(self, rel_path: str) -> None:
        """Refuse to mutate a path that was dirty at baseline capture."""
        if rel_path in self._baseline_dirty_paths:
            raise BaselineDirtyRefusal(
                f"Refusing to overwrite '{rel_path}': the path was modified in the "
                "working tree at baseline (RUP-EXEC-005). RUP never mutates "
                "pre-existing user changes; resolve the conflict manually."
            )

    def _target_relative(self, rel_path: str) -> str:
        """Map a work-dir-relative path to the target-relative path (for state)."""
        if self._work_dir == self.target_dir:
            return rel_path
        return (self._work_dir.relative_to(self.target_dir) / rel_path).as_posix()

    def _handler_path(self, rel_path: str) -> Path:
        """Resolve a handler-relative path inside the current work directory.

        Unscoped runs use the repository root; ``--workspace`` runs write and
        check paths inside the scoped package directory (audit P1-11).
        """
        return self._work_dir / rel_path

    def _backup_bytes(self, rel_path: str) -> Optional[str]:
        """Snapshot pre-write content of ``rel_path`` into the content-addressed
        backup store under the state directory; returns the SHA-256 or None."""
        abs_path = self._handler_path(rel_path)
        try:
            with open_jailed_read(self.target_dir, abs_path, "rb") as f:
                data = f.read()
        except (FileNotFoundError, PermissionError):
            return None
        sha = hashlib.sha256(data).hexdigest()
        backups_dir = self.state_manager.paths.state_dir / "backups"
        backups_dir.mkdir(parents=True, exist_ok=True)
        dest = backups_dir / sha
        if not dest.exists():
            fd, tmp_path = tempfile.mkstemp(dir=backups_dir, prefix=".rup_b_", suffix=".tmp")
            try:
                with os.fdopen(fd, "wb") as f:
                    f.write(data)
                os.replace(tmp_path, dest)
            except Exception:
                if os.path.exists(tmp_path):
                    os.unlink(tmp_path)
                raise
        return sha

    def _write_target(self, rel_path: str, content: str) -> None:
        """Write a generated file inside the target through the jailed writer.

        Writes inside the current work directory (package-scoped when
        ``--workspace`` is active), refuses baseline-dirty paths, and snapshots
        pre-write content so the file can be restored exactly on rollback.
        """
        self._refuse_dirty(self._target_relative(rel_path))
        target = self._handler_path(rel_path)
        if target.exists() and not target.is_symlink():
            sha = self._backup_bytes(rel_path)
            if sha:
                self._backups[self._target_relative(rel_path)] = sha
        atomic_jailed_write(self.target_dir, target, content)

    def _mkdir_target(self, rel_path: str) -> None:
        """Create a directory inside the work dir through the jailed mkdir."""
        jailed_mkdir(self.target_dir, self._handler_path(rel_path))

    def _read_target_text(self, rel_path: str) -> str:
        """Read a work-dir file through the jailed reader."""
        return read_jailed_text(self.target_dir, self._handler_path(rel_path))

    # ------------------------------------------------------------------
    # Git status helpers
    # ------------------------------------------------------------------
    def _git_status_entries(self) -> List[Dict[str, Optional[str]]]:
        """Parse ``git status --porcelain`` into structured entries."""
        entries: List[Dict[str, Optional[str]]] = []
        rc, stdout, _ = run_command(["git", "status", "--porcelain"], cwd=self.target_dir)
        if rc != 0:
            return entries
        for line in stdout.splitlines():
            if not line.strip():
                continue
            code = line[:2]
            rest = line[3:].strip()
            old_path: Optional[str] = None
            path = rest
            if code.startswith("R") or code.startswith("C"):
                if " -> " in rest:
                    old_path, path = rest.split(" -> ", 1)
                    old_path = old_path.strip()
                    path = path.strip()
            entries.append({"code": code, "path": path, "old_path": old_path})
        return entries

    def _baseline_paths(self) -> Set[str]:
        """Capture all paths mentioned in the baseline Git status."""
        baseline: Set[str] = set()
        for entry in self._git_status_entries():
            baseline.add(entry["path"])
            if entry["old_path"]:
                baseline.add(entry["old_path"])
        return baseline

    @staticmethod
    def _status_to_change_type(code: str) -> str:
        """Map a two-character Git status code to a RUP change type."""
        if code == "??" or "A" in code:
            return "create"
        if "D" in code:
            return "delete"
        if "R" in code:
            return "rename"
        return "modify"

    # ------------------------------------------------------------------
    # Attribution helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _path_matches_category(file_path: str, category: str) -> bool:
        file_path = file_path.replace("\\", "/")
        lower = file_path.lower()
        if category == "tests":
            return (
                file_path.startswith("tests/")
                or file_path.startswith("test/")
                or "/tests/" in file_path
                or lower == "pytest.ini"
                or "jest.config" in lower
                or "vitest.config" in lower
                or "test_" in file_path
            )
        if category == "dx":
            return lower in {
                "ruff.toml",
                ".ruff.toml",
                "mypy.ini",
                ".mypy.ini",
                "pyproject.toml",
                "tsconfig.json",
                ".eslintrc.json",
                ".eslintrc.js",
                ".eslintrc.cjs",
                "eslint.config.js",
                "eslint.config.mjs",
            }
        if category == "ci":
            return (
                file_path.startswith(".github/workflows/")
                or ".gitlab-ci" in lower
                or ".circleci" in file_path
                or "azure-pipelines" in lower
            )
        if category == "docs":
            return (
                lower in {"readme.md", "contributing.md"}
                or file_path.startswith("docs/")
                or lower.endswith(".md")
            )
        if category == "governance":
            return (
                lower in {"license", ".github/codeowners", "codeowners"}
                or lower.endswith("codeowners")
            )
        if category == "security":
            return lower in {"security.md", ".github/security.md"}
        if category == "bugs":
            return False
        return False

    @staticmethod
    def _resolve_completion(
        item_changes: List[Dict[str, Any]], item_recommendations: List[Dict[str, Any]]
    ) -> str:
        """Determine the completion disposition for a single backlog item.

        AGENT_ONLY > NOT_PORTED > PARTIAL > COMPLETE so that any blocker is
        visible in downstream reporting.
        """
        rank = {"COMPLETE": 0, "PARTIAL": 1, "NOT_PORTED": 2, "AGENT_ONLY": 3}
        best = "COMPLETE" if item_changes else "NOT_PORTED"
        for rec in item_recommendations:
            disp = rec.get("disposition", "AGENT_ONLY")
            if rank.get(disp, 0) > rank.get(best, 0):
                best = disp
        return best

    @staticmethod
    def _item_subtype(item: Dict[str, Any]) -> str:
        """Derive the remediation subtype from the backlog item id and title.

        Subtype dispatch is authoritative; category is only used as a fallback
        for legacy or unrecognized items.
        """
        item_id = item.get("id", "")
        title = item.get("title", "")
        category = item.get("category", "")
        lower_title = title.lower()

        # Bugs
        if item_id.startswith("BUG") or category == "bugs":
            return "bug"

        # Tests
        if item_id.startswith("TEST") or category == "tests":
            return "test_framework"

        # Developer experience (lint / type)
        if item_id.startswith("LINT") or (
            category == "dx" and "linter" in lower_title
        ):
            return "linter"
        if item_id.startswith("TYPE") or (
            category == "dx" and "type" in lower_title
        ):
            return "type_checker"

        # Security
        if item_id.startswith("SEC"):
            if item_id == "SEC-001" or "secret" in lower_title:
                return "secret_exposure"
            if item_id.startswith("SEC-1") or "lockfile" in lower_title:
                return "lockfile"
            if "security" in lower_title or "policy" in lower_title:
                return "security_policy"
            return "security"

        # CI/CD
        if item_id.startswith("CI") or category == "ci":
            return "ci"

        # Documentation
        if item_id.startswith("DOCS") or category == "docs":
            if "README" in item_id or "readme" in lower_title:
                return "readme"
            if "CONTRIBUTING" in item_id or "contributing" in lower_title:
                return "contributing"
            return "docs"

        # Governance
        if item_id.startswith("GOV") or category == "governance":
            if "CODEOWNERS" in item_id or "codeowners" in lower_title:
                return "codeowners"
            if "LIC" in item_id or "license" in lower_title:
                return "license"
            return "governance"

        # Containers / IaC / Observability. Gap ids are authoritative because
        # the canonical Gap category enum has no containerization/observability
        # slots (discovery classifies them as performance/dx); category remains
        # the fallback for legacy or explicitly-categorized plans.
        if item_id.startswith("CONT"):
            return "container"
        if item_id.startswith("OBS"):
            return "observability"
        if category in ("containerization", "containers", "container"):
            return "container"
        if category in ("iac", "infrastructure"):
            return "iac"
        if category in ("observability", "monitoring"):
            return "observability"

        return category or "unknown"

    def _attribute_item_id(
        self, file_path: str, selected_items: List[Dict[str, Any]]
    ) -> str:
        for item in selected_items:
            if self._path_matches_category(file_path, item.get("category", "")):
                return item.get("id", "UNASSIGNED")
        if selected_items:
            return selected_items[0].get("id", "UNASSIGNED")
        return "UNASSIGNED"

    @staticmethod
    def _group_changes_by_package(
        changes: List[Dict[str, Any]], ws: Optional[Dict[str, Any]]
    ) -> Dict[str, List[str]]:
        """Group change file paths by workspace package (audit P1-11)."""
        if not ws:
            return {}
        packages = ws.get("packages", [])
        grouped: Dict[str, List[str]] = {}
        for change in changes:
            path = change.get("file_path", "")
            owner = None
            for p in packages:
                prefix = p["path"].rstrip("/") + "/"
                if path == p["path"] or path.startswith(prefix):
                    owner = p["name"]
                    break
            if owner:
                grouped.setdefault(owner, []).append(path)
        return grouped

    # ------------------------------------------------------------------
    # Recommendation helper
    # ------------------------------------------------------------------
    def _recommendation(
        self,
        item_id: str,
        subtype: str,
        disposition: str,
        rationale: str,
    ) -> Dict[str, Any]:
        """Return a non-change workstream disposition for agent follow-up.

        Disposition values:
        - AGENT_ONLY: requires human/agent judgment; cannot be automated safely.
        - PARTIAL: runtime can scaffold or document the fix, but completion
          requires further work.
        - NOT_PORTED: no automated handler exists for this subtype yet.
        """
        return {
            "backlog_item_id": item_id,
            "subtype": subtype,
            "disposition": disposition,
            "rationale": rationale,
        }

    # ------------------------------------------------------------------
    # Workstream handlers
    # ------------------------------------------------------------------
    def _handle_bugs(
        self, item: Dict[str, Any], subtype: str
    ) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        item_id = item.get("id", "")
        recommendation = self._recommendation(
            item_id,
            subtype,
            "AGENT_ONLY",
            "Automated bug remediation requires targeted acceptance criteria; "
            "manual analysis and a dedicated fix plan are needed.",
        )
        return [], [recommendation]

    def _handle_tests(
        self, item: Dict[str, Any], primary_lang: str, subtype: str
    ) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        item_id = item.get("id", "")
        changes: List[Dict[str, Any]] = []
        recommendations: List[Dict[str, Any]] = []
        acceptance = item.get("acceptance_criteria", [])

        # Only emit a concrete test file when acceptance criteria contain
        # specific, automatable expectations. Generic framework criteria are
        # treated as configuration-only scaffolding.
        concrete = bool(acceptance) and any(
            any(
                marker in criterion.lower()
                for marker in ("test_", "assert", "function", "module", "file:")
            )
            for criterion in acceptance
        )

        if primary_lang in ("python", "jupyter notebook"):
            pytest_ini = self._handler_path("pytest.ini")
            if not pytest_ini.exists():
                self._write_target(
                    "pytest.ini",
                    "[pytest]\ntestpaths = tests\npython_files = test_*.py\n",
                )
                changes.append(
                    {
                        "file_path": "pytest.ini",
                        "change_type": "create",
                        "rationale": "Configured baseline pytest configuration",
                        "backlog_item_id": item_id,
                    }
                )
            self._mkdir_target("tests")

            if concrete:
                # Concrete criteria are present, but we still refuse to generate
                # tautological placeholder tests. A recommendation is recorded
                # until a human provides the specific assertions to automate.
                recommendations.append(
                    self._recommendation(
                        item_id,
                        subtype,
                        "AGENT_ONLY",
                        "Concrete acceptance criteria detected, but automated "
                        "test generation requires explicit assertions to avoid "
                        "tautological placeholders.",
                    )
                )
            else:
                recommendations.append(
                    self._recommendation(
                        item_id,
                        subtype,
                        "AGENT_ONLY",
                        "No concrete acceptance criteria available; test code "
                        "must be authored against explicit requirements.",
                    )
                )
        else:
            recommendations.append(
                self._recommendation(
                    item_id,
                    subtype,
                    "AGENT_ONLY",
                    f"Automated test scaffolding for '{primary_lang}' requires "
                    "concrete acceptance criteria to avoid tautological tests.",
                )
            )
        return changes, recommendations

    @staticmethod
    def _detect_default_branch(target_dir: Path) -> str:
        """Return the repository's default branch, falling back to 'main'."""
        try:
            rc, stdout, _ = run_command(
                ["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=target_dir
            )
            if rc == 0 and stdout.strip():
                return stdout.strip()
        except Exception as e:
            warnings.warn(f"Could not detect default branch: {e}", RuntimeWarning, stacklevel=2)
        return "main"

    def _pyproject_is_installable(self, pyproject: Path) -> bool:
        """Return True when pyproject.toml indicates the package is installable."""
        if not pyproject.exists():
            return False
        try:
            text = read_jailed_text(self.target_dir, pyproject)
        except Exception:
            return False
        return any(
            header in text
            for header in ("[project]", "[tool.setuptools]", "[tool.flit", "[tool.poetry]")
        )

    def _handle_ci(
        self, item: Dict[str, Any], primary_lang: str, subtype: str
    ) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        item_id = item.get("id", "")
        changes: List[Dict[str, Any]] = []
        recommendations: List[Dict[str, Any]] = []
        self._mkdir_target(".github/workflows")
        ci_path = self._handler_path(".github/workflows/ci.yml")
        if ci_path.exists():
            return changes, []

        lang = (primary_lang or "unknown").lower()
        tools = self.tool_detector.detect_all()
        default_branch = self._detect_default_branch(self.target_dir)

        supported = {"python", "javascript", "typescript", "rust", "go"}
        if lang not in supported:
            recommendations.append(
                self._recommendation(
                    item_id,
                    subtype,
                    "AGENT_ONLY",
                    f"No CI generator available for primary language '{primary_lang}'; "
                    "author a workflow manually.",
                )
            )
            return changes, recommendations

        if lang in ("javascript", "typescript"):
            build_tool = tools.get("build_tool") or "npm"
            pkg_mgr = build_tool if build_tool in ("npm", "pnpm", "yarn") else "npm"
            if pkg_mgr == "npm":
                install_cmd = "npm ci"
                test_cmd = "npm test"
            elif pkg_mgr == "pnpm":
                install_cmd = "pnpm install --frozen-lockfile"
                test_cmd = "pnpm test"
            else:
                install_cmd = "yarn install --frozen-lockfile"
                test_cmd = "yarn test"
            steps = f"""      - name: Set up Node.js
        uses: actions/setup-node@v4
        with:
          node-version: '20'
      - name: Install dependencies
        run: {install_cmd}
      - name: Run tests
        run: {test_cmd}"""
        elif lang == "rust":
            steps = """      - name: Set up Rust
        uses: actions-rust-lang/setup-rust-toolchain@v1
      - name: Build
        run: cargo build
      - name: Run tests
        run: cargo test"""
        elif lang == "go":
            steps = """      - name: Set up Go
        uses: actions/setup-go@v5
        with:
          go-version: '1.22'
      - name: Build
        run: go build ./...
      - name: Run tests
        run: go test ./..."""
        else:
            # Python-oriented steps.
            installable = self._pyproject_is_installable(self._handler_path("pyproject.toml"))
            install_block = """          python -m pip install --upgrade pip
          if [ -f requirements.txt ]; then pip install -r requirements.txt; fi
          pip install pytest"""
            if installable:
                install_block += "\n          if [ -f pyproject.toml ]; then pip install -e .; fi"
            steps = f"""      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'
      - name: Install dependencies
        run: |
{install_block}
      - name: Run tests
        run: pytest"""

        content = f"""name: CI

on:
  push:
    branches: [{default_branch}]
  pull_request:
    branches: [{default_branch}]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
{steps}
"""
        self._write_target(".github/workflows/ci.yml", content)
        changes.append(
            {
                "file_path": ".github/workflows/ci.yml",
                "change_type": "create",
                "rationale": f"Generated automated CI pipeline for {primary_lang}",
                "backlog_item_id": item_id,
            }
        )
        return changes, recommendations

    def _handle_readme(
        self, item: Dict[str, Any], meta: Dict[str, Any], subtype: str
    ) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        item_id = item.get("id", "")
        changes: List[Dict[str, Any]] = []
        repo_name = meta.get("name", "Project")
        repo_type = meta.get("repo_type", "Application")

        readme_path = self._handler_path("README.md")
        if not readme_path.exists():
            content = f"""# {repo_name}

{repo_type.title()} codebase.

## Overview
Automated repository managed with RUP Protocol standards.

## Installation
Refer to language-specific package manifests for setup instructions.

## Development & Testing
Run tests locally prior to submitting pull requests.

## License
Refer to the [LICENSE](LICENSE) file for distribution terms.
"""
            self._write_target("README.md", content)
            changes.append(
                {
                    "file_path": "README.md",
                    "change_type": "create",
                    "rationale": "Generated standardized README documentation",
                    "backlog_item_id": item_id,
                }
            )
        return changes, []

    def _handle_contributing(
        self, item: Dict[str, Any], subtype: str
    ) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        item_id = item.get("id", "")
        changes: List[Dict[str, Any]] = []
        contrib_path = self._handler_path("CONTRIBUTING.md")
        if not contrib_path.exists():
            content = """# Contributing Guidelines

Thank you for contributing!

## Pull Request Process
1. Ensure all tests and linters pass before opening a pull request.
2. Follow Conventional Commits format (`feat:`, `fix:`, `docs:`, `chore:`).
3. Update documentation for any user-facing changes.
"""
            self._write_target("CONTRIBUTING.md", content)
            changes.append(
                {
                    "file_path": "CONTRIBUTING.md",
                    "change_type": "create",
                    "rationale": "Added contributor guidelines",
                    "backlog_item_id": item_id,
                }
            )
        return changes, []

    def _handle_codeowners(
        self, item: Dict[str, Any], subtype: str
    ) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        item_id = item.get("id", "")
        changes: List[Dict[str, Any]] = []

        codeowners_path = self._handler_path(".github/CODEOWNERS")
        if not codeowners_path.exists() and not self._handler_path("CODEOWNERS").exists():
            self._mkdir_target(".github")
            content = """# CODEOWNERS
# Replace the examples below with real GitHub usernames or team names.
# See https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/customizing-your-repository/about-code-owners
# * @owner
# src/ @team-frontend
# docs/ @team-docs
"""
            self._write_target(".github/CODEOWNERS", content)
            changes.append(
                {
                    "file_path": ".github/CODEOWNERS",
                    "change_type": "create",
                    "rationale": "Created CODEOWNERS file with instructions for real identities",
                    "backlog_item_id": item_id,
                }
            )
        return changes, []

    def _handle_license(
        self, item: Dict[str, Any], subtype: str
    ) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        item_id = item.get("id", "")
        changes: List[Dict[str, Any]] = []
        recommendations: List[Dict[str, Any]] = []

        lic_path = self._handler_path("LICENSE")
        if not lic_path.exists():
            template_path = self.state_manager.paths.get_skill_path(
                "templates", "LICENSE-APACHE-2.0.txt"
            )
            if template_path.exists():
                self._write_target(
                    "LICENSE", template_path.read_text(encoding="utf-8")
                )
                changes.append(
                    {
                        "file_path": "LICENSE",
                        "change_type": "create",
                        "rationale": "Installed complete Apache-2.0 license text",
                        "backlog_item_id": item_id,
                    }
                )
            else:
                recommendations.append(
                    self._recommendation(
                        item_id,
                        subtype,
                        "AGENT_ONLY",
                        "No bundled full Apache-2.0 license text found; "
                        "explicit license selection is required before committing a LICENSE file.",
                    )
                )
        return changes, recommendations

    def _handle_security_policy(
        self, item: Dict[str, Any], subtype: str
    ) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        item_id = item.get("id", "")
        changes: List[Dict[str, Any]] = []
        sec_path = self._handler_path("SECURITY.md")
        if not sec_path.exists() and not self._handler_path(".github/SECURITY.md").exists():
            content = """# Security Policy

## Supported Versions
We actively support security fixes for the current release.

## Reporting a Vulnerability
Please report security vulnerabilities responsibly using GitHub private
vulnerability reporting:

https://github.com/OWNER/REPO/security/advisories/new

Replace `OWNER/REPO` with the actual repository coordinates. Do not open a
public issue for security-sensitive findings.
"""
            self._write_target("SECURITY.md", content)
            changes.append(
                {
                    "file_path": "SECURITY.md",
                    "change_type": "create",
                    "rationale": "Added security disclosure policy pointing to GitHub private vulnerability reporting",
                    "backlog_item_id": item_id,
                }
            )
        return changes, []

    def _handle_secret_exposure(
        self, item: Dict[str, Any], subtype: str
    ) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        item_id = item.get("id", "")
        return [], [
            self._recommendation(
                item_id,
                subtype,
                "AGENT_ONLY",
                "Exposed secrets require manual verification, credential rotation, "
                "and git-history cleanup before any automated change can be applied.",
            )
        ]

    def _handle_lockfile(
        self, item: Dict[str, Any], subtype: str
    ) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        item_id = item.get("id", "")
        return [], [
            self._recommendation(
                item_id,
                subtype,
                "PARTIAL",
                "Lockfile generation is environment-specific; run the appropriate "
                "package manager (npm install, poetry lock, cargo generate-lockfile, etc.) "
                "and commit the resulting lockfile.",
            )
        ]

    def _handle_linter(
        self, item: Dict[str, Any], primary_lang: str, subtype: str
    ) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        item_id = item.get("id", "")
        changes: List[Dict[str, Any]] = []
        lang = (primary_lang or "unknown").lower()

        if lang in ("javascript", "typescript"):
            eslint_path = self._handler_path(".eslintrc.json")
            if not eslint_path.exists():
                self._write_target(
                    ".eslintrc.json",
                    json.dumps(
                        {
                            "env": {"browser": True, "es2021": True, "node": True},
                            "extends": "eslint:recommended",
                            "parserOptions": {"ecmaVersion": "latest"},
                            "rules": {},
                        },
                        indent=2,
                    )
                    + "\n",
                )
                changes.append(
                    {
                        "file_path": ".eslintrc.json",
                        "change_type": "create",
                        "rationale": "Generated baseline ESLint configuration",
                        "backlog_item_id": item_id,
                    }
                )
        elif lang == "python":
            ruff_path = self._handler_path("ruff.toml")
            if not ruff_path.exists() and not self._handler_path("pyproject.toml").exists():
                self._write_target(
                    "ruff.toml",
                    "[lint]\nselect = ['E', 'F', 'I']\nignore = []\n",
                )
                changes.append(
                    {
                        "file_path": "ruff.toml",
                        "change_type": "create",
                        "rationale": "Generated baseline ruff linter configuration",
                        "backlog_item_id": item_id,
                    }
                )
        return changes, []

    def _handle_type_checker(
        self, item: Dict[str, Any], primary_lang: str, subtype: str
    ) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        item_id = item.get("id", "")
        changes: List[Dict[str, Any]] = []
        lang = (primary_lang or "unknown").lower()

        if lang == "typescript":
            tsconfig_path = self._handler_path("tsconfig.json")
            if not tsconfig_path.exists():
                self._write_target(
                    "tsconfig.json",
                    json.dumps(
                        {
                            "compilerOptions": {
                                "target": "ES2020",
                                "module": "commonjs",
                                "strict": True,
                                "esModuleInterop": True,
                                "skipLibCheck": True,
                                "forceConsistentCasingInFileNames": True,
                            },
                            "include": ["src/**/*"],
                        },
                        indent=2,
                    )
                    + "\n",
                )
                changes.append(
                    {
                        "file_path": "tsconfig.json",
                        "change_type": "create",
                        "rationale": "Generated baseline TypeScript compiler configuration",
                        "backlog_item_id": item_id,
                    }
                )
        elif lang == "python":
            mypy_path = self._handler_path("mypy.ini")
            if not mypy_path.exists():
                self._write_target(
                    "mypy.ini",
                    "[mypy]\npython_version = 3.11\nwarn_return_any = True\nwarn_unused_configs = True\n",
                )
                changes.append(
                    {
                        "file_path": "mypy.ini",
                        "change_type": "create",
                        "rationale": "Generated baseline mypy configuration",
                        "backlog_item_id": item_id,
                    }
                )
        return changes, []

    # Canonical Phase-2 containerization workstream (ws_containers). The
    # Dockerfile and Compose templates below mirror protocol/rup-protocol.yaml
    # `phases.2.workstreams.containerization` with per-language parameter
    # substitution; generation is deterministic and additive (never overwrites
    # an existing Dockerfile / .dockerignore / docker-compose.yml).
    _CONTAINER_LANG_MAP: Dict[str, Dict[str, str]] = {
        "python": {
            "base_image": "python:3.12-slim",
            "lockfile": "requirements.txt",
            "install_command": "pip install --no-cache-dir -r requirements.txt",
            "build_command": "python -m compileall -q .",
            "runtime_image": "python:3.12-slim",
            "artifact": "",
            "port": "8000",
            "health_check_command": "python -c \"import urllib.request; urllib.request.urlopen('http://localhost:8000/health', timeout=5)\"",
            "entrypoint": "python app.py",
        },
        "javascript": {
            "base_image": "node:20-alpine",
            "lockfile": "package-lock.json",
            "install_command": "npm ci",
            "build_command": "npm run build",
            "runtime_image": "node:20-alpine",
            "artifact": "",
            "port": "8080",
            "health_check_command": "wget --no-verbose --tries=1 --spider http://localhost:8080/health",
            "entrypoint": "npm start",
        },
        "typescript": {
            "base_image": "node:20-alpine",
            "lockfile": "package-lock.json",
            "install_command": "npm ci",
            "build_command": "npm run build",
            "runtime_image": "node:20-alpine",
            "artifact": "dist",
            "port": "8080",
            "health_check_command": "wget --no-verbose --tries=1 --spider http://localhost:8080/health",
            "entrypoint": "npm start",
        },
        "rust": {
            "base_image": "rust:1.80-slim",
            "lockfile": "Cargo.lock",
            "install_command": "cargo build --release",
            "build_command": "cargo build --release",
            "runtime_image": "debian:bookworm-slim",
            "artifact": "target/release/app",
            "port": "8080",
            "health_check_command": "curl --fail http://localhost:8080/health",
            "entrypoint": "./app",
        },
        "go": {
            "base_image": "golang:1.22-alpine",
            "lockfile": "go.sum",
            "install_command": "go mod download",
            "build_command": "go build -o /app/bin/app .",
            "runtime_image": "alpine:3.20",
            "artifact": "bin/app",
            "port": "8080",
            "health_check_command": "wget --no-verbose --tries=1 --spider http://localhost:8080/health",
            "entrypoint": "./app",
        },
    }

    _DOCKERIGNORE_TEMPLATE = (
        "# Dependency directories\n"
        "node_modules/\n"
        "vendor/\n"
        "__pycache__/\n"
        ".venv/\n"
        "\n"
        "# Build artifacts\n"
        "dist/\n"
        "build/\n"
        "target/\n"
        "*.py[cod]\n"
        "\n"
        "# Test and coverage output\n"
        ".pytest_cache/\n"
        ".coverage\n"
        "coverage.xml\n"
        "\n"
        "# Version control and local state\n"
        ".git/\n"
        ".gitignore\n"
        ".rup/\n"
        ".env\n"
        ".DS_Store\n"
    )

    _DOCKERFILE_TEMPLATE = (
        "# syntax=docker/dockerfile:1\n"
        "\n"
        "# Build stage\n"
        "FROM {base_image} AS builder\n"
        "WORKDIR /app\n"
        "COPY {lockfile} .\n"
        "RUN {install_command}\n"
        "COPY . .\n"
        "RUN {build_command}\n"
        "\n"
        "# Runtime stage\n"
        "FROM {runtime_image}\n"
        "{user_setup}"
        "USER appuser\n"
        "WORKDIR /app\n"
        "{copy_artifact}"
        "EXPOSE {port}\n"
        "HEALTHCHECK --interval=30s --timeout=3s \\\n"
        "  CMD {health_check_command}\n"
        "CMD [\"{entrypoint}\"]\n"
    )

    _COMPOSE_TEMPLATE = (
        "services:\n"
        "  app:\n"
        "    build: .\n"
        "    ports:\n"
        "      - \"{port}:{port}\"\n"
        "    environment:\n"
        "      - APP_ENV=production\n"
        "    restart: unless-stopped\n"
        "    healthcheck:\n"
        "      test: [\"CMD-SHELL\", \"{health_check_command}\"]\n"
        "      interval: 30s\n"
        "      timeout: 10s\n"
        "      retries: 3\n"
    )

    def _handle_container(
        self, item: Dict[str, Any], subtype: str
    ) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        """Generate a canonical multi-stage Dockerfile plus supporting files.

        Follows the canonical ``ws_containers`` workstream (multi-stage builds,
        non-root user, health checks, .dockerignore) with per-language
        parameters. Never overwrites an existing Dockerfile / .dockerignore /
        docker-compose.yml. Unsupported languages and non-application repos are
        routed to AGENT_ONLY instead of being scaffolded blindly.
        """
        item_id = item.get("id", "")
        meta = self.discovery_data.get("repo_metadata", {})
        primary_lang = str(meta.get("primary_language", "python") or "python").lower()
        params = self._CONTAINER_LANG_MAP.get(primary_lang)
        if params is None:
            return [], [
                self._recommendation(
                    item_id,
                    subtype,
                    "AGENT_ONLY",
                    f"No Dockerfile generator for primary language '{primary_lang}'; "
                    "author the container definition manually.",
                )
            ]

        changes: List[Dict[str, Any]] = []

        # Dockerfile (skip silently when present: user-authored config wins).
        dockerfile_path = self._handler_path("Dockerfile")
        if not dockerfile_path.exists():
            copy_artifact = (
                f"COPY --from=builder /app/{params['artifact']} ./\n"
                if params["artifact"]
                else "COPY --from=builder /app .\n"
            )
            # Canonical best practice: non-root runtime user. Alpine bases use
            # adduser; Debian-based bases use useradd.
            user_setup = (
                "RUN addgroup -S appuser && adduser -S -G appuser appuser\n"
                if "alpine" in params["runtime_image"]
                else "RUN useradd --create-home --shell /usr/sbin/nologin appuser\n"
            )
            dockerfile = self._DOCKERFILE_TEMPLATE.format(
                base_image=params["base_image"],
                lockfile=params["lockfile"],
                install_command=params["install_command"],
                build_command=params["build_command"],
                runtime_image=params["runtime_image"],
                copy_artifact=copy_artifact,
                user_setup=user_setup,
                port=params["port"],
                health_check_command=params["health_check_command"],
                entrypoint=params["entrypoint"],
            )
            self._write_target("Dockerfile", dockerfile)
            changes.append(
                {
                    "file_path": "Dockerfile",
                    "change_type": "create",
                    "rationale": (
                        "Generated multi-stage Dockerfile from canonical ws_containers template "
                        "(non-root runtime, pinned deps, health check)"
                    ),
                    "backlog_item_id": item_id,
                }
            )

        # .dockerignore (additive baseline; never overwrite).
        di_path = self._handler_path(".dockerignore")
        if not di_path.exists():
            self._write_target(".dockerignore", self._DOCKERIGNORE_TEMPLATE)
            changes.append(
                {
                    "file_path": ".dockerignore",
                    "change_type": "create",
                    "rationale": "Generated .dockerignore minimizing build context",
                    "backlog_item_id": item_id,
                }
            )

        # docker-compose.yml (only when the repo looks like an application).
        repo_type = str(meta.get("repo_type", "application") or "application").lower()
        compose_path = self._handler_path("docker-compose.yml")
        if repo_type != "library" and not compose_path.exists():
            self._write_target(
                "docker-compose.yml",
                self._COMPOSE_TEMPLATE.format(
                    port=params["port"],
                    health_check_command=params["health_check_command"],
                ),
            )
            changes.append(
                {
                    "file_path": "docker-compose.yml",
                    "change_type": "create",
                    "rationale": "Generated Compose scaffold from canonical ws_containers template",
                    "backlog_item_id": item_id,
                }
            )

        recommendations = [
            self._recommendation(
                item_id,
                subtype,
                "PARTIAL",
                "Scaffolded canonical Dockerfile/.dockerignore/Compose baseline; "
                "confirm the health check path and entrypoint against the application.",
            )
        ]
        return changes, recommendations

    def _handle_iac(
        self, item: Dict[str, Any], subtype: str
    ) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        item_id = item.get("id", "")
        return [], [
            self._recommendation(
                item_id,
                subtype,
                "NOT_PORTED",
                "Infrastructure-as-Code generation is not ported to the deterministic runtime; "
                "author manually or extend the runtime with an IaC workstream handler.",
            )
        ]

    # Canonical Phase-2 observability workstream (ws_observability): JSON
    # structured logging, standard RED/USE metrics, and OpenTelemetry tracing
    # with W3C Trace Context, per protocol/rup-protocol.yaml
    # `phases.2.workstreams.observability`. The handler emits a deterministic
    # baseline document and per-language configuration scaffold.
    _OBSERVABILITY_BASELINE = (
        "# Observability Baseline\n"
        "\n"
        "Generated from the canonical RUP `ws_observability` workstream. Adopt the "
        "standards below so logs, metrics, and traces share one correlation model.\n"
        "\n"
        "## Logging\n"
        "\n"
        "- Format: **JSON structured logging** with one event per line.\n"
        "- Required fields: `timestamp`, `level`, `message`, `service`, `trace_id`, `span_id`; "
        "add `duration_ms` for request-scoped events.\n"
        "- Example:\n"
        "\n"
        "```json\n"
        "{\"timestamp\":\"2025-01-18T12:00:00Z\",\"level\":\"info\",\"message\":\"Request processed\","
        "\"service\":\"api\",\"trace_id\":\"abc123\",\"span_id\":\"def456\",\"duration_ms\":42}\n"
        "```\n"
        "\n"
        "## Metrics\n"
        "\n"
        "Standard instrument set:\n"
        "\n"
        "- `request_count` (counter)\n"
        "- `request_duration_seconds` (histogram)\n"
        "- `error_count` (counter)\n"
        "- `active_connections` (gauge)\n"
        "\n"
        "## Tracing\n"
        "\n"
        "- Standard: **OpenTelemetry**\n"
        "- Propagation: **W3C Trace Context** (`traceparent` header)\n"
        "- Logs, metrics, and traces must share the same `trace_id`/`span_id`.\n"
    )

    def _handle_observability(
        self, item: Dict[str, Any], subtype: str
    ) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        """Emit a canonical observability baseline (logging/metrics/tracing).

        Deterministic scaffolding only: the document and per-language notes are
        generated, while runtime instrumentation remains a manual/agent step,
        so the workstream is reported PARTIAL rather than fully ported.
        """
        item_id = item.get("id", "")
        meta = self.discovery_data.get("repo_metadata", {})
        primary_lang = str(meta.get("primary_language", "python") or "python").lower()
        changes: List[Dict[str, Any]] = []

        obs_path = self._handler_path("docs/observability.md")
        if not obs_path.exists():
            self._mkdir_target("docs")
            content = self._OBSERVABILITY_BASELINE
            if primary_lang in ("javascript", "typescript"):
                content += (
                    "\n## Language Notes (Node.js)\n\n"
                    "- JSON logging: `pino` (or `bunyan`); export `trace_id`/`span_id` on every record.\n"
                    "- Metrics: `prom-client` with the standard instrument set above.\n"
                    "- Tracing: `@opentelemetry/sdk-node` + `@opentelemetry/instrumentation-http`; "
                    "enable W3C propagator.\n"
                )
            elif primary_lang == "python":
                content += (
                    "\n## Language Notes (Python)\n\n"
                    "- JSON logging: `structlog` or `python-json-logger`; bind `service`, `trace_id`, `span_id`.\n"
                    "- Metrics: `prometheus-client`.\n"
                    "- Tracing: `opentelemetry-sdk` + `opentelemetry-instrumentation-flask/fastapi`; "
                    "W3C propagator enabled by default.\n"
                )
            elif primary_lang == "go":
                content += (
                    "\n## Language Notes (Go)\n\n"
                    "- JSON logging: `slog` with `slog.NewJSONHandler`.\n"
                    "- Metrics: `prometheus/client_golang`.\n"
                    "- Tracing: `go.opentelemetry.io/otel` with `otelhttp` middleware.\n"
                )
            elif primary_lang == "rust":
                content += (
                    "\n## Language Notes (Rust)\n\n"
                    "- JSON logging: `tracing` with `tracing-subscriber` JSON formatter.\n"
                    "- Metrics: `metrics` or `prometheus` crate.\n"
                    "- Tracing: `tracing-opentelemetry` + `opentelemetry-otlp`.\n"
                )
            self._write_target("docs/observability.md", content)
            changes.append(
                {
                    "file_path": "docs/observability.md",
                    "change_type": "create",
                    "rationale": (
                        "Generated canonical observability baseline: JSON structured logging, "
                        "standard metrics, OpenTelemetry tracing with W3C Trace Context"
                    ),
                    "backlog_item_id": item_id,
                }
            )

        recommendations = [
            self._recommendation(
                item_id,
                subtype,
                "PARTIAL",
                "Generated observability baseline (logging/metrics/tracing standards); "
                "wire runtime instrumentation into the application code.",
            )
        ]
        return changes, recommendations

    def _execute_workstream_item(
        self, item: Dict[str, Any], discovery_data: Dict[str, Any]
    ) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        """Implement remediation for a specific backlog item.

        Returns a tuple of (file_changes, recommendations) so that guidance,
        partial work, and not-yet-ported subtypes are recorded without being
        treated as repository changes.
        """
        subtype = self._item_subtype(item)
        meta = discovery_data.get("repo_metadata", {})
        primary_lang = meta.get("primary_language", "python")

        if subtype == "bug":
            return self._handle_bugs(item, subtype)
        if subtype == "test_framework":
            return self._handle_tests(item, primary_lang, subtype)
        if subtype == "linter":
            return self._handle_linter(item, primary_lang, subtype)
        if subtype == "type_checker":
            return self._handle_type_checker(item, primary_lang, subtype)
        if subtype == "secret_exposure":
            return self._handle_secret_exposure(item, subtype)
        if subtype == "security_policy":
            return self._handle_security_policy(item, subtype)
        if subtype == "lockfile":
            return self._handle_lockfile(item, subtype)
        if subtype == "ci":
            return self._handle_ci(item, primary_lang, subtype)
        if subtype == "readme":
            return self._handle_readme(item, meta, subtype)
        if subtype == "contributing":
            return self._handle_contributing(item, subtype)
        if subtype == "codeowners":
            return self._handle_codeowners(item, subtype)
        if subtype == "license":
            return self._handle_license(item, subtype)
        if subtype == "container":
            return self._handle_container(item, subtype)
        if subtype == "iac":
            return self._handle_iac(item, subtype)
        if subtype == "observability":
            return self._handle_observability(item, subtype)

        item_id = item.get("id", "")
        return [], [
            self._recommendation(
                item_id,
                subtype,
                "NOT_PORTED",
                f"No deterministic handler available for subtype '{subtype}'.",
            )
        ]

    # ------------------------------------------------------------------
    # Baseline coverage / test counts (before changes are applied)
    # ------------------------------------------------------------------
    @staticmethod
    def _parse_test_counts(stdout: str, stderr: str, rc: int) -> Tuple[int, int, int]:
        combined = stdout + "\n" + stderr
        m_pass = re.search(r"(\d+)\s+passed", combined)
        m_fail = re.search(r"(\d+)\s+failed", combined)
        m_skip = re.search(r"(\d+)\s+skipped", combined)
        m_collected = re.search(r"collected\s+(\d+)\s+item", combined, re.IGNORECASE)

        passed = int(m_pass.group(1)) if m_pass else 0
        failed = int(m_fail.group(1)) if m_fail else 0
        skipped = int(m_skip.group(1)) if m_skip else 0
        collected = int(m_collected.group(1)) if m_collected else (passed + failed + skipped)

        if passed == 0 and failed == 0 and rc == 0:
            passed = 1
        if failed == 0 and rc != 0:
            failed = 1

        return passed, failed, skipped, collected

    def _collect_baseline_coverage(self) -> Dict[str, Any]:
        """Run tests with coverage before changes to establish a true before/after delta."""
        tools = self.tool_detector.detect_all()
        framework = tools.get("test_framework")
        test_cmd = self._test_command(framework)
        if not test_cmd:
            return {"coverage_before": None, "tests_before": 0}

        coverage_before: Optional[float] = None
        tests_before = 0

        if framework == "pytest":
            cov_cmd = [sys.executable, "-m", "coverage", "run", "--source=.", "-m", "pytest", "-q"]
            rc, stdout, stderr = run_command(cov_cmd, cwd=self.target_dir, timeout=180)
            if rc == 0:
                rc2, stdout2, _ = run_command(
                    [sys.executable, "-m", "coverage", "report"],
                    cwd=self.target_dir,
                    timeout=60,
                )
                if rc2 == 0:
                    for line in reversed(stdout2.splitlines()):
                        parts = line.split()
                        if parts and parts[0] == "TOTAL":
                            try:
                                coverage_before = float(parts[-1].replace("%", ""))
                            except ValueError:
                                pass
                            break
            passed, failed, skipped, collected = self._parse_test_counts(stdout, stderr, rc)
            tests_before = collected
        elif framework in ("jest", "vitest", "mocha", "npm-test") or tools.get("build_tool") in ("npm", "pnpm", "yarn"):
            build_tool = tools.get("build_tool")
            pkg_mgr = build_tool if build_tool in ("npm", "pnpm", "yarn") else "npm"
            if test_cmd and test_cmd[0] == pkg_mgr and test_cmd[1:] == ["test"]:
                cov_cmd = test_cmd + ["--", "--coverage"]
            else:
                cov_cmd = test_cmd + ["--coverage"]
            rc, stdout, stderr = run_command(cov_cmd, cwd=self.target_dir, timeout=180)
            if rc == 0:
                combined = stdout + "\n" + stderr
                m = re.search(
                    r"All files\s*\|[\s\d.]+\|[\s\d.]+\|[\s\d.]+\|\s*([\d.]+)%",
                    combined,
                )
                if m:
                    coverage_before = float(m.group(1))
                else:
                    m = re.search(r"Statements\s*:\s*([\d.]+)%", combined)
                    if m:
                        coverage_before = float(m.group(1))
            passed, failed, skipped, collected = self._parse_test_counts(stdout, stderr, rc)
            tests_before = collected

        # Best-effort cleanup of temporary coverage files (jailed so cleanup can
        # never delete files outside the target through redirected paths).
        for cov_file in self.target_dir.glob(".coverage*"):
            try:
                jailed_unlink(self.target_dir, cov_file)
            except Exception:  # nosec B110
                pass

        return {"coverage_before": coverage_before, "tests_before": tests_before}

    # ------------------------------------------------------------------
    # Local verification
    # ------------------------------------------------------------------
    def _test_command(self, framework: Optional[str]) -> Optional[List[str]]:
        if framework == "pytest":
            return ["python", "-m", "pytest"]
        if framework == "jest":
            return resolve_js_tool(self._work_dir, "jest")
        if framework == "vitest":
            return resolve_js_tool(self._work_dir, "vitest", ["run"])
        if framework == "mocha":
            return resolve_js_tool(self._work_dir, "mocha")
        if framework == "npm-test":
            return ["npm", "test"]
        if framework == "cargo test":
            return ["cargo", "test"]
        if framework == "go test":
            return ["go", "test", "./..."]
        return None

    def _lint_command(self, linter: Optional[str]) -> Optional[List[str]]:
        if linter == "ruff":
            return ["ruff", "check", "."]
        if linter == "flake8":
            return ["flake8"]
        if linter == "eslint":
            return resolve_js_tool(self._work_dir, "eslint", ["."])
        if linter == "clippy":
            return ["cargo", "clippy"]
        if linter == "golangci-lint":
            return ["golangci-lint", "run"]
        return None

    def _type_check_command(self, type_checker: Optional[str]) -> Optional[List[str]]:
        if type_checker == "mypy":
            return ["mypy", "."]
        if type_checker == "tsc":
            return resolve_js_tool(self._work_dir, "tsc", ["--noEmit"])
        return None

    def _build_command(
        self, build_tool: Optional[str], target_dir: Path
    ) -> Optional[List[str]]:
        if build_tool in ("npm", "pnpm", "yarn"):
            pkg = target_dir / "package.json"
            if pkg.exists():
                try:
                    data = json.loads(read_jailed_text(self.target_dir, pkg))
                    if "build" in data.get("scripts", {}):
                        runner = "pnpm" if build_tool == "pnpm" else ("yarn" if build_tool == "yarn" else "npm")
                        return [runner, "run", "build"]
                except Exception as e:
                    warnings.warn(f"Could not parse package.json for build script: {e}", RuntimeWarning, stacklevel=2)
            return None
        if build_tool == "cargo":
            return ["cargo", "build"]
        if build_tool == "go":
            return ["go", "build", "./..."]
        return None

    def _run_verification_gate(
        self, tool: Optional[str], command: Optional[List[str]]
    ) -> Dict[str, Any]:
        if not tool or not command:
            return {
                "executed": False,
                "passed": False,
                "tool": tool,
                "details": "Tool not detected or no applicable command",
            }
        rc, stdout, stderr = run_command(command, cwd=self.target_dir)
        executed = True
        passed = rc == 0
        details = (stdout.strip() + "\n" + stderr.strip()).strip()
        if not details:
            details = f"Command exited with code {rc}"
        return {
            "executed": executed,
            "passed": passed,
            "tool": tool,
            "details": details[:2000],
        }

    def _run_checkpoint_gate(
        self, method: str, tools: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Run the single targeted gate for a workstream checkpoint (audit P1-13)."""
        if method == "test":
            return self._run_verification_gate(
                tools.get("test_framework"),
                self._test_command(tools.get("test_framework")),
            )
        if method == "lint":
            return self._run_verification_gate(
                tools.get("linter"), self._lint_command(tools.get("linter"))
            )
        if method == "type_check":
            return self._run_verification_gate(
                tools.get("type_checker"),
                self._type_check_command(tools.get("type_checker")),
            )
        # Non-executable methods (existence, file_validation, scan) are validated
        # by the presence of the workstream's change records; no target command
        # is executed for them.
        return {
            "executed": False,
            "passed": None,
            "status": "not_applicable",
            "method": method,
            "details": "Non-executable checkpoint; validated by change record existence.",
        }

    def _enforce_item_checkpoint(
        self, method: str, tools: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Enforce one item's checkpoint and return its structured result."""
        result = self._run_checkpoint_gate(method, tools)
        if result.get("status") == "not_applicable":
            return {
                "method": method,
                "status": "not_applicable",
                "passed": True,
                "details": result.get("details", ""),
            }
        passed = result.get("passed") is True and result.get("command_succeeded") is not False
        return {
            "method": method,
            "status": "passed" if passed else "failed",
            "passed": passed,
            "tool": result.get("tool"),
            "details": (result.get("details") or "")[:500],
        }

    def _verify_item(
        self, item: Dict[str, Any], tools: Dict[str, Any]
    ) -> Dict[str, Any]:
        return {
            "tests": self._run_verification_gate(
                tools.get("test_framework"),
                self._test_command(tools.get("test_framework")),
            ),
            "lint": self._run_verification_gate(
                tools.get("linter"), self._lint_command(tools.get("linter"))
            ),
            "type_check": self._run_verification_gate(
                tools.get("type_checker"),
                self._type_check_command(tools.get("type_checker")),
            ),
            "build": self._run_verification_gate(
                tools.get("build_tool"),
                self._build_command(tools.get("build_tool"), self.target_dir),
            ),
        }

    def _blocked_verification(self, reason: Optional[str]) -> Dict[str, Any]:
        """Return an explicit non-executed verification shape when the trust gate refuses."""
        detail = reason or "Target-controlled commands refused by execution trust gate"
        gates: Dict[str, Any] = {}
        for name in ("tests", "lint", "type_check", "build"):
            gates[name] = {
                "executed": False,
                "passed": False,
                "tool": None,
                "details": detail,
            }
        return gates

    # ------------------------------------------------------------------
    # Rollback
    # ------------------------------------------------------------------
    @staticmethod
    def _is_config_file(file_path: str) -> bool:
        lower = file_path.lower()
        return (
            file_path.startswith(".github/workflows/")
            or lower in {"pytest.ini", ".pre-commit-config.yaml", "pyproject.toml", "package.json", "tsconfig.json"}
            or lower.endswith("codeowners")
            or file_path.startswith(".github/")
        )

    def _build_rollback(
        self, changes: List[Dict[str, Any]], baseline_paths: Set[str]
    ) -> Dict[str, Any]:
        """Build the single platform-neutral rollback representation.

        Every operation is semantic (restore_content / remove_file /
        restore_deleted / move_back), carries its owning backlog item, and
        records the baseline content hash where applicable, so per-item and
        whole-run rollback share one source of truth (audit P1-28).
        """
        created: List[str] = []
        modified: List[str] = []
        deleted: List[str] = []
        renamed: List[Dict[str, Any]] = []
        config_changed: List[str] = []

        for change in changes:
            ctype = change.get("change_type")
            path = change.get("file_path", "")
            if ctype == "create":
                created.append(path)
                if self._is_config_file(path):
                    config_changed.append(path)
            elif ctype == "modify":
                modified.append(path)
                if self._is_config_file(path):
                    config_changed.append(path)
            elif ctype == "delete":
                deleted.append(path)
            elif ctype == "rename":
                renamed.append(
                    {
                        "new_path": path,
                        "old_path": change.get("old_path", path),
                    }
                )

        operations: List[Dict[str, Any]] = []

        def _add_op(op: str, path: str, **extra: Any) -> None:
            operations.append({"op": op, "path": path, **extra})

        for change in changes:
            ctype = change.get("change_type")
            path = change.get("file_path", "")
            item_id = change.get("backlog_item_id", "UNASSIGNED")
            if ctype == "create":
                _add_op("remove_file", path, backlog_item_id=item_id)
            elif ctype == "modify":
                _add_op(
                    "restore_content",
                    path,
                    backlog_item_id=item_id,
                    backup_sha256=self._backups.get(path),
                )
            elif ctype == "delete":
                _add_op("restore_deleted", path, backlog_item_id=item_id)
            elif ctype == "rename":
                _add_op(
                    "move_back",
                    path,
                    old_path=change.get("old_path", path),
                    backlog_item_id=item_id,
                )

        if not operations:
            operations.append({"op": "none", "path": None, "backlog_item_id": None})

        commands: List[str] = render_rollback_commands(operations, platform="posix")

        # Per-item rollback grouping for the report and the rollback workflow.
        by_item: Dict[str, List[Dict[str, Any]]] = {}
        for op in operations:
            item_id = op.get("backlog_item_id") or "UNASSIGNED"
            by_item.setdefault(item_id, []).append(op)

        return {
            "created": created,
            "modified": modified,
            "deleted": deleted,
            "renamed": renamed,
            "config_changed": config_changed,
            "commands": commands,
            "operations": operations,
            "by_item": by_item,
            "baseline_dirty_files": sorted(baseline_paths),
        }

    # ------------------------------------------------------------------
    # Main entry point
    # ------------------------------------------------------------------
    def execute(self) -> Dict[str, Any]:
        """Run the execution phase on planned items."""
        plan_data = self.state_manager.load_json("RUP_PLAN.json")
        if not plan_data:
            raise RuntimeError("Missing RUP_PLAN.json. Must run plan first.")

        discovery_data = self.state_manager.load_json("RUP_DISCOVERY.json")
        self.discovery_data = discovery_data or {}
        backlog = plan_data.get("backlog", [])
        selected_ids = set(plan_data.get("selected_items", []))
        selected_items = [item for item in backlog if item.get("id") in selected_ids]
        execution_order = plan_data.get("execution_order", list(selected_ids))

        # RUP-XFER-002: the escalation guard is enforced by the execution phase
        # itself, not just by CLI orchestration, so phase-only ``rup plan; rup
        # execute`` has the same safety semantics as ``rup run`` (audit P1-25).
        plan_state = self.state_manager.load_json("plan-state.json")
        if isinstance(plan_state, dict) and plan_state.get("requires_explicit_override") and not self.override_escalation:
            raise RuntimeError(
                "Planning produced escalations that require explicit override. "
                "Re-run with --override-escalation to continue."
            )

        # RUP-XFER-001: Skill-only planning constraints live in plan-state.json
        # and are authoritative. Legacy RUP_PLAN.json constraints are honored as
        # a fallback for pre-sidecar artifacts, with a deprecation warning.
        constraints = {}
        if isinstance(plan_state, dict):
            constraints = plan_state.get("constraints", {})
        if not constraints:
            legacy = plan_data.get("constraints", {})
            if legacy:
                warnings.warn(
                    "plan-state.json has no constraints; falling back to legacy "
                    "RUP_PLAN.json constraints (deprecated)",
                    RuntimeWarning,
                    stacklevel=2,
                )
            constraints = legacy
        max_files = constraints.get("max_files", 20)
        risk_tolerance = constraints.get("risk_tolerance", "medium")
        tolerance_rank = RISK_RANK.get(risk_tolerance, 1)

        order_index = {item_id: idx for idx, item_id in enumerate(execution_order)}
        ordered_items = sorted(
            selected_items,
            key=lambda item: order_index.get(item.get("id", ""), 9999),
        )

        # RUP-SEC-002: the adversarial trust gate runs before any target-controlled
        # command (baseline coverage, per-item verification gates). A hostile
        # repository cannot trigger test/build execution without --allow-exec and,
        # when required, a detected sandbox.
        threat_findings = scan_repository_for_threats(self.target_dir)
        gates_allowed, gates_reason = execution_gate_status(
            self.allow_exec, self.sandbox, threat_findings
        )
        execution_gate = {
            "allowed": gates_allowed,
            "reason": gates_reason,
            "threat_findings": len(threat_findings),
            "allow_exec": self.allow_exec,
            "sandbox": self.sandbox,
        }

        # RUP-EXEC-005: capture baseline Git status and per-path content hashes
        # before applying changes. Dirty paths are never mutated by RUP.
        baseline_paths = self._baseline_paths()
        baseline_snapshot = self._capture_content_baseline()

        # Capture baseline coverage and test counts before any changes are applied.
        # Skipped (recorded as empty) when the execution trust gate refuses
        # target-controlled commands.
        baseline = (
            self._collect_baseline_coverage()
            if gates_allowed
            else {"coverage_before": None, "tests_before": 0}
        )

        changes: List[Dict[str, Any]] = []
        recommendations: List[Dict[str, Any]] = []
        changed_files: Set[str] = set()
        per_item_completion: Dict[str, str] = {}
        per_item_checkpoints: Dict[str, Dict[str, Any]] = {}

        # RUP-PLAN-004: the planning phase emits a per-workstream checkpoint
        # graph (verification method + success criteria). Execution enforces each
        # item's checkpoint after its workstream instead of only a single global
        # verification pass (audit P1-13).
        checkpoint_methods: Dict[str, str] = {}
        if isinstance(plan_state, dict):
            for cp in plan_state.get("checkpoints", []) or []:
                if isinstance(cp, dict) and cp.get("backlog_item_id"):
                    checkpoint_methods[cp["backlog_item_id"]] = cp.get("verification_method", "existence")

        # Monorepo scoping (audit P1-11): --workspace / --changed-packages.
        ws = detect_workspace(self.target_dir)
        scoped_names: Optional[Set[str]] = None
        package_dirs: Dict[str, Path] = {}
        scoped_workspace: Optional[Dict[str, Any]] = None
        if (self.workspace or self.changed_only) and ws is not None:
            if self.changed_only:
                changed = changed_packages(self.target_dir, ws)
                if changed and changed != ["all"]:
                    scoped_names = set(changed)
            elif self.workspace:
                known = {p["name"] for p in ws["packages"]}
                if self.workspace in known:
                    scoped_names = {self.workspace}
            if scoped_names:
                scoped_workspace = {"tool": ws["tool"], "names": sorted(scoped_names)}
                for p in ws["packages"]:
                    if p["name"] in scoped_names:
                        package_dirs[p["name"]] = self.target_dir / p["path"]
        if (self.workspace or self.changed_only) and scoped_names is None:
            warnings.warn(
                "Workspace scoping requested but no matching packages found; "
                "executing without scoping.",
                RuntimeWarning,
                stacklevel=2,
            )

        def _item_package(item: Dict[str, Any]) -> Optional[str]:
            if ws is None:
                return None
            for f in item.get("scope", {}).get("files", []) or []:
                for p in ws["packages"]:
                    prefix = p["path"].rstrip("/") + "/"
                    if f == p["path"] or f.startswith(prefix):
                        return p["name"]
            return None

        if scoped_workspace is not None:
            pkg_items: Dict[str, List[Dict[str, Any]]] = {}
            root_items: List[Dict[str, Any]] = []
            out_of_scope: List[Dict[str, Any]] = []
            for item in ordered_items:
                pkg = _item_package(item)
                if pkg is None:
                    root_items.append(item)
                elif pkg in scoped_names:
                    pkg_items.setdefault(pkg, []).append(item)
                else:
                    out_of_scope.append(item)
            for item in out_of_scope:
                item_id = item.get("id", "")
                recommendations.append(
                    self._recommendation(
                        item_id,
                        self._item_subtype(item),
                        "AGENT_ONLY",
                        f"Item targets a package outside the scoped workspace "
                        f"({', '.join(sorted(scoped_names))}); skipped (RUP-MONO-001).",
                    )
                )
                per_item_completion[item_id] = "AGENT_ONLY"
            # Packages run in dependency order, then root/shared items.
            ordered_items = []
            for pkg_name in dependency_order(sorted(scoped_names), ws["graph"]):
                ordered_items.extend(pkg_items.get(pkg_name, []))
            ordered_items.extend(root_items)

        tools = self.tool_detector.detect_all()
        current_pkg: Optional[str] = None

        for item in ordered_items:
            item_id = item.get("id", "")
            subtype = self._item_subtype(item)
            item_risk_rank = RISK_RANK.get(item.get("risk", "low"), 0)
            if item_risk_rank > tolerance_rank:
                rec = self._recommendation(
                    item_id,
                    subtype,
                    "AGENT_ONLY",
                    f"Item risk '{item.get('risk')}' exceeds run tolerance '{risk_tolerance}'; "
                    "manual review required before applying changes.",
                )
                recommendations.append(rec)
                per_item_completion[item_id] = "AGENT_ONLY"
                continue
            if len(changed_files) >= max_files:
                rec = self._recommendation(
                    item_id,
                    subtype,
                    "AGENT_ONLY",
                    f"Skipped because max-files limit ({max_files}) has been reached.",
                )
                recommendations.append(rec)
                per_item_completion[item_id] = "AGENT_ONLY"
                continue

            # Per-package tooling and write root: switch when crossing packages
            # (audit P1-11), so handlers see the package's own toolchain and
            # remediation files land inside the package directory.
            if scoped_workspace is not None:
                pkg = _item_package(item)
                if pkg != current_pkg:
                    if pkg is not None and pkg in package_dirs:
                        self._work_dir = package_dirs[pkg]
                        self.tool_detector = ToolDetector(self._work_dir)
                    else:
                        self._work_dir = self.target_dir
                        self.tool_detector = ToolDetector(self.target_dir)
                    tools = self.tool_detector.detect_all()
                    current_pkg = pkg
            try:
                item_changes, item_recommendations = self._execute_workstream_item(
                    item, discovery_data
                )
            except BaselineDirtyRefusal as exc:
                recommendations.append(
                    self._recommendation(
                        item_id,
                        subtype,
                        "AGENT_ONLY",
                        str(exc),
                    )
                )
                per_item_completion[item_id] = "AGENT_ONLY"
                continue

            # Package-scoped writes: handler paths are work-dir relative; the
            # recorded change paths must be target-relative for attribution,
            # rollback, and package grouping (audit P1-11).
            if self._work_dir != self.target_dir:
                prefix = self._work_dir.relative_to(self.target_dir).as_posix()
                for change in item_changes:
                    fp = change.get("file_path")
                    if fp and not fp.startswith(prefix + "/"):
                        change["file_path"] = f"{prefix}/{fp}"

            recommendations.extend(item_recommendations)

            # RUP-PLAN-004: enforce this item's checkpoint gate now that its
            # workstream has run (per-item verification, not only a global pass).
            method = checkpoint_methods.get(item_id, "existence")
            if gates_allowed:
                checkpoint_result = self._enforce_item_checkpoint(method, tools)
            else:
                checkpoint_result = {
                    "method": method,
                    "status": "skipped",
                    "passed": None,
                    "details": gates_reason,
                }
            per_item_checkpoints[item_id] = checkpoint_result

            completion = self._resolve_completion(item_changes, item_recommendations)
            if checkpoint_result.get("status") == "failed":
                completion = "PARTIAL"
                recommendations.append(
                    self._recommendation(
                        item_id,
                        subtype,
                        "PARTIAL",
                        f"Checkpoint '{method}' failed after the workstream ran; "
                        "remediation present but unverified (rollback available per item).",
                    )
                )
            per_item_completion[item_id] = completion

            for change in item_changes:
                file_path = change.get("file_path")
                if file_path and len(changed_files) >= max_files:
                    continue
                if file_path in self._backups:
                    change["backup_sha256"] = self._backups[file_path]
                changes.append(change)
                if file_path:
                    changed_files.add(file_path)

        # RUP-EXEC-003: run a single local verification pass after changes are applied.
        # The canonical protocol schema expects a single {tests, lint, build, type_check}
        # object, not a per-item map. When the trust gate refuses target-controlled
        # commands, record an explicit non-executed shape instead of running them.
        # Workspace-scoped runs re-detect root tooling for the aggregate pass.
        if scoped_workspace is not None:
            self.tool_detector = ToolDetector(self.target_dir)
            tools = self.tool_detector.detect_all()
        if gates_allowed:
            local_verification = self._verify_item({}, tools)
        else:
            local_verification = self._blocked_verification(gates_reason)

        # RUP-EXEC-001/005/006: attribute only net-new changes to backlog items.
        existing_paths = {c.get("file_path") for c in changes if c.get("file_path")}
        for entry in self._git_status_entries():
            path = entry["path"]
            old_path = entry.get("old_path")
            if path in existing_paths:
                continue
            if path in baseline_paths or (old_path and old_path in baseline_paths):
                continue
            if path.startswith(".rup") or path.startswith("RUP_"):
                continue
            # Directory entries (git collapses untracked trees) are containers
            # for the file changes already tracked; rollback removes their
            # contents, and an empty dir cannot be `rm`-ed.
            if (self.target_dir / path).is_dir():
                continue
            if len(changed_files) >= max_files:
                break

            change: Dict[str, Any] = {
                "file_path": path,
                "change_type": self._status_to_change_type(entry["code"]),
                "rationale": "Detected repository modification",
                "backlog_item_id": self._attribute_item_id(path, selected_items),
            }
            if old_path:
                change["old_path"] = old_path
            changes.append(change)
            changed_files.add(path)

        # Extract recent commits.
        commits: List[Dict[str, Any]] = []
        try:
            rc, stdout, _ = run_command(
                ["git", "log", "-n", "5", "--oneline"], cwd=self.target_dir
            )
            if rc == 0 and stdout:
                for line in stdout.splitlines():
                    if not line.strip():
                        continue
                    parts = line.split(" ", 1)
                    commits.append(
                        {
                            "hash": parts[0],
                            "message": parts[1] if len(parts) > 1 else "",
                            "files": [],
                            "type": "commit",
                            "breaking": "BREAKING" in line,
                            "backlog_item_ids": [],
                        }
                    )
        except Exception as e:
            warnings.warn(f"Git log enumeration failed: {e}", RuntimeWarning, stacklevel=2)

        # RUP-EXEC-004: build rollback procedure.
        rollback_procedure = self._build_rollback(changes, baseline_paths)

        # The full execution record is used for the human-readable report and may
        # contain downstream extensions (recommendations, rollback details). The
        # machine-readable JSON artifact must conform to the canonical protocol schema.
        execution_data: Dict[str, Any] = {
            "changes": changes,
            "recommendations": recommendations,
            "commits": commits,
            "local_verification": local_verification,
            "rollback_procedure": rollback_procedure,
            "artifacts": [],
        }
        schema_execution_data: Dict[str, Any] = {
            "changes": changes,
            "commits": commits,
            "local_verification": local_verification,
            "artifacts": [],
        }

        # Skill-only machine state captures dispositions and safe rollback
        # operations that the canonical execution contract intentionally omits.
        execution_state: Dict[str, Any] = {
            "recommendations": recommendations,
            "dispositions": {
                rec["backlog_item_id"]: rec["disposition"]
                for rec in recommendations
            },
            "per_item_completion": per_item_completion,
            "rollback_operations": rollback_procedure.get("operations", []),
            "rollback_by_item": rollback_procedure.get("by_item", {}),
            "per_item_checkpoints": per_item_checkpoints,
            "package_changes": self._group_changes_by_package(changes, ws),
            "scoped_workspace": scoped_workspace,
            "baseline": baseline_snapshot,
            "backups": dict(self._backups),
            "coverage_before": baseline["coverage_before"],
            "tests_before": baseline["tests_before"],
            "coverage_delta": None,
            "execution_gate": execution_gate,
        }

        # Save machine-readable state atomically.
        self.state_manager.save_json(schema_execution_data, "RUP_EXECUTION.json")
        self.state_manager.save_json(execution_state, "execution-state.json")

        # Build human-readable markdown matching canonical template.
        self.artifact_builder.build_markdown(
            "execution-report.md", execution_data, "RUP_EXECUTION.md"
        )

        return execution_data
