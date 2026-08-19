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
import json
import os
import re
import shlex
import sys
import warnings
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from .artifact_builder import ArtifactBuilder
from .command_runner import run_command
from .state import StateManager
from .tool_detection import ToolDetector

RISK_RANK = {"low": 0, "medium": 1, "high": 2}


class ExecutionPhase:
    def __init__(
        self,
        target_dir: Path,
        state_manager: StateManager,
        artifact_builder: ArtifactBuilder,
        allow_exec: bool = False,
        sandbox_policy: str = "required",
    ):
        self.target_dir = target_dir
        self.state_manager = state_manager
        self.artifact_builder = artifact_builder
        self.tool_detector = ToolDetector(target_dir)
        self.allow_exec = allow_exec
        self.sandbox_policy = sandbox_policy

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

        # Containers / IaC / Observability
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
            pytest_ini = self.target_dir / "pytest.ini"
            if not pytest_ini.exists():
                pytest_ini.write_text(
                    "[pytest]\ntestpaths = tests\npython_files = test_*.py\n",
                    encoding="utf-8",
                )
                changes.append(
                    {
                        "file_path": "pytest.ini",
                        "change_type": "create",
                        "rationale": "Configured baseline pytest configuration",
                        "backlog_item_id": item_id,
                    }
                )
            tests_dir = self.target_dir / "tests"
            tests_dir.mkdir(exist_ok=True, parents=True)

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

    @staticmethod
    def _pyproject_is_installable(pyproject: Path) -> bool:
        """Return True when pyproject.toml indicates the package is installable."""
        if not pyproject.exists():
            return False
        try:
            text = pyproject.read_text(encoding="utf-8")
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
        wf_dir = self.target_dir / ".github" / "workflows"
        wf_dir.mkdir(exist_ok=True, parents=True)
        ci_path = wf_dir / "ci.yml"
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
            installable = self._pyproject_is_installable(self.target_dir / "pyproject.toml")
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
        ci_path.write_text(content, encoding="utf-8")
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

        readme_path = self.target_dir / "README.md"
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
            readme_path.write_text(content, encoding="utf-8")
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
        contrib_path = self.target_dir / "CONTRIBUTING.md"
        if not contrib_path.exists():
            content = """# Contributing Guidelines

Thank you for contributing!

## Pull Request Process
1. Ensure all tests and linters pass before opening a pull request.
2. Follow Conventional Commits format (`feat:`, `fix:`, `docs:`, `chore:`).
3. Update documentation for any user-facing changes.
"""
            contrib_path.write_text(content, encoding="utf-8")
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

        codeowners_path = self.target_dir / ".github" / "CODEOWNERS"
        if not codeowners_path.exists() and not (self.target_dir / "CODEOWNERS").exists():
            codeowners_path.parent.mkdir(parents=True, exist_ok=True)
            content = """# CODEOWNERS
# Replace the examples below with real GitHub usernames or team names.
# See https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/customizing-your-repository/about-code-owners
# * @owner
# src/ @team-frontend
# docs/ @team-docs
"""
            codeowners_path.write_text(content, encoding="utf-8")
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

        lic_path = self.target_dir / "LICENSE"
        if not lic_path.exists():
            template_path = self.state_manager.paths.get_skill_path(
                "templates", "LICENSE-APACHE-2.0.txt"
            )
            if template_path.exists():
                lic_path.write_text(
                    template_path.read_text(encoding="utf-8"), encoding="utf-8"
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
        sec_path = self.target_dir / "SECURITY.md"
        if not sec_path.exists() and not (self.target_dir / ".github" / "SECURITY.md").exists():
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
            sec_path.write_text(content, encoding="utf-8")
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
            eslint_path = self.target_dir / ".eslintrc.json"
            if not eslint_path.exists():
                eslint_path.write_text(
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
                    encoding="utf-8",
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
            ruff_path = self.target_dir / "ruff.toml"
            if not ruff_path.exists() and not (self.target_dir / "pyproject.toml").exists():
                ruff_path.write_text(
                    "[lint]\nselect = ['E', 'F', 'I']\nignore = []\n",
                    encoding="utf-8",
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
            tsconfig_path = self.target_dir / "tsconfig.json"
            if not tsconfig_path.exists():
                tsconfig_path.write_text(
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
                    encoding="utf-8",
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
            mypy_path = self.target_dir / "mypy.ini"
            if not mypy_path.exists():
                mypy_path.write_text(
                    "[mypy]\npython_version = 3.11\nwarn_return_any = True\nwarn_unused_configs = True\n",
                    encoding="utf-8",
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

    def _handle_container(
        self, item: Dict[str, Any], subtype: str
    ) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        item_id = item.get("id", "")
        return [], [
            self._recommendation(
                item_id,
                subtype,
                "NOT_PORTED",
                "Container and Dockerfile generation is not ported to the deterministic runtime; "
                "author manually or extend the runtime with a container workstream handler.",
            )
        ]

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

    def _handle_observability(
        self, item: Dict[str, Any], subtype: str
    ) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        item_id = item.get("id", "")
        return [], [
            self._recommendation(
                item_id,
                subtype,
                "NOT_PORTED",
                "Observability configuration generation is not ported to the deterministic runtime; "
                "author manually or extend the runtime with an observability workstream handler.",
            )
        ]

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

        # Best-effort cleanup of temporary coverage files.
        for cov_file in self.target_dir.glob(".coverage*"):
            try:
                cov_file.unlink()
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
            return ["npx", "jest"]
        if framework == "vitest":
            return ["npx", "vitest", "run"]
        if framework == "mocha":
            return ["npx", "mocha"]
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
            return ["npx", "eslint", "."]
        if linter == "clippy":
            return ["cargo", "clippy"]
        if linter == "golangci-lint":
            return ["golangci-lint", "run"]
        return None

    def _type_check_command(self, type_checker: Optional[str]) -> Optional[List[str]]:
        if type_checker == "mypy":
            return ["mypy", "."]
        if type_checker == "tsc":
            return ["npx", "tsc", "--noEmit"]
        return None

    def _build_command(
        self, build_tool: Optional[str], target_dir: Path
    ) -> Optional[List[str]]:
        if build_tool in ("npm", "pnpm", "yarn"):
            pkg = target_dir / "package.json"
            if pkg.exists():
                try:
                    data = json.loads(pkg.read_text(encoding="utf-8", errors="ignore"))
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
        commands: List[str] = [
            "# Rollback commands for RUP-generated changes",
        ]

        def _add_op(op: str, argv: List[str], shell: str) -> None:
            operations.append({"op": op, "argv": argv})
            commands.append(shell)

        for path in created:
            _add_op(
                "rm",
                ["rm", "-f", "--", path],
                " ".join(["rm", "-f", "--", shlex.quote(path)]),
            )
        for path in modified:
            _add_op(
                "git-checkout",
                ["git", "checkout", "--", path],
                " ".join(["git", "checkout", "--", shlex.quote(path)]),
            )
        for path in deleted:
            _add_op(
                "git-restore",
                ["git", "checkout", "HEAD", "--", path],
                " ".join(["git", "checkout", "HEAD", "--", shlex.quote(path)]),
            )
        for entry in renamed:
            new_path = entry["new_path"]
            old_path = entry["old_path"]
            _add_op(
                "git-mv",
                ["git", "mv", "--", new_path, old_path],
                " ".join(["git", "mv", "--", shlex.quote(new_path), shlex.quote(old_path)]),
            )
        for path in config_changed:
            _add_op(
                "git-checkout",
                ["git", "checkout", "--", path],
                " ".join(["git", "checkout", "--", shlex.quote(path)]),
            )

        if not operations:
            operations.append({"op": "none", "argv": ["#", "No changes to revert"]})
            commands.append("# No changes to revert")

        return {
            "created": created,
            "modified": modified,
            "deleted": deleted,
            "renamed": renamed,
            "config_changed": config_changed,
            "commands": commands,
            "operations": operations,
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
        backlog = plan_data.get("backlog", [])
        selected_ids = set(plan_data.get("selected_items", []))
        selected_items = [item for item in backlog if item.get("id") in selected_ids]
        execution_order = plan_data.get("execution_order", list(selected_ids))

        plan_state = self.state_manager.load_json("plan-state.json") or {}
        plan_constraints = plan_state.get("constraints", {})
        if not plan_constraints:
            plan_constraints = plan_data.get("constraints", {})
            if plan_constraints:
                warnings.warn(
                    "Execution fell back to legacy RUP_PLAN.json constraints; "
                    "plan-state.json is the authoritative source.",
                    DeprecationWarning,
                    stacklevel=2,
                )
        max_files = plan_constraints.get("max_files", 20)
        risk_tolerance = plan_constraints.get("risk_tolerance", "medium")
        tolerance_rank = RISK_RANK.get(risk_tolerance, 1)

        order_index = {item_id: idx for idx, item_id in enumerate(execution_order)}
        ordered_items = sorted(
            selected_items,
            key=lambda item: order_index.get(item.get("id", ""), 9999),
        )

        # RUP-EXEC-005: capture baseline Git status before applying changes.
        baseline_paths = self._baseline_paths()

        # Capture baseline coverage and test counts before any changes are applied.
        baseline = self._collect_baseline_coverage()

        changes: List[Dict[str, Any]] = []
        recommendations: List[Dict[str, Any]] = []
        changed_files: Set[str] = set()
        per_item_completion: Dict[str, str] = {}
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
            item_changes, item_recommendations = self._execute_workstream_item(
                item, discovery_data
            )
            recommendations.extend(item_recommendations)
            per_item_completion[item_id] = self._resolve_completion(
                item_changes, item_recommendations
            )
            for change in item_changes:
                file_path = change.get("file_path")
                if file_path and len(changed_files) >= max_files:
                    continue
                changes.append(change)
                if file_path:
                    changed_files.add(file_path)

        # RUP-EXEC-003: run a single local verification pass after changes are applied.
        # The canonical protocol schema expects a single {tests, lint, build, type_check}
        # object, not a per-item map.
        tools = self.tool_detector.detect_all()
        local_verification = self._verify_item({}, tools)

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
            "coverage_before": baseline["coverage_before"],
            "tests_before": baseline["tests_before"],
            "coverage_delta": None,
        }

        # Save machine-readable state atomically.
        self.state_manager.save_json(schema_execution_data, "RUP_EXECUTION.json")
        self.state_manager.save_json(execution_state, "execution-state.json")

        # Build human-readable markdown matching canonical template.
        self.artifact_builder.build_markdown(
            "execution-report.md", execution_data, "RUP_EXECUTION.md"
        )

        return execution_data
