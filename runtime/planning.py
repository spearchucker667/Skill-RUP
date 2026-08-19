"""
Planning phase module for RUP deterministic runtime.
Implements canonical Phase 2 Planning:
2.1 Backlog Generation (P0-P3 priority, tailored acceptance criteria)
2.2 Risk Analysis (breaking changes, manual review, rollback complexity)
2.3 Work Selection (time budget, max files, risk tolerance)
2.4 Execution Planning (dependency graph, topological sort, checkpoints, verification methods)
"""
from typing import Dict, Any, List, Optional
from pathlib import Path
from .state import StateManager
from .artifact_builder import ArtifactBuilder


class PlanningError(RuntimeError):
    """Raised when the planning phase encounters an invalid plan."""


PRIORITY_MAP = {
    "critical": "P0",
    "high": "P1",
    "medium": "P2",
    "low": "P3"
}

EFFORT_MINUTES = {
    "small": 10,
    "medium": 25,
    "large": 45
}

class PlanningPhase:
    def __init__(
        self,
        target_dir: Path,
        state_manager: StateManager,
        artifact_builder: ArtifactBuilder,
        time_budget_minutes: int = 45,
        max_files: int = 20,
        risk_tolerance: str = "medium"
    ):
        self.target_dir = target_dir
        self.state_manager = state_manager
        self.artifact_builder = artifact_builder
        self.time_budget_minutes = time_budget_minutes
        self.max_files = max_files
        self.risk_tolerance = risk_tolerance

    def _generate_backlog(self, gaps: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Transform discovery gaps into prioritized backlog items with acceptance criteria."""
        backlog = []
        for i, gap in enumerate(gaps):
            gid = gap.get("id", f"GAP-{i+1}")
            sev = gap.get("severity", "medium")
            priority = PRIORITY_MAP.get(sev, "P2")
            effort_str = gap.get("effort_estimate", "medium")
            mins = EFFORT_MINUTES.get(effort_str, 20)
            category = gap.get("category", "general")

            # Tailored acceptance criteria & verification methods
            acceptance_criteria = []
            verification_method = "Automated verification"
            dependencies = list(gap.get("dependencies", []))

            if category == "tests":
                acceptance_criteria = [
                    "Test framework configuration and baseline test runner are established",
                    "Initial test execution completes without syntax errors"
                ]
                verification_method = "Test runner execution (3x stability check)"
            elif category == "ci":
                acceptance_criteria = [
                    "CI workflow file exists under .github/workflows/",
                    "Workflow schema and steps are syntactically valid"
                ]
                verification_method = "Schema & YAML syntax validation"
                if any(g.get("category") == "tests" for g in gaps):
                    dependencies.append("TEST-001")
            elif category == "security":
                acceptance_criteria = [
                    "Security finding remediated or policy committed",
                    "No remaining raw credentials in tracked repository files"
                ]
                verification_method = "Secret scanner & dependency check"
            elif category == "docs":
                acceptance_criteria = [
                    f"Required documentation file '{gap.get('title', '')}' created with complete sections",
                    "No placeholder strings or broken links present"
                ]
                verification_method = "Documentation integrity check"
            elif category == "governance":
                acceptance_criteria = [
                    "Governance policy file created and formatted according to open-source standards"
                ]
                verification_method = "File structure & policy validation"
            else:
                acceptance_criteria = [f"Remediation for {gap.get('title', '')} is implemented and verified"]
                verification_method = "Static analysis & automated tests"

            # Estimate change risk
            risk_level = "low"
            if priority == "P0" or category == "security":
                risk_level = "medium" if effort_str != "large" else "high"
            elif priority == "P1" and effort_str == "large":
                risk_level = "medium"

            backlog.append({
                "id": gid,
                "priority": priority,
                "category": category,
                "title": gap.get("title", f"Remediate {gid}"),
                "description": gap.get("description", ""),
                "scope": {
                    "files": gap.get("files_affected", []),
                    "packages": []
                },
                "risk": risk_level,
                "estimated_effort_minutes": mins,
                "verification_method": verification_method,
                "dependencies": dependencies,
                "acceptance_criteria": acceptance_criteria
            })

        return backlog

    def _select_work(self, backlog: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Select items within time budget, max files, and risk tolerance.

        P0 items are mandatory-to-address but must still fit inside the
        configured run boundary. Items that violate constraints are escalated
        for explicit override rather than silently admitted.
        """
        priority_rank = {"P0": 0, "P1": 1, "P2": 2, "P3": 3}
        risk_rank = {"low": 0, "medium": 1, "high": 2}
        sorted_backlog = sorted(
            backlog,
            key=lambda x: (priority_rank.get(x["priority"], 9), x["estimated_effort_minutes"]),
        )

        selected: List[str] = []
        escalation: List[str] = []
        allocated_minutes = 0
        selected_files = 0
        tolerance_rank = risk_rank.get(self.risk_tolerance, 1)

        def _fits_constraints(item: Dict[str, Any], mins: int, file_count: int, item_risk_rank: int) -> bool:
            return (
                item_risk_rank <= tolerance_rank
                and allocated_minutes + mins <= self.time_budget_minutes
                and selected_files + file_count <= self.max_files
            )

        for item in sorted_backlog:
            mins = item["estimated_effort_minutes"]
            file_count = max(1, len(item.get("scope", {}).get("files", [])))
            item_risk_rank = risk_rank.get(item.get("risk", "low"), 0)

            if item["priority"] == "P0":
                if _fits_constraints(item, mins, file_count, item_risk_rank):
                    selected.append(item["id"])
                    allocated_minutes += mins
                    selected_files += file_count
                else:
                    escalation.append(item["id"])
            elif _fits_constraints(item, mins, file_count, item_risk_rank):
                selected.append(item["id"])
                allocated_minutes += mins
                selected_files += file_count

        # Fallback: select a single feasible high-value item if nothing else fit.
        if not selected and not escalation and backlog:
            for item in sorted_backlog:
                mins = item["estimated_effort_minutes"]
                file_count = max(1, len(item.get("scope", {}).get("files", [])))
                item_risk_rank = risk_rank.get(item.get("risk", "low"), 0)
                if _fits_constraints(item, mins, file_count, item_risk_rank):
                    selected.append(item["id"])
                    break

        return {
            "selected_items": selected,
            "selected_for_escalation": escalation,
            "requires_explicit_override": bool(escalation),
        }

    def _sequence_execution(self, selected_ids: List[str], backlog: List[Dict[str, Any]]) -> List[str]:
        """Topological sequencing of selected backlog items based on dependencies."""
        backlog_by_id = {b["id"]: b for b in backlog}
        selected_set = set(selected_ids)
        visiting: set[str] = set()
        visited: set[str] = set()
        ordered: list[str] = []

        def visit(item_id: str) -> None:
            if item_id in visiting:
                raise PlanningError(f"Dependency cycle detected involving {item_id}")
            if item_id in visited or item_id not in selected_set:
                return
            if item_id not in backlog_by_id:
                visited.add(item_id)
                return
            visiting.add(item_id)
            for dep in backlog_by_id[item_id].get("dependencies", []):
                if dep in selected_set:
                    visit(dep)
            visiting.remove(item_id)
            visited.add(item_id)
            ordered.append(item_id)

        for sid in selected_ids:
            visit(sid)

        return ordered

    def _analyze_plan_risk(self, selected_items: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Analyze risks of planned execution."""
        breaking_possible = any(item["risk"] == "high" for item in selected_items)
        requires_manual_review = any("SEC-001" in item["id"] or item["risk"] == "high" for item in selected_items)
        
        rollback_complexity = "trivial"
        if len(selected_items) > 5 or breaking_possible:
            rollback_complexity = "moderate"

        return {
            "breaking_changes_possible": breaking_possible,
            "requires_manual_review": requires_manual_review,
            "rollback_complexity": rollback_complexity,
            "affected_packages": []
        }

    def execute(self) -> Dict[str, Any]:
        """Run the planning phase based on discovery state."""
        discovery_data = self.state_manager.load_json("RUP_DISCOVERY.json")
        if not discovery_data:
            raise RuntimeError("Missing RUP_DISCOVERY.json. Must run discovery first.")

        gaps = discovery_data.get("gaps", [])
        backlog = self._generate_backlog(gaps)
        selection = self._select_work(backlog)
        selected_ids = selection["selected_items"]
        execution_order = self._sequence_execution(selected_ids, backlog)

        selected_items = [b for b in backlog if b["id"] in selected_ids]
        risk_analysis = self._analyze_plan_risk(selected_items)

        total_effort = sum(b["estimated_effort_minutes"] for b in selected_items)

        constraints = {
            "time_budget_minutes": self.time_budget_minutes,
            "max_files": self.max_files,
            "risk_tolerance": self.risk_tolerance,
        }

        plan_data = {
            "constraints": constraints,
            "backlog": backlog,
            "selected_items": selected_ids,
            "selected_for_escalation": selection["selected_for_escalation"],
            "requires_explicit_override": selection["requires_explicit_override"],
            "execution_order": execution_order,
            "risk_analysis": risk_analysis,
            "estimated_effort": {
                "total_minutes": total_effort,
                "confidence": "high",
                "breakdown": {item["id"]: item["estimated_effort_minutes"] for item in selected_items}
            }
        }

        # Save machine-readable state atomically
        self.state_manager.save_json(plan_data, "RUP_PLAN.json")

        # Build human-readable markdown matching canonical template
        self.artifact_builder.build_markdown("plan.md", plan_data, "RUP_PLAN.md")

        return plan_data

