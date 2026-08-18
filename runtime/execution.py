"""
Execution phase module for RUP deterministic runtime.
Implements canonical Phase 3 Execution per RUP-EXEC-001..007:
- Workstream selection & dispatch (ws_bugs, ws_tests, ws_ci, ws_docs, ws_governance, ws_security)
- Baseline Git status capture and RUP-only change attribution
- Genuine remediation of planned backlog items
- Per-item local verification & change tracking
- Rollback procedure generation
- Exclusion of .rup/ state from repository diffs
"""
import json
import os
import warnings
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from .artifact_builder import ArtifactBuilder
from .command_runner import run_command
from .state import StateManager
from .tool_detection import ToolDetector


class ExecutionPhase:
    def __init__(
        self,
        target_dir: Path,
        state_manager: StateManager,
        artifact_builder: ArtifactBuilder,
    ):
        self.target_dir = target_dir
        self.state_manager = state_manager
        self.artifact_builder = artifact_builder
        self.tool_detector = ToolDetector(target_dir)

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
        self, item_id: str, rationale: str, file_path: str = ""
    ) -> Dict[str, Any]:
        return {
            "file_path": file_path or f"RECOMMENDATION-{item_id}",
            "change_type": "recommendation",
            "rationale": rationale,
            "backlog_item_id": item_id,
        }

    # ------------------------------------------------------------------
    # Workstream handlers
    # ------------------------------------------------------------------
    def _handle_bugs(self, item: Dict[str, Any]) -> List[Dict[str, Any]]:
        item_id = item.get("id", "")
        return [
            self._recommendation(
                item_id,
                "Automated bug remediation requires targeted acceptance criteria; "
                "manual analysis and a dedicated fix plan are needed.",
            )
        ]

    def _handle_tests(self, item: Dict[str, Any], primary_lang: str) -> List[Dict[str, Any]]:
        item_id = item.get("id", "")
        changes: List[Dict[str, Any]] = []
        acceptance = item.get("acceptance_criteria", [])

        # Only emit a concrete test file when acceptance criteria contain
        # specific, automatable expectations. Generic framework criteria are
        # treated as configuration-only scaffolding.
        concrete = bool(acceptance) and any(
            any(marker in criterion.lower() for marker in ("test_", "assert", "function", "module", "file:"))
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
                changes.append(
                    self._recommendation(
                        item_id,
                        "Concrete acceptance criteria detected, but automated "
                        "test generation requires explicit assertions to avoid "
                        "tautological placeholders.",
                        "tests/",
                    )
                )
            else:
                changes.append(
                    self._recommendation(
                        item_id,
                        "No concrete acceptance criteria available; test code "
                        "must be authored against explicit requirements.",
                        "tests/",
                    )
                )
        else:
            changes.append(
                self._recommendation(
                    item_id,
                    f"Automated test scaffolding for '{primary_lang}' requires "
                    "concrete acceptance criteria to avoid tautological tests.",
                )
            )
        return changes

    def _handle_ci(self, item: Dict[str, Any], primary_lang: str) -> List[Dict[str, Any]]:
        item_id = item.get("id", "")
        changes: List[Dict[str, Any]] = []
        wf_dir = self.target_dir / ".github" / "workflows"
        wf_dir.mkdir(exist_ok=True, parents=True)
        ci_path = wf_dir / "ci.yml"
        if ci_path.exists():
            return changes

        lang = (primary_lang or "unknown").lower()
        if lang in ("javascript", "typescript"):
            steps = """      - name: Set up Node.js
        uses: actions/setup-node@v4
        with:
          node-version: '20'
      - name: Install dependencies
        run: npm ci
      - name: Run tests
        run: npm test"""
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
            # Default to Python-oriented steps.
            steps = """      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'
      - name: Install dependencies
        run: |
          python -m pip install --upgrade pip
          if [ -f requirements.txt ]; then pip install -r requirements.txt; fi
          if [ -f pyproject.toml ]; then pip install -e .; fi
          pip install pytest
      - name: Run tests
        run: pytest"""

        content = f"""name: CI

on:
  push:
    branches: [main, master]
  pull_request:
    branches: [main, master]

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
        return changes

    def _handle_docs(self, item: Dict[str, Any], meta: Dict[str, Any]) -> List[Dict[str, Any]]:
        item_id = item.get("id", "")
        title = item.get("title", "")
        changes: List[Dict[str, Any]] = []
        repo_name = meta.get("name", "Project")
        repo_type = meta.get("repo_type", "Application")

        if "README" in item_id or "README" in title or item_id == "DOCS-001":
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

        if "CONTRIBUTING" in item_id or "CONTRIBUTING" in title or item_id == "DOCS-002":
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
        return changes

    def _handle_governance(self, item: Dict[str, Any]) -> List[Dict[str, Any]]:
        item_id = item.get("id", "")
        title = item.get("title", "")
        changes: List[Dict[str, Any]] = []

        if "CODEOWNERS" in item_id or "CODEOWNERS" in title or item_id == "GOV-001":
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

        if (
            "LIC" in item_id
            or "License" in title
            or item_id == "GOV-002"
            or (item.get("category") == "governance" and "license" in title.lower())
        ):
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
                    changes.append(
                        self._recommendation(
                            item_id,
                            "No bundled full Apache-2.0 license text found; "
                            "explicit license selection is required before committing a LICENSE file.",
                            "LICENSE",
                        )
                    )
        return changes

    def _handle_security(self, item: Dict[str, Any]) -> List[Dict[str, Any]]:
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
        return changes

    def _execute_workstream_item(
        self, item: Dict[str, Any], discovery_data: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """Implement remediation for a specific backlog item."""
        item_id = item.get("id", "")
        category = item.get("category", "")
        meta = discovery_data.get("repo_metadata", {})
        primary_lang = meta.get("primary_language", "python")

        if category == "bugs" or item_id.startswith("BUG"):
            return self._handle_bugs(item)
        if category == "tests" or item_id.startswith("TEST"):
            return self._handle_tests(item, primary_lang)
        if category == "ci" or item_id.startswith("CI"):
            return self._handle_ci(item, primary_lang)
        if category == "docs" or item_id.startswith("DOCS"):
            return self._handle_docs(item, meta)
        if category == "governance" or item_id.startswith("GOV"):
            return self._handle_governance(item)
        if category == "security" or item_id.startswith("SEC"):
            return self._handle_security(item)

        return []

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

        commands: List[str] = [
            "# Rollback commands for RUP-generated changes",
        ]
        for path in created:
            commands.append(f"rm '{path}'")
        for path in modified:
            commands.append(f"git checkout -- '{path}'")
        for path in deleted:
            commands.append(f"git checkout HEAD -- '{path}'")
        for entry in renamed:
            commands.append(
                f"git mv '{entry['new_path']}' '{entry['old_path']}'"
            )
        for path in config_changed:
            commands.append(f"git checkout -- '{path}'")

        return {
            "created": created,
            "modified": modified,
            "deleted": deleted,
            "renamed": renamed,
            "config_changed": config_changed,
            "commands": commands,
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

        order_index = {item_id: idx for idx, item_id in enumerate(execution_order)}
        ordered_items = sorted(
            selected_items,
            key=lambda item: order_index.get(item.get("id", ""), 9999),
        )

        # RUP-EXEC-005: capture baseline Git status before applying changes.
        baseline_paths = self._baseline_paths()

        changes: List[Dict[str, Any]] = []
        for item in ordered_items:
            item_changes = self._execute_workstream_item(item, discovery_data)
            changes.extend(item_changes)

        # RUP-EXEC-003: per-item local verification after changes are applied.
        tools = self.tool_detector.detect_all()
        local_verification: Dict[str, Any] = {}
        for item in ordered_items:
            local_verification[item.get("id", "")] = self._verify_item(item, tools)

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

            change: Dict[str, Any] = {
                "file_path": path,
                "change_type": self._status_to_change_type(entry["code"]),
                "rationale": "Detected repository modification",
                "backlog_item_id": self._attribute_item_id(path, selected_items),
            }
            if old_path:
                change["old_path"] = old_path
            changes.append(change)

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

        execution_data: Dict[str, Any] = {
            "changes": changes,
            "commits": commits,
            "local_verification": local_verification,
            "rollback_procedure": rollback_procedure,
            "artifacts": [],
        }

        # Save machine-readable state atomically.
        self.state_manager.save_json(execution_data, "RUP_EXECUTION.json")

        # Build human-readable markdown matching canonical template.
        self.artifact_builder.build_markdown(
            "execution-report.md", execution_data, "RUP_EXECUTION.md"
        )

        return execution_data
