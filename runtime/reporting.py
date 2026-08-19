"""
Reporting phase module for RUP deterministic runtime.
Implements canonical Phase 4 Reporting & Handoff:
- Complete lifecycle aggregation (Discovery, Planning, Execution, Verification)
- Metrics delta and technical debt / readiness progression
- Evidence-backed change summary
- Follow-ups for unselected/remaining items
- Rollback commands
- Truthful publication instructions (no false PR merge claims)
"""
import warnings
from typing import Dict, Any, List, Set
from pathlib import Path
from .state import StateManager
from .artifact_builder import ArtifactBuilder
from .command_runner import run_command

class ReportingPhase:
    def __init__(self, target_dir: Path, state_manager: StateManager, artifact_builder: ArtifactBuilder):
        self.target_dir = target_dir
        self.state_manager = state_manager
        self.artifact_builder = artifact_builder

    def _get_git_branch(self) -> str:
        """Get current git branch name."""
        try:
            rc, stdout, _ = run_command(["git", "branch", "--show-current"], cwd=self.target_dir)
            if rc == 0 and stdout.strip():
                return stdout.strip()
        except Exception as e:
            warnings.warn(f"Git branch query failed: {e}", RuntimeWarning, stacklevel=2)
        return "local-workspace"

    def execute(self) -> Dict[str, Any]:
        """Generate comprehensive final report and handoff package."""
        discovery_data = self.state_manager.load_json("RUP_DISCOVERY.json")
        plan_data = self.state_manager.load_json("RUP_PLAN.json")
        execution_data = self.state_manager.load_json("RUP_EXECUTION.json")
        verification_data = self.state_manager.load_json("RUP_VERIFICATION.json")
        execution_state = self.state_manager.load_json("execution-state.json")

        if not (discovery_data and plan_data and execution_data and verification_data):
            raise RuntimeError("Missing previous lifecycle phase states. Cannot generate final report.")

        ver_res = verification_data.get("verification_results", {})
        overall_status = ver_res.get("overall_status", "unknown")
        metrics = verification_data.get("metrics", {})
        changes = execution_data.get("changes", [])
        backlog = plan_data.get("backlog", [])
        selected_ids = set(plan_data.get("selected_items", []))

        # Determine which selected items did not complete.
        completion = execution_state.get("per_item_completion", {}) if execution_state else {}
        incomplete_selected: Set[str] = {
            item_id for item_id in selected_ids
            if completion.get(item_id, "COMPLETE") != "COMPLETE"
        }

        # Determine follow-ups (unselected items and incomplete selected items)
        followups = []
        for b in backlog:
            if b["id"] not in selected_ids:
                followups.append({
                    "id": b["id"],
                    "priority": b["priority"],
                    "title": b["title"],
                    "category": b["category"],
                    "estimated_effort_minutes": b["estimated_effort_minutes"],
                    "reason": "not_selected",
                })
            elif b["id"] in incomplete_selected:
                followups.append({
                    "id": b["id"],
                    "priority": b["priority"],
                    "title": b["title"],
                    "category": b["category"],
                    "estimated_effort_minutes": b["estimated_effort_minutes"],
                    "reason": "incomplete",
                    "disposition": completion.get(b["id"], "UNKNOWN"),
                })

        # Rollback commands
        rollback_cmds = []
        created_files = [c["file_path"] for c in changes if c.get("change_type") == "create"]
        modified_files = [c["file_path"] for c in changes if c.get("change_type") in ("modify", "delete", "rename")]

        if modified_files:
            rollback_cmds.append(f"git checkout -- {' '.join(modified_files)}")
        if created_files:
            rollback_cmds.append(f"rm -f {' '.join(created_files)}")
        if not rollback_cmds:
            rollback_cmds.append("# No changes to revert")

        branch = self._get_git_branch()
        is_ready = (overall_status == "passed" and not incomplete_selected)

        if is_ready:
            handoff_instructions = f"Verification passed on branch '{branch}'. Review changes with 'git diff' and commit/push to submit a pull request."
        else:
            handoff_instructions = f"Verification status is '{overall_status}'. Inspect verification report findings and resolve remaining issues before submission."

        report_data = {
            "summary": {
                "overall_status": overall_status,
                "total_items_processed": len(selected_ids),
                "total_changes": len(changes),
                "ready_for_submission": is_ready
            },
            "phases_completed": ["discovery", "plan", "execution", "verification"],
            "metrics": {
                "production_readiness_score": discovery_data.get("risk_assessment", {}).get("production_readiness_score", 100),
                "technical_debt_score": discovery_data.get("risk_assessment", {}).get("technical_debt_score", 0),
                "files_changed": metrics.get("files_changed", len(changes)),
                "lines_added": metrics.get("lines_added", 0),
                "lines_removed": metrics.get("lines_removed", 0),
                "test_duration_seconds": ver_res.get("tests", {}).get("duration_seconds", 0.0),
                "tests_passed": ver_res.get("tests", {}).get("passed", 0),
                "tests_failed": ver_res.get("tests", {}).get("failed", 0)
            },
            "changes_summary": [
                {
                    "file": c.get("file_path", ""),
                    "type": c.get("change_type", "modify"),
                    "rationale": c.get("rationale", "")
                } for c in changes
            ],
            "followups": followups,
            "rollback_procedure": {
                "commands": rollback_cmds,
                "complexity": plan_data.get("risk_analysis", {}).get("rollback_complexity", "low")
            },
            "handoff_instructions": handoff_instructions
        }

        # Save machine-readable state atomically
        self.state_manager.save_json(report_data, "RUP_FINAL_REPORT.json")

        # Build human-readable markdown matching canonical template
        self.artifact_builder.build_markdown("final-report.md", report_data, "RUP_FINAL_REPORT.md")

        return report_data

