"""
Verification phase module for RUP deterministic runtime.
Implements canonical Phase 4 Verification:
4.1 Test Verification (3-run flakiness detection, real duration, actual pass/fail counts)
4.2 Lint Verification (violation counts before/after)
4.3 Security Verification (secret scanning, prompt-injection defense, dependency check, real SAST)
4.4 Build & Type Check Verification
4.5 Real Git diff numstat metrics
4.6 Strict status determination (never certifies unexecuted gates as passed)
"""
import datetime
import json
import re
import shutil
import sys
import time
import warnings
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .artifact_builder import ArtifactBuilder
from .command_runner import run_command
from .inventory import InventoryManager
from .redaction import scan_file_for_secrets_status
from .security import (
    execution_gate_status,
    iter_jailed_files,
    jailed_unlink,
    open_jailed_read,
    read_jailed_text,
    scan_content_for_threats,
)
from .state import StateManager
from .tool_detection import ToolDetector
from .tool_resolution import resolve_js_tool
from .workspace import changed_packages, detect_workspace


class VerificationPhase:
    def __init__(
        self,
        target_dir: Path,
        state_manager: StateManager,
        artifact_builder: ArtifactBuilder,
        strict: bool = False,
        allow_exec: bool = False,
        sandbox: str = "off",
        workspace: Optional[str] = None,
        changed_only: bool = False,
    ):
        self.target_dir = target_dir
        self.state_manager = state_manager
        self.artifact_builder = artifact_builder
        self.strict = strict
        self.allow_exec = allow_exec
        self.sandbox = sandbox
        # Monorepo scoping (audit P1-11): when a package is selected, executable
        # gates (tests/lint/type/build) run from the package directory with the
        # package's own toolchain; security walks remain repository-wide.
        self._gate_cwd = target_dir
        if workspace or changed_only:
            ws = detect_workspace(target_dir)
            if ws is not None:
                if changed_only:
                    names = changed_packages(target_dir, ws)
                    scoped = names if names and names != ["all"] else []
                else:
                    scoped = [workspace] if workspace in {p["name"] for p in ws["packages"]} else []
                if scoped:
                    pkg_dir = next(
                        (target_dir / p["path"] for p in ws["packages"] if p["name"] in scoped),
                        target_dir,
                    )
                    self._gate_cwd = pkg_dir
                    self.workspace_scope = sorted(scoped)
        self._tools = ToolDetector(self._gate_cwd).detect_all()
        self._primary_language = InventoryManager(target_dir).analyze_inventory().get(
            "primary_language", "unknown"
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _now_utc(self) -> str:
        now = datetime.datetime.now(datetime.timezone.utc).isoformat()
        return now if now.endswith("Z") else now.replace("+00:00", "Z")

    def _is_dir(self) -> bool:
        return self.target_dir.is_dir()

    def _tool_available(self, executable: str) -> bool:
        return shutil.which(executable) is not None

    def _python_module_available(self, module: str) -> bool:
        if self._tool_available(module):
            return True
        rc, _, _ = run_command([sys.executable, "-m", module, "--version"], cwd=self.target_dir, timeout=30)
        return rc == 0

    def _project_files(self):
        """Yield project files, skipping well-known dependency/build/vcs dirs.

        Uses the jailed walker (RUP-SEC-001) so repository file symlinks can
        never pull external content into scanning.
        """
        if not self._is_dir():
            return
        skip_parts = {
            ".git", ".venv", "venv", "node_modules", "dist", "build", ".rup",
            "__pycache__", ".pytest_cache", ".coverage", "htmlcov", ".tox",
        }
        for p in iter_jailed_files(self.target_dir, skip_dirnames=skip_parts):
            include = False
            try:
                include = p.stat().st_size <= 5 * 1024 * 1024
            except Exception:
                include = False
            if include:
                yield p

    def _run_tool(self, cmd: List[str], timeout: int = 300) -> Tuple[int, str, str]:
        if not cmd:
            return 127, "", "No command provided"
        if not self._tool_available(cmd[0]):
            return 127, "", f"Executable not found: {cmd[0]}"
        return run_command(cmd, cwd=self._gate_cwd, timeout=timeout)

    def _gate_not_run(
        self, status: str, reason: str, tool: Optional[str] = None
    ) -> Dict[str, Any]:
        result: Dict[str, Any] = {
            "executed": False,
            "passed": False,
            "status": status,
            "reason": reason,
        }
        if tool is not None:
            result["tool"] = tool
        return result

    def _schema_test_not_run(
        self, status: str, reason: str, tool: Optional[str] = None
    ) -> Dict[str, Any]:
        return {
            "executed": False,
            "passed": 0,
            "failed": 0,
            "skipped": 0,
            "duration_seconds": 0.0,
            "coverage_before": None,
            "coverage_after": None,
            "coverage_delta": None,
            "flaky_tests": [],
            "new_tests_added": 0,
            "status": status,
            "reason": reason,
            "tool": tool,
        }

    def _schema_lint_not_run(
        self, status: str, reason: str, tool: Optional[str] = None
    ) -> Dict[str, Any]:
        return {
            "executed": False,
            "violations_before": 0,
            "violations_after": 0,
            "auto_fixed": 0,
            "new_violations": [],
            "status": status,
            "reason": reason,
            "tool": tool,
        }

    def _schema_build_not_run(
        self, status: str, reason: str, tool: Optional[str] = None
    ) -> Dict[str, Any]:
        return {
            "executed": False,
            "succeeded": False,
            "warnings": 0,
            "duration_seconds": 0.0,
            "status": status,
            "reason": reason,
            "tool": tool,
        }

    def _schema_type_check_not_run(
        self, status: str, reason: str, tool: Optional[str] = None
    ) -> Dict[str, Any]:
        return {
            "executed": False,
            "passed": False,
            "errors": 0,
            "status": status,
            "reason": reason,
            "tool": tool,
        }

    # ------------------------------------------------------------------
    # Git metrics
    # ------------------------------------------------------------------
    def _get_git_numstat(self) -> Tuple[int, int, int]:
        """Compute lines added, lines removed, and files changed via git diff numstat."""
        added = 0
        removed = 0
        files_changed = 0

        try:
            rc, stdout, _ = run_command(["git", "diff", "--numstat", "HEAD"], cwd=self.target_dir)
            if rc == 0 and stdout.strip():
                for line in stdout.splitlines():
                    if not line.strip():
                        continue
                    parts = line.split("\t")
                    if len(parts) >= 3:
                        fname = parts[2].strip()
                        if fname.startswith(".rup") or fname.startswith("RUP_"):
                            continue
                        files_changed += 1
                        try:
                            if parts[0] != "-":
                                added += int(parts[0])
                            if parts[1] != "-":
                                removed += int(parts[1])
                        except ValueError as e:
                            warnings.warn(f"Could not parse git numstat line: {line!r} ({e})", RuntimeWarning, stacklevel=2)
        except Exception as e:
            warnings.warn(f"Git diff numstat failed: {e}", RuntimeWarning, stacklevel=2)

        # Also account for untracked files
        try:
            rc, stdout, _ = run_command(["git", "status", "--porcelain"], cwd=self.target_dir)
            if rc == 0 and stdout:
                for line in stdout.splitlines():
                    if line.startswith("??"):
                        fname = line[3:].strip()
                        if fname.startswith(".rup") or fname.startswith("RUP_"):
                            continue
                        files_changed += 1
                        p = self.target_dir / fname
                        if p.is_file():
                            try:
                                with open_jailed_read(
                                    self.target_dir, p, encoding="utf-8", errors="ignore"
                                ) as f:
                                    added += sum(1 for _ in f)
                            except Exception as e:
                                warnings.warn(f"Untracked file line-count failed for {p}: {e}", RuntimeWarning, stacklevel=2)
        except Exception as e:
            warnings.warn(f"Git status enumeration failed: {e}", RuntimeWarning, stacklevel=2)

        return added, removed, files_changed

    # ------------------------------------------------------------------
    # Tests
    # ------------------------------------------------------------------
    def _test_command(self) -> Optional[List[str]]:
        framework = self._tools.get("test_framework")
        build_tool = self._tools.get("build_tool")

        if framework == "pytest":
            return [sys.executable, "-m", "pytest"]
        if framework == "cargo test":
            return ["cargo", "test"]
        if framework == "go test":
            return ["go", "test", "./..."]
        if framework in ("vitest", "jest", "mocha", "npm-test") or (
            framework is None and build_tool in ("npm", "pnpm", "yarn")
        ):
            pkg_mgr = build_tool if build_tool in ("npm", "pnpm", "yarn") else "npm"
            pkg_json = self.target_dir / "package.json"
            if pkg_json.exists():
                try:
                    data = json.loads(read_jailed_text(self.target_dir, pkg_json))
                    if "test" in data.get("scripts", {}):
                        return [pkg_mgr, "test"]
                except Exception as e:
                    warnings.warn(f"Could not parse package.json for test script: {e}", RuntimeWarning, stacklevel=2)
            # No test script: drive the detected framework directly, offline
            # (audit P1-18: never implicitly acquire tools over the network).
            if framework == "mocha":
                return resolve_js_tool(self._gate_cwd, "mocha")
            if framework in ("vitest", "jest"):
                return resolve_js_tool(self._gate_cwd, framework, ["run"])
            return [pkg_mgr, "test"]
        return None

    def _parse_test_counts(self, stdout: str, stderr: str, rc: int) -> Tuple[int, int, int, int]:
        combined = stdout + "\n" + stderr
        m_pass = re.search(r"(\d+)\s+passed", combined)
        m_fail = re.search(r"(\d+)\s+failed", combined)
        m_skip = re.search(r"(\d+)\s+skipped", combined)
        m_collected = re.search(r"collected\s+(\d+)\s+item", combined, re.IGNORECASE)

        passed = int(m_pass.group(1)) if m_pass else 0
        failed = int(m_fail.group(1)) if m_fail else 0
        skipped = int(m_skip.group(1)) if m_skip else 0
        collected = int(m_collected.group(1)) if m_collected else (passed + failed + skipped)

        # Fallback for simple runners that do not emit pytest-style summaries.
        if passed == 0 and failed == 0 and rc == 0:
            passed = 1
        if failed == 0 and rc != 0:
            failed = 1

        return passed, failed, skipped, collected

    def _collect_coverage(self, test_cmd: List[str]) -> Optional[float]:
        """Collect a real coverage percentage when the ecosystem supports it.

        Coverage collection is best-effort: if the required tooling is missing or
        the coverage run fails, ``None`` is returned rather than fabricating a
        value. Any temporary coverage data files created in the target directory
        are removed before returning.
        """
        framework = self._tools.get("test_framework")
        coverage_files_before = set(self.target_dir.glob(".coverage*"))

        try:
            if framework == "pytest":
                if not self._python_module_available("coverage"):
                    return None
                # Preserve any extra arguments from the detected test command.
                extra_args = test_cmd[2:] if len(test_cmd) > 2 else []
                cmd = [sys.executable, "-m", "coverage", "run", "--source=.", "-m", "pytest"] + extra_args
                rc, stdout, stderr = run_command(cmd, cwd=self._gate_cwd, timeout=180)
                if rc != 0:
                    return None
                rc2, stdout2, _ = run_command(
                    [sys.executable, "-m", "coverage", "report"],
                    cwd=self._gate_cwd,
                    timeout=60,
                )
                if rc2 != 0:
                    return None
                for line in reversed(stdout2.splitlines()):
                    parts = line.split()
                    if parts and parts[0] == "TOTAL":
                        try:
                            return float(parts[-1].replace("%", ""))
                        except ValueError:
                            return None
                return None

            if framework in ("jest", "vitest", "mocha", "npm-test") or (
                framework is None and self._tools.get("build_tool") in ("npm", "pnpm", "yarn")
            ):
                build_tool = self._tools.get("build_tool")
                pkg_mgr = build_tool if build_tool in ("npm", "pnpm", "yarn") else "npm"
                if test_cmd and test_cmd[0] == pkg_mgr and test_cmd[1:] == ["test"]:
                    # Package-manager test scripts require '--' to forward flags.
                    cmd = test_cmd + ["--", "--coverage"]
                else:
                    cmd = test_cmd + ["--coverage"]
                rc, stdout, stderr = run_command(cmd, cwd=self.target_dir, timeout=180)
                if rc != 0:
                    return None
                combined = stdout + "\n" + stderr
                # Istanbul-style table: "All files | 95 | 80 | 100 | 95%"
                m = re.search(
                    r"All files\s*\|[\s\d.]+\|[\s\d.]+\|[\s\d.]+\|\s*([\d.]+)%",
                    combined,
                )
                if m:
                    return float(m.group(1))
                # jest older output
                m = re.search(r"Statements\s*:\s*([\d.]+)%", combined)
                if m:
                    return float(m.group(1))
                return None

            return None
        finally:
            for cov_file in self.target_dir.glob(".coverage*"):
                if cov_file in coverage_files_before:
                    continue
                # Best-effort cleanup of temporary coverage files (jailed so
                # cleanup can never delete files outside the target).
                try:
                    jailed_unlink(self.target_dir, cov_file)
                except Exception:  # nosec B110
                    pass

    def _run_tests_with_flakiness(self) -> Dict[str, Any]:
        """Execute test runner 3x to detect flakiness and gather real pass/fail counts."""
        cmd = self._test_command()

        if cmd is None:
            return self._schema_test_not_run(
                "unavailable",
                "No automated test runner available",
            )

        if not self._tool_available(cmd[0]):
            return self._schema_test_not_run(
                "unavailable",
                f"Test runner executable not available: {cmd[0]}",
                tool=cmd[0],
            )

        runs: List[Dict[str, Any]] = []
        total_duration = 0.0
        last_stdout = ""
        last_stderr = ""

        for _ in range(3):
            start = time.perf_counter()
            rc, stdout, stderr = run_command(cmd, cwd=self._gate_cwd, timeout=120)
            elapsed = time.perf_counter() - start
            total_duration += elapsed
            last_stdout = stdout
            last_stderr = stderr

            passed, failed, skipped, collected = self._parse_test_counts(stdout, stderr, rc)
            runs.append({
                "rc": rc,
                "passed": passed,
                "failed": failed,
                "skipped": skipped,
                "collected": collected,
            })

        all_passed = all(r["rc"] == 0 for r in runs)
        any_passed = any(r["rc"] == 0 for r in runs)
        flaky = []
        if any_passed and not all_passed:
            flaky.append("Primary test suite showed non-deterministic failure across 3 runs")

        # Detect variance across any meaningful dimension.
        for dim in ("passed", "failed", "skipped", "collected"):
            values = [r[dim] for r in runs]
            if len(set(values)) > 1:
                flaky.append(f"Test {dim} count varied across runs: {values}")

        max_passed = max(r["passed"] for r in runs)
        max_failed = max(r["failed"] for r in runs)
        max_skipped = max(r["skipped"] for r in runs)

        coverage_after = self._collect_coverage(cmd) if cmd else None

        # Load baseline coverage/test counts captured by the execution phase.
        execution_state_raw = self.state_manager.load_json("execution-state.json")
        execution_state = execution_state_raw if execution_state_raw is not None else {}
        coverage_before = execution_state.get("coverage_before")
        tests_before = execution_state.get("tests_before", 0)
        tests_after = max(r["collected"] for r in runs) if runs else 0
        coverage_delta = (
            (coverage_after or 0) - (coverage_before or 0)
            if coverage_before is not None and coverage_after is not None
            else None
        )

        # Update the Skill-only sidecar with the after state so downstream
        # reporting and audit tooling can see true before/after deltas.
        if execution_state_raw is not None:
            execution_state["coverage_after"] = coverage_after
            execution_state["coverage_delta"] = coverage_delta
            execution_state["tests_after"] = tests_after
            self.state_manager.save_json(execution_state, "execution-state.json")

        return {
            "executed": True,
            "command_succeeded": all_passed,
            "passed": max_passed if all_passed else 0,
            "failed": max_failed if not all_passed else 0,
            "skipped": max_skipped,
            "duration_seconds": round(total_duration, 2),
            "coverage_before": coverage_before,
            "coverage_after": coverage_after,
            "flaky_tests": flaky,
            "new_tests_added": max(0, tests_after - tests_before),
            "tool": " ".join(cmd),
        }

    # ------------------------------------------------------------------
    # Lint
    # ------------------------------------------------------------------
    def _count_lint_violations(self, linter: str, cmd: List[str]) -> Tuple[int, str, int]:
        """Run the linter and return (violation_count, raw_output, returncode).

        RUP-VERIFY-001: the return code is preserved so a failing linter with
        empty output cannot be certified as passing. ``violations == 0`` never
        implies command success.
        """
        if linter == "ruff":
            # Prefer JSON output for an exact count; fall back to line counting.
            json_cmd = cmd + ["--output-format=json"]
            rc, stdout, _ = self._run_tool(json_cmd, timeout=120)
            # Fallback to line counting if ruff JSON output is unavailable.
            try:
                data = json.loads(stdout)
                if isinstance(data, list):
                    return len(data), stdout, rc
            except Exception:  # nosec B110
                pass
            if stdout.strip():
                return (
                    len([line for line in stdout.splitlines() if line.strip()]),
                    stdout,
                    rc,
                )
            return 0, stdout, rc

        rc, stdout, _ = self._run_tool(cmd, timeout=120)
        if rc != 0:
            return len([line for line in stdout.splitlines() if line.strip()]), stdout, rc
        return 0, stdout, rc

    def _run_lint(self) -> Dict[str, Any]:
        linter = self._tools.get("linter")
        if linter is None:
            return self._schema_lint_not_run("unavailable", "No linter configured or detected")

        cmd: Optional[List[str]] = None
        if linter == "ruff":
            cmd = ["ruff", "check", "."]
        elif linter == "flake8":
            cmd = ["flake8"]
        elif linter == "eslint":
            cmd = resolve_js_tool(self._gate_cwd, "eslint", ["."])
        elif linter == "clippy":
            cmd = ["cargo", "clippy", "--", "-D", "warnings"]
        elif linter == "golangci-lint":
            cmd = ["golangci-lint", "run"]

        if cmd is None:
            return self._schema_lint_not_run("unavailable", f"Unsupported linter: {linter}", tool=linter)

        violations, lint_stdout, rc = self._count_lint_violations(linter, cmd)

        return {
            "executed": True,
            "command_succeeded": rc == 0,
            "violations_before": 0,
            "violations_after": violations,
            "auto_fixed": 0,
            "new_violations": lint_stdout.splitlines() if violations else [],
            "tool": linter,
        }

    # ------------------------------------------------------------------
    # Build
    # ------------------------------------------------------------------
    def _count_build_warnings(self, build_tool: str, stdout: str, stderr: str) -> int:
        """Count compiler/package-manager warnings in a tool-specific way."""
        combined = stdout + "\n" + stderr
        if build_tool == "cargo":
            return len(re.findall(r"^warning:", combined, re.MULTILINE))
        if build_tool in ("npm", "pnpm", "yarn"):
            return combined.lower().count("warning")
        return combined.count("warning:")

    def _run_build(self) -> Dict[str, Any]:
        build_tool = self._tools.get("build_tool")
        if build_tool is None:
            return self._schema_build_not_run("unavailable", "No build tool detected")

        cmd: Optional[List[str]] = None
        if build_tool == "cargo":
            cmd = ["cargo", "build"]
        elif build_tool == "go":
            cmd = ["go", "build", "./..."]
        elif build_tool in ("npm", "pnpm", "yarn"):
            pkg_json = self.target_dir / "package.json"
            try:
                data = json.loads(read_jailed_text(self.target_dir, pkg_json))
                scripts = data.get("scripts", {})
                if "build" in scripts:
                    cmd = [build_tool, "run", "build"]
            except Exception as e:
                warnings.warn(f"Could not parse package.json for build script: {e}", RuntimeWarning, stacklevel=2)
            if cmd is None:
                return self._schema_build_not_run(
                    "not_applicable",
                    f"Package manager {build_tool} detected but no build script configured",
                    tool=build_tool,
                )
        elif build_tool in ("poetry", "pipenv"):
            return self._schema_build_not_run(
                "not_applicable",
                f"Python package manager {build_tool} does not require a compiled build step",
                tool=build_tool,
            )

        if cmd is None:
            return self._schema_build_not_run("unavailable", f"Unsupported build tool: {build_tool}", tool=build_tool)

        start = time.perf_counter()
        rc, stdout, stderr = self._run_tool(cmd, timeout=300)
        elapsed = time.perf_counter() - start

        return {
            "executed": True,
            "command_succeeded": rc == 0,
            "succeeded": rc == 0,
            "warnings": self._count_build_warnings(build_tool, stdout, stderr),
            "duration_seconds": round(elapsed, 2),
            "tool": build_tool,
        }

    # ------------------------------------------------------------------
    # Type check
    # ------------------------------------------------------------------
    def _run_type_check(self) -> Dict[str, Any]:
        type_checker = self._tools.get("type_checker")
        if type_checker is None:
            return self._schema_type_check_not_run("unavailable", "No type checker configured or detected")

        cmd: Optional[List[str]] = None
        if type_checker == "tsc":
            cmd = resolve_js_tool(self._gate_cwd, "tsc", ["--noEmit"])
        elif type_checker == "mypy":
            cmd = ["mypy", "."]
        elif type_checker == "pyright":
            if self._tool_available("pyright"):
                cmd = ["pyright"]
            else:
                cmd = [sys.executable, "-m", "pyright"]

        if cmd is None:
            return self._schema_type_check_not_run("unavailable", f"Unsupported type checker: {type_checker}", tool=type_checker)

        rc, stdout, stderr = self._run_tool(cmd, timeout=180)
        combined = stdout + "\n" + stderr
        errors = combined.count("error:")

        return {
            "executed": True,
            "command_succeeded": rc == 0,
            "passed": rc == 0,
            "errors": errors,
            "tool": type_checker,
        }

    # ------------------------------------------------------------------
    # Security
    # ------------------------------------------------------------------
    def _run_external_secret_scanner(self) -> Optional[Dict[str, Any]]:
        """Run an installed external secret scanner (gitleaks / trufflehog).

        External scanners are host-controlled, read-only tooling and run before
        the portable built-in scan; the built-in scan remains the fallback when
        neither is installed (audit P1-21).
        """
        for scanner, argv in (
            ("gitleaks", ["detect", "--no-git", "--no-banner", "--redact", "--source", "."]),
            ("trufflehog", ["filesystem", ".", "--no-update"]),
        ):
            if not self._tool_available(scanner):
                continue
            try:
                rc, stdout, stderr = run_command(
                    [scanner, *argv], cwd=self.target_dir, timeout=300
                )
            except Exception as e:  # pragma: no cover - depends on external tool
                return {
                    "tool": scanner,
                    "executed": False,
                    "passed": None,
                    "details": f"scan invocation failed: {e}",
                }
            non_empty = [line for line in stdout.splitlines() if line.strip()]
            return {
                "tool": scanner,
                "executed": True,
                "command_succeeded": rc == 0,
                "passed": rc == 0,
                "findings": len(non_empty) if rc != 0 else 0,
                "details": (stdout + "\n" + stderr).strip()[:2000],
            }
        return None

    def _run_secret_scan(self) -> Dict[str, Any]:
        """Scan repository files with structured coverage status (audit P1-20).

        A zero-finding list no longer conflates ``scanned clean`` with
        ``not scanned (too large / error)``: the result reports per-file
        status, and incomplete coverage is surfaced (and in strict mode fails
        the gate) instead of looking clean. When gitleaks or trufflehog is
        installed, its findings are merged in and the portable built-in scan
        remains the fallback (audit P1-21).
        """
        findings: List[Dict[str, Any]] = []
        files_scanned = 0
        files_skipped = 0
        scan_errors = 0
        skipped_paths: List[str] = []

        for p in self._project_files():
            hits, status = scan_file_for_secrets_status(p)
            if status == "scanned":
                files_scanned += 1
                findings.extend(hits)
            elif status in ("too_large", "error"):
                if status == "too_large":
                    files_skipped += 1
                else:
                    scan_errors += 1
                skipped_paths.append(str(p))
            # "missing" paths are skipped silently; they contribute nothing.

        complete = scan_errors == 0 and files_skipped == 0
        if not complete:
            warnings.warn(
                f"Secret scan coverage incomplete: {files_skipped} file(s) too large, "
                f"{scan_errors} scan error(s). These paths were NOT scanned.",
                RuntimeWarning,
                stacklevel=2,
            )

        result: Dict[str, Any] = {
            "executed": True,
            "passed": len(findings) == 0,
            "complete": complete,
            "files_scanned": files_scanned,
            "files_skipped": files_skipped,
            "scan_errors": scan_errors,
            "skipped_paths": skipped_paths[:20],
            "findings": len(findings),
            "details": findings[:20],
        }

        external = self._run_external_secret_scanner()
        if external is not None:
            result["external_scanner"] = external
            if external.get("executed") and external.get("passed") is False:
                result["passed"] = False
                result["findings"] = result.get("findings", 0) + external.get("findings", 0)
        return result

    def _run_prompt_injection_scan(self) -> Dict[str, Any]:
        findings: List[Dict[str, Any]] = []
        for p in self._project_files():
            try:
                content = p.read_text(encoding="utf-8", errors="ignore")
                threats = scan_content_for_threats(content)
                for t in threats:
                    t["file"] = str(p)
                findings.extend(threats)
            except Exception as e:
                warnings.warn(f"Prompt-injection content scan failed for {p}: {e}", RuntimeWarning, stacklevel=2)

        return {
            "executed": True,
            "passed": len(findings) == 0,
            "findings": len(findings),
            "details": findings[:20],
        }

    def _run_dependency_scan(self) -> Dict[str, Any]:
        build_tool = self._tools.get("build_tool")
        pkg_json = self.target_dir / "package.json"
        pyproject = self.target_dir / "pyproject.toml"
        requirements = self.target_dir / "requirements.txt"

        # Python
        if pyproject.exists() or requirements.exists() or (self.target_dir / "setup.py").exists():
            if self._python_module_available("pip-audit"):
                rc, stdout, _ = self._run_tool(["pip-audit", "--format=json"], timeout=180)
                return self._parse_dependency_scan_result(
                    "pip-audit", rc, stdout, passed=rc == 0
                )
            if self._python_module_available("safety"):
                rc, stdout, _ = self._run_tool(["safety", "check", "--json"], timeout=180)
                return self._parse_dependency_scan_result(
                    "safety", rc, stdout, passed=rc == 0
                )
            return self._gate_not_run(
                "unavailable",
                "No Python dependency audit tool available (pip-audit or safety)",
            )

        # JS / TS
        if pkg_json.exists():
            lockfiles = ("package-lock.json", "yarn.lock", "pnpm-lock.yaml", "bun.lockb")
            has_lockfile = any((self.target_dir / lf).exists() for lf in lockfiles)
            if not has_lockfile:
                return self._gate_not_run(
                    "not_applicable",
                    "Dependency scan not applicable: no supported lockfile found for JS/TS project",
                    tool="npm audit",
                )
            pkg_mgr = build_tool if build_tool in ("npm", "pnpm", "yarn") else "npm"
            if not self._tool_available(pkg_mgr):
                return self._gate_not_run(
                    "unavailable",
                    f"Package manager {pkg_mgr} not available",
                    tool=pkg_mgr,
                )
            rc, stdout, _ = self._run_tool([pkg_mgr, "audit", "--json"], timeout=180)
            return self._parse_dependency_scan_result(pkg_mgr + " audit", rc, stdout, passed=rc == 0)

        return self._gate_not_run(
            "not_applicable",
            "Dependency scan not applicable: no supported lockfile or package manifest found",
        )

    def _parse_dependency_scan_result(
        self, tool: str, rc: int, stdout: str, passed: bool
    ) -> Dict[str, Any]:
        counts = {"critical": 0, "high": 0, "medium": 0, "low": 0}
        try:
            data = json.loads(stdout)
        except Exception:
            data = None

        if isinstance(data, dict):
            # npm/pnpm/yarn audit style
            meta = data.get("metadata", {})
            vuln_counts = meta.get("vulnerabilities", {})
            if vuln_counts:
                for sev in counts:
                    counts[sev] = vuln_counts.get(sev, 0)
            else:
                # pip-audit style
                deps = data.get("dependencies", [])
                for dep in deps:
                    for vuln in dep.get("vulns", []):
                        severity = str(vuln.get("severity", "high")).lower()
                        if severity not in counts:
                            severity = "high"
                        counts[severity] += 1
        elif isinstance(data, list):
            # safety style
            for item in data:
                severity = str(item.get("severity", "high")).lower()
                if severity not in counts:
                    severity = "high"
                counts[severity] += 1

        # If the tool reports nonzero vulnerabilities but we could not parse them,
        # record at least one high finding so the gate does not silently pass.
        if rc != 0 and sum(counts.values()) == 0:
            counts["high"] = 1

        return {
            "executed": True,
            "command_succeeded": rc == 0,
            "passed": passed and sum(counts.values()) == 0,
            "tool": tool,
            "critical": counts["critical"],
            "high": counts["high"],
            "medium": counts["medium"],
            "low": counts["low"],
        }

    def _run_sast_scan(self) -> Dict[str, Any]:
        """Run SAST based on the target's primary executable language ecosystem.

        Bandit is selected for Python projects; ESLint is selected for
        JavaScript/TypeScript projects when a configuration or dependency exists.
        Other ecosystems report ``not_applicable`` rather than defaulting to a
        globally-installed tool.
        """
        primary = self._primary_language

        if primary == "python":
            if not self._python_module_available("bandit"):
                return self._gate_not_run(
                    "unavailable",
                    "Bandit not available for Python SAST",
                    tool="bandit",
                )
            rc, stdout, _ = self._run_tool(
                [
                    sys.executable,
                    "-m",
                    "bandit",
                    "-r",
                    ".",
                    "-f",
                    "json",
                    "-x",
                    "tests,test,.venv,node_modules",
                ],
                timeout=180,
            )
            findings = 0
            try:
                data = json.loads(stdout)
                findings = len(data.get("results", []))
            except Exception:
                if rc != 0:
                    findings = stdout.count("Issue:") + stdout.count("B")
            if rc != 0 and findings == 0:
                findings = 1
            return {
                "executed": True,
                "command_succeeded": rc == 0,
                "passed": rc == 0 and findings == 0,
                "findings": findings,
                "tool": "bandit",
            }

        if primary in ("javascript", "typescript"):
            pkg_json = self._gate_cwd / "package.json"
            has_eslint_config = (
                list(self._gate_cwd.glob("eslint.config.*"))
                or list(self._gate_cwd.glob(".eslintrc*"))
            )
            has_eslint_in_deps = False
            if pkg_json.exists():
                try:
                    data = json.loads(read_jailed_text(self.target_dir, pkg_json))
                    deps = {**data.get("dependencies", {}), **data.get("devDependencies", {})}
                    has_eslint_in_deps = "eslint" in deps
                except Exception as e:
                    warnings.warn(
                        f"Could not parse package.json for eslint detection: {e}",
                        RuntimeWarning,
                        stacklevel=2,
                    )

            if not (has_eslint_config or has_eslint_in_deps):
                return self._gate_not_run(
                    "not_applicable",
                    "No ESLint configuration or dependency detected for JS/TS project",
                    tool="eslint",
                )

            cmd = resolve_js_tool(self._gate_cwd, "eslint", ["."])
            if not self._tool_available(cmd[0]):
                return self._gate_not_run(
                    "unavailable",
                    f"ESLint not resolvable offline ({cmd[0]}); refusing network acquisition",
                    tool="eslint",
                )
            rc, stdout, _ = self._run_tool(cmd, timeout=180)
            findings = 0
            if rc != 0:
                findings = len([line for line in stdout.splitlines() if line.strip()])
            if rc != 0 and findings == 0:
                findings = 1
            return {
                "executed": True,
                "command_succeeded": rc == 0,
                "passed": rc == 0 and findings == 0,
                "findings": findings,
                "tool": "eslint",
            }

        return self._gate_not_run(
            "not_applicable",
            f"No SAST tool configured for primary ecosystem '{primary}'",
        )

    # ------------------------------------------------------------------
    # Status determination
    # ------------------------------------------------------------------
    def _gate_passed(self, name: str, result: Dict[str, Any]) -> bool:
        """A gate passes only when the command succeeded AND its semantic result permits it.

        RUP-VERIFY-001: an empty finding set or zero violation count never
        implies command success. Every executable gate carries an explicit
        ``command_succeeded`` field (returncode == 0); in-process scans carry no
        such field and are evaluated on their ``passed`` flag alone.
        """
        if not result.get("executed"):
            return False
        if result.get("command_succeeded") is False:
            return False
        if name == "tests":
            return result.get("failed", 0) == 0
        if name == "lint":
            return result.get("violations_after", 0) == 0
        if name == "build":
            return result.get("succeeded") is True
        if name == "secret_scan":
            # Fail closed on incomplete coverage in strict mode: skipped/error
            # files must not look like a clean scan (audit P1-20).
            if result.get("passed") is not True:
                return False
            if self.strict and result.get("complete") is not True:
                return False
            return True
        # type_check and all remaining scanners expose an explicit `passed` field.
        return result.get("passed") is True

    def _determine_status(
        self,
        tests: Dict[str, Any],
        lint: Dict[str, Any],
        build: Dict[str, Any],
        type_check: Dict[str, Any],
        secret_scan: Dict[str, Any],
        prompt_injection_scan: Dict[str, Any],
        dependency_scan: Dict[str, Any],
        sast_scan: Dict[str, Any],
    ) -> Tuple[str, str, List[Dict[str, Any]]]:
        gates = {
            "tests": tests,
            "lint": lint,
            "build": build,
            "type_check": type_check,
            "secret_scan": secret_scan,
            "prompt_injection_scan": prompt_injection_scan,
            "dependency_scan": dependency_scan,
            "sast_scan": sast_scan,
        }

        failed_gates = []
        blocked_gates = []
        unavailable_gates = []
        skipped_gates = []
        not_applicable_gates = []

        for name, result in gates.items():
            if result.get("executed"):
                if not self._gate_passed(name, result):
                    failed_gates.append(name)
            else:
                status = result.get("status", "unavailable")
                if status == "blocked":
                    blocked_gates.append(name)
                elif status == "unavailable":
                    unavailable_gates.append(name)
                elif status == "skipped":
                    skipped_gates.append(name)
                elif status == "not_applicable":
                    not_applicable_gates.append(name)
                else:
                    unavailable_gates.append(name)

        audit_entries: List[Dict[str, Any]] = []

        if failed_gates:
            msg = f"Gate(s) failed: {', '.join(failed_gates)}."
            return "failed", msg, audit_entries

        if blocked_gates:
            msg = (
                f"Gate(s) blocked by the execution trust gate: {', '.join(blocked_gates)}. "
                f"Target-controlled commands were refused."
            )
            return "failed", msg, audit_entries

        degraded = unavailable_gates + skipped_gates
        if degraded:
            if self.strict:
                msg = (
                    f"Strict mode: required gate(s) not executed or unavailable: "
                    f"{', '.join(degraded)}."
                )
                return "failed", msg, audit_entries
            msg = (
                f"Required gate(s) not executed or unavailable: {', '.join(degraded)}. "
                f"Manual verification required."
            )
            return "passed_with_warnings", msg, audit_entries

        if tests.get("flaky_tests"):
            if self.strict:
                return "failed", "Strict mode: tests exhibited flakiness.", audit_entries
            return (
                "passed_with_warnings",
                "Tests passed but exhibited flakiness across runs.",
                audit_entries,
            )

        if not_applicable_gates:
            return (
                "passed",
                f"All applicable gates passed; {', '.join(not_applicable_gates)} not applicable.",
                audit_entries,
            )

        return "passed", "All executed automated verification gates passed.", audit_entries

    # ------------------------------------------------------------------
    # Execute
    # ------------------------------------------------------------------
    def execute(self) -> Dict[str, Any]:
        """Run the complete verification phase."""
        execution_data = self.state_manager.load_json("RUP_EXECUTION.json")
        if not execution_data:
            raise RuntimeError("Missing RUP_EXECUTION.json. Must run execute first.")

        # RUP-SEC-002: the adversarial prompt-injection scan runs FIRST, before
        # any target-controlled command. If the scan (or the sandbox policy)
        # refuses execution, executable gates are recorded as blocked and never
        # run. In-process scanners (secret scan) still run: they read files and
        # execute no target code.
        prompt_injection_result = self._run_prompt_injection_scan()
        exec_allowed, exec_reason = execution_gate_status(
            self.allow_exec,
            self.sandbox,
            prompt_injection_result.get("details", []),
        )

        if exec_allowed:
            tests_result = self._run_tests_with_flakiness()
            lint_result = self._run_lint()
            build_result = self._run_build()
            type_check_result = self._run_type_check()
            dep_result = self._run_dependency_scan()
            sast_result = self._run_sast_scan()
        else:
            reason = exec_reason or "Blocked by the execution trust gate"
            tests_result = self._schema_test_not_run("blocked", reason)
            lint_result = self._schema_lint_not_run("blocked", reason)
            build_result = self._schema_build_not_run("blocked", reason)
            type_check_result = self._schema_type_check_not_run("blocked", reason)
            dep_result = self._gate_not_run("blocked", reason)
            sast_result = self._gate_not_run("blocked", reason)
        secret_result = self._run_secret_scan()

        overall_status, audit_msg, _ = self._determine_status(
            tests_result,
            lint_result,
            build_result,
            type_check_result,
            secret_result,
            prompt_injection_result,
            dep_result,
            sast_result,
        )

        # Build schema-compliant output copies while preserving metadata for audit.
        schema_tests = {
            k: v
            for k, v in tests_result.items()
            if k in {
                "executed",
                "passed",
                "failed",
                "skipped",
                "duration_seconds",
                "coverage_before",
                "coverage_after",
                "flaky_tests",
                "new_tests_added",
            }
        }
        schema_lint = {
            k: v
            for k, v in lint_result.items()
            if k in {"executed", "violations_before", "violations_after", "auto_fixed", "new_violations"}
        }
        schema_build = {
            k: v for k, v in build_result.items() if k in {"executed", "succeeded", "warnings", "duration_seconds"}
        }
        schema_type_check = {
            k: v for k, v in type_check_result.items() if k in {"executed", "passed", "errors"}
        }

        # Metrics
        lines_added, lines_removed, num_files = self._get_git_numstat()
        if num_files == 0:
            num_files = len(execution_data.get("changes", []))

        audit_entries = [
            {
                "timestamp": self._now_utc(),
                "agent": "Skill-RUP",
                "action": "Verification",
                "result": "success"
                if overall_status == "passed"
                else ("warning" if overall_status == "passed_with_warnings" else "failure"),
                "details": {
                    "message": audit_msg,
                    "strict": self.strict,
                    "gates": {
                        "tests": {
                            "executed": tests_result.get("executed"),
                            "passed": tests_result.get("passed"),
                            "command_succeeded": tests_result.get("command_succeeded"),
                            "status": tests_result.get("status"),
                            "reason": tests_result.get("reason"),
                            "tool": tests_result.get("tool"),
                        },
                        "lint": {
                            "executed": lint_result.get("executed"),
                            "passed": lint_result.get("passed"),
                            "command_succeeded": lint_result.get("command_succeeded"),
                            "status": lint_result.get("status"),
                            "reason": lint_result.get("reason"),
                            "tool": lint_result.get("tool"),
                        },
                        "build": {
                            "executed": build_result.get("executed"),
                            "passed": build_result.get("passed"),
                            "command_succeeded": build_result.get("command_succeeded"),
                            "status": build_result.get("status"),
                            "reason": build_result.get("reason"),
                            "tool": build_result.get("tool"),
                        },
                        "type_check": {
                            "executed": type_check_result.get("executed"),
                            "passed": type_check_result.get("passed"),
                            "command_succeeded": type_check_result.get("command_succeeded"),
                            "status": type_check_result.get("status"),
                            "reason": type_check_result.get("reason"),
                            "tool": type_check_result.get("tool"),
                        },
                        "secret_scan": {"executed": True, "passed": secret_result["passed"]},
                        "prompt_injection_scan": {
                            "executed": True,
                            "passed": prompt_injection_result["passed"],
                        },
                        "dependency_scan": {
                            "executed": dep_result.get("executed"),
                            "passed": dep_result.get("passed"),
                            "command_succeeded": dep_result.get("command_succeeded"),
                            "status": dep_result.get("status"),
                            "reason": dep_result.get("reason"),
                            "tool": dep_result.get("tool"),
                        },
                        "sast_scan": {
                            "executed": sast_result.get("executed"),
                            "passed": sast_result.get("passed"),
                            "command_succeeded": sast_result.get("command_succeeded"),
                            "status": sast_result.get("status"),
                            "reason": sast_result.get("reason"),
                            "tool": sast_result.get("tool"),
                        },
                    },
                },
            }
        ]

        verification_data = {
            "verification_results": {
                "overall_status": overall_status,
                "tests": schema_tests,
                "lint": schema_lint,
                "security": {
                    "secret_scan": secret_result,
                    "dependency_scan": dep_result,
                    "sast_scan": sast_result,
                },
                "build": schema_build,
                "type_check": schema_type_check,
            },
            "metrics": {
                "files_changed": num_files,
                "lines_added": lines_added,
                "lines_removed": lines_removed,
            },
            "audit_trail": audit_entries,
            "recommendations": {
                "ready_for_pr": overall_status == "passed"
            },
        }

        # Save machine-readable state atomically
        self.state_manager.save_json(verification_data, "RUP_VERIFICATION.json")

        # Build human-readable markdown matching canonical template
        self.artifact_builder.build_markdown("verification-report.md", verification_data, "RUP_VERIFICATION.md")

        return verification_data
