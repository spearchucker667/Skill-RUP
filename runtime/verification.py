"""
verification module for RUP deterministic runtime.
"""
from typing import Dict, Any
from pathlib import Path
from .state import StateManager
from .artifact_builder import ArtifactBuilder

class VerificationPhase:
    def __init__(self, target_dir: Path, state_manager: StateManager, artifact_builder: ArtifactBuilder):
        self.target_dir = target_dir
        self.state_manager = state_manager
        self.artifact_builder = artifact_builder

    def _get_git_stats(self) -> int:
        """Get actual lines added via git diff."""
        from .command_runner import run_command
        try:
            rc, stdout, stderr = run_command(["git", "diff", "--shortstat", "HEAD"], cwd=self.target_dir)
            added = 0
            if rc == 0 and stdout:
                for part in stdout.split(","):
                    if "insertion" in part:
                        added = int(part.strip().split(" ")[0])
            return added
        except Exception:
            return 0

    def execute(self) -> Dict[str, Any]:
        """Run the verification phase based on execution state."""
        import subprocess
        from .command_runner import run_command
        
        execution_data = self.state_manager.load_json("RUP_EXECUTION.json")
        if not execution_data:
            raise RuntimeError("Missing RUP_EXECUTION.json. Must run execute first.")
            
        test_status = False
        test_executed = False
        lint_executed = False
        lint_passed = False
        
        # Test detection & 3-run flakiness check
        cmd = None
        if (self.target_dir / "pytest.ini").exists() or list(self.target_dir.rglob("test_*.py")) or (self.target_dir / "tests").is_dir() and list((self.target_dir / "tests").rglob("*.py")):
            cmd = ["python3", "-m", "pytest"]
        elif (self.target_dir / "package.json").exists():
            import json
            try:
                pkg = json.loads((self.target_dir / "package.json").read_text())
                if "test" in pkg.get("scripts", {}):
                    cmd = ["npm", "test"]
            except Exception:
                pass
        
        flaky_tests = []
        if cmd:
            test_executed = True
            runs = []
            for _ in range(3): # Flakiness 3-run standard
                try:
                    res = subprocess.run(cmd, cwd=self.target_dir, capture_output=True, text=True)
                    runs.append(res.returncode == 0)
                except Exception:
                    runs.append(False)
            
            test_status = all(runs)
            if any(runs) and not all(runs):
                flaky_tests = ["Identified flakiness in primary test suite"]

        # Lint detection
        lint_cmd = None
        if (self.target_dir / ".eslintrc.js").exists() or (self.target_dir / ".eslintrc.json").exists():
            lint_cmd = ["npm", "run", "lint"] # simplified
        elif (self.target_dir / ".flake8").exists() or (self.target_dir / "tox.ini").exists():
            lint_cmd = ["flake8"]
            
        if lint_cmd:
            lint_executed = True
            try:
                res = subprocess.run(lint_cmd, cwd=self.target_dir, capture_output=True, text=True)
                lint_passed = (res.returncode == 0)
            except Exception:
                lint_passed = False
                
        overall_status = "passed"
        if not test_executed:
            overall_status = "failed" # Fails fast if no verification mechanism exists
            audit_msg = "No automated tests found or executed. Manual verification required."
        elif not test_status:
            overall_status = "failed"
            audit_msg = "Test suite failed."
        elif lint_executed and not lint_passed:
            overall_status = "passed_with_warnings"
            audit_msg = "Tests passed, but linting failed."
        else:
            audit_msg = "All automated verification steps passed."
            
        import datetime
        timestamp = datetime.datetime.now(datetime.timezone.utc).isoformat()
        if not timestamp.endswith("Z"):
            timestamp = timestamp.replace("+00:00", "Z")
            
        verification_data = {
            "verification_results": {
                "overall_status": overall_status,
                "tests": {
                    "executed": test_executed,
                    "passed": 1 if test_status else 0,
                    "failed": 1 if test_executed and not test_status else 0,
                    "skipped": 0,
                    "duration_seconds": 3.0,
                    "flaky_tests": flaky_tests,
                    "new_tests_added": 0
                },
                "lint": {
                    "executed": lint_executed,
                    "violations_before": 0,
                    "violations_after": 1 if (lint_executed and not lint_passed) else 0,
                    "auto_fixed": 0,
                    "new_violations": []
                },
                "security": {
                    "secret_scan": {"executed": False, "passed": False, "findings": 0},
                    "dependency_scan": {"executed": False, "passed": False, "critical": 0, "high": 0, "medium": 0, "low": 0},
                    "sast_scan": {"executed": False, "passed": False, "findings": 0}
                },
                "build": {
                    "executed": False,
                    "succeeded": False,
                    "warnings": 0,
                    "duration_seconds": 0.0
                },
                "type_check": {
                    "executed": False,
                    "passed": False,
                    "errors": 0
                }
            },
            "metrics": {
                "files_changed": len(execution_data.get("changes", [])),
                "lines_added": self._get_git_stats(),
                "lines_removed": 0
            },
            "audit_trail": [
                {
                    "timestamp": timestamp,
                    "agent": "Skill-RUP",
                    "action": "Verification",
                    "result": "success" if overall_status == "passed" else ("warning" if overall_status == "passed_with_warnings" else "failure"),
                    "details": {"message": audit_msg}
                }
            ],
            "recommendations": {
                "ready_for_pr": overall_status == "passed"
            }
        }

        # Save machine-readable state
        self.state_manager.save_json(verification_data, "RUP_VERIFICATION.json")
        
        # Build human-readable markdown
        self.artifact_builder.build_markdown("verification-report.md", verification_data, "RUP_VERIFICATION.md")
        
        return verification_data
