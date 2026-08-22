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
from .discovery import DiscoveryPhase
from .inventory import InventoryManager
from .rollback import render_rollback_commands
from .tool_detection import ToolDetector

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

    def _rescore_after_execution(
        self, discovery_data: Dict[str, Any], verification_status: str
    ) -> Dict[str, Any]:
        """Recompute readiness/debt against the post-execution repository state.

        The canonical discovery scorer is reused so that newly created files and
        resolved gaps are reflected. Verification failures are then applied as an
        additional penalty because the repository is not yet submission-ready.
        """
        try:
            inventory = InventoryManager(self.target_dir).analyze_inventory()
            languages = inventory["languages"]
            metadata = InventoryManager(self.target_dir).get_repo_metadata()
            tooling = ToolDetector(self.target_dir).detect_all()
            # Use DiscoveryPhase helper methods without overwriting the saved
            # discovery artifact from the start of the run.
            discovery = DiscoveryPhase(self.target_dir, self.state_manager, self.artifact_builder)
            gaps_after = discovery._evaluate_all_gaps(metadata, languages, tooling)
            risk_after = discovery._calculate_risk_and_scores(gaps_after, metadata)
            readiness_after = risk_after["production_readiness_score"]
            debt_after = risk_after["technical_debt_score"]
        except Exception as e:
            warnings.warn(f"Could not rescore repository after execution: {e}", RuntimeWarning, stacklevel=2)
            readiness_after = discovery_data.get("risk_assessment", {}).get("production_readiness_score", 100)
            debt_after = discovery_data.get("risk_assessment", {}).get("technical_debt_score", 0)

        # Verification status modifies the score: a failed run is not ready.
        if verification_status == "failed":
            readiness_after = max(0, readiness_after - 20)
            debt_after = min(100, debt_after + 20)
        elif verification_status == "passed_with_warnings":
            readiness_after = max(0, readiness_after - 10)
            debt_after = min(100, debt_after + 10)

        return {
            "readiness_after": readiness_after,
            "debt_after": debt_after,
        }

    def execute(self) -> Dict[str, Any]:
        """Generate comprehensive final report and handoff package."""
        discovery_data = self.state_manager.load_json("RUP_DISCOVERY.json")
        plan_data = self.state_manager.load_json("RUP_PLAN.json")
        plan_state = self.state_manager.load_json("plan-state.json")
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
        execution_state_valid = isinstance(execution_state, dict)
        completion = execution_state.get("per_item_completion", {}) if execution_state_valid else {}
        incomplete_selected: Set[str] = set()
        for item_id in selected_ids:
            if not execution_state_valid:
                incomplete_selected.add(item_id)
            else:
                disp = completion.get(item_id, "UNKNOWN")
                if disp != "COMPLETE":
                    incomplete_selected.add(item_id)
        completed_count = len(selected_ids) - len(incomplete_selected)

        # Escalated P0 items also block submission, even though they were never
        # admitted to the selected set.
        escalated_ids: Set[str] = set(plan_state.get("selected_for_escalation", []))

        # Recompute readiness/debt against the post-execution repository state.
        readiness_before = discovery_data.get("risk_assessment", {}).get("production_readiness_score", 100)
        debt_before = discovery_data.get("risk_assessment", {}).get("technical_debt_score", 0)
        after_scores = self._rescore_after_execution(discovery_data, overall_status)
        readiness_after = after_scores["readiness_after"]
        debt_after = after_scores["debt_after"]

        # Determine follow-ups (escalated items, incomplete selected items, and
        # unselected backlog items).
        followups = []
        for b in backlog:
            if b["id"] in escalated_ids:
                followups.append({
                    "id": b["id"],
                    "priority": b["priority"],
                    "title": b["title"],
                    "category": b["category"],
                    "estimated_effort_minutes": b["estimated_effort_minutes"],
                    "reason": "escalated",
                    "requires_explicit_override": True,
                })
            elif b["id"] in incomplete_selected:
                followups.append({
                    "id": b["id"],
                    "priority": b["priority"],
                    "title": b["title"],
                    "category": b["category"],
                    "estimated_effort_minutes": b["estimated_effort_minutes"],
                    "reason": "incomplete",
                    "disposition": completion.get(b["id"], "UNKNOWN") if execution_state_valid else "UNKNOWN",
                })
            elif b["id"] not in selected_ids:
                followups.append({
                    "id": b["id"],
                    "priority": b["priority"],
                    "title": b["title"],
                    "category": b["category"],
                    "estimated_effort_minutes": b["estimated_effort_minutes"],
                    "reason": "not_selected",
                })

        # Rollback: consume the single platform-neutral representation produced
        # by the execution phase (audit P1-28). execution-state.json is
        # authoritative; RUP_EXECUTION.json rollback_procedure is the fallback;
        # reconstructing from raw changes is the legacy path for stale artifacts
        # and emits a deprecation warning.
        rollback_operations: List[Dict[str, Any]] = []
        if execution_state_valid and execution_state.get("rollback_operations"):
            rollback_operations = execution_state["rollback_operations"]
        elif execution_data.get("rollback_procedure", {}).get("operations"):
            rollback_operations = execution_data["rollback_procedure"]["operations"]
        else:
            created_files = [c["file_path"] for c in changes if c.get("change_type") == "create"]
            modified_files = [c["file_path"] for c in changes if c.get("change_type") in ("modify", "delete", "rename")]
            if created_files or modified_files:
                warnings.warn(
                    "No structured rollback operations found; reconstructing from changes "
                    "(legacy artifacts). Re-run execute to record authoritative rollback ops.",
                    RuntimeWarning,
                    stacklevel=2,
                )
                rollback_operations = [
                    *({"op": "remove_file", "path": p} for p in created_files),
                    *({"op": "restore_content", "path": p} for p in modified_files),
                ]
        rollback_cmds = render_rollback_commands(rollback_operations, platform="posix")
        if not rollback_operations:
            rollback_cmds.append("# No changes to revert")

        # Monorepo aggregate (audit P1-11): per-package change rollup from the
        # execution phase's package graph, when a workspace was detected.
        workspace_summary = None
        if execution_state_valid and execution_state.get("package_changes"):
            package_changes = execution_state["package_changes"]
            workspace_summary = {
                "packages": {
                    name: {
                        "files_changed": len(files),
                        "files": sorted(files),
                    }
                    for name, files in sorted(package_changes.items())
                }
            }

        branch = self._get_git_branch()
        is_ready = (
            overall_status == "passed"
            and not incomplete_selected
            and not escalated_ids
        )

        if is_ready:
            handoff_instructions = f"Verification passed on branch '{branch}'. Review changes with 'git diff' and commit/push to submit a pull request."
        else:
            handoff_instructions = f"Verification status is '{overall_status}'. Inspect verification report findings and resolve remaining issues before submission."

        report_data = {
            "summary": {
                "overall_status": overall_status,
                "total_items_selected": len(selected_ids),
                "total_items_processed": completed_count,
                "total_changes": len(changes),
                "ready_for_submission": is_ready
            },
            "phases_completed": ["discovery", "plan", "execution", "verification", "reporting"],
            "metrics": {
                "production_readiness_score": readiness_after,
                "technical_debt_score": debt_after,
                "readiness_before": readiness_before,
                "readiness_after": readiness_after,
                "readiness_delta": readiness_after - readiness_before,
                "debt_before": debt_before,
                "debt_after": debt_after,
                "debt_delta": debt_after - debt_before,
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
                "operations": rollback_operations,
                "commands": rollback_cmds,
                "by_item": (
                    execution_state.get("rollback_by_item", {})
                    if execution_state_valid and execution_state.get("rollback_by_item")
                    else {}
                ),
                "complexity": plan_data.get("risk_analysis", {}).get("rollback_complexity", "low")
            },
            "workspace_summary": workspace_summary,
            "handoff_instructions": handoff_instructions
        }

        # Save machine-readable state atomically
        self.state_manager.save_json(report_data, "RUP_FINAL_REPORT.json")

        # Build human-readable markdown matching canonical template
        self.artifact_builder.build_markdown("final-report.md", report_data, "RUP_FINAL_REPORT.md")

        return report_data

