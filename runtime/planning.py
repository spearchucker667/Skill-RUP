"""
Planning phase module for RUP deterministic runtime.
Implements canonical Phase 2 Planning:
2.1 Backlog Generation (P0-P3 priority, tailored acceptance criteria)
2.2 Risk Analysis (breaking changes, manual review, rollback complexity)
2.3 Work Selection (time budget, max files, risk tolerance)
2.4 Execution Planning (dependency graph, topological sort, checkpoints, verification methods)
"""
import warnings
from typing import Dict, Any, List, Optional
from pathlib import Path
from .state import StateManager
from .artifact_builder import ArtifactBuilder

# Per-category checkpoint definitions (RUP-PLAN-004): each selected workstream
# carries a verification method, success criteria, and per-item rollback so the
# execution phase can enforce workstream checkpoints instead of a single global
# verification pass (audit P1-13).
_CHECKPOINT_METHODS: Dict[str, Dict[str, str]] = {
    "tests": {
        "method": "test",
        "success_criteria": "Test suite passes with no new failures (3-run flakiness detection).",
    },
    "dx": {
        "method": "lint_or_type_check",
        "success_criteria": "Linter or type checker exits 0 with zero violations.",
    },
    "ci": {
        "method": "file_validation",
        "success_criteria": "Generated CI workflow exists and is syntactically valid YAML.",
    },
    "security": {
        "method": "scan",
        "success_criteria": "No new secrets; secret-scan coverage complete.",
    },
    "docs": {
        "method": "existence",
        "success_criteria": "Documentation file exists and is non-empty.",
    },
    "governance": {
        "method": "existence",
        "success_criteria": "Governance file exists; placeholders require manual completion.",
    },
    "bugs": {
        "method": "test",
        "success_criteria": "Failing test reproduces the bug; fix passes the test 3 times.",
    },
}


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

        # RUP-PLAN-003: enforce dependency closure. A selected item may only be
        # admitted together with its mandatory dependencies (recursively); the
        # canonical planning reference requires dependencies to execute first.
        # If admitting a dependency would break the budget/risk boundary, the
        # dependent item is escalated instead of executing without its deps
        # (audit P1-12).
        closure_admitted: List[str] = []
        selected_set = set(selected)
        backlog_by_id = {b["id"]: b for b in backlog}
        queue: List[str] = list(selected)
        while queue:
            item_id = queue.pop(0)
            item = backlog_by_id.get(item_id)
            if not item:
                continue
            for dep_id in item.get("dependencies", []):
                if dep_id in selected_set:
                    continue
                dep = backlog_by_id.get(dep_id)
                if dep is None:
                    warnings.warn(
                        f"Backlog item {item_id} depends on {dep_id}, which is not in the "
                        "backlog; treating it as an external dependency.",
                        RuntimeWarning,
                        stacklevel=2,
                    )
                    continue
                mins = dep["estimated_effort_minutes"]
                file_count = max(1, len(dep.get("scope", {}).get("files", [])))
                dep_risk_rank = risk_rank.get(dep.get("risk", "low"), 0)
                if dep["priority"] == "P0" or _fits_constraints(dep, mins, file_count, dep_risk_rank):
                    selected_set.add(dep_id)
                    selected.append(dep_id)
                    allocated_minutes += mins
                    selected_files += file_count
                    closure_admitted.append(dep_id)
                    queue.append(dep_id)
                else:
                    # The dependency cannot be admitted within the run boundary;
                    # the dependent item must not run without it.
                    if item_id not in escalation:
                        escalation.append(item_id)
                    if item_id in selected_set:
                        selected_set.discard(item_id)
                        selected.remove(item_id)

        return {
            "selected_items": selected,
            "selected_for_escalation": escalation,
            "requires_explicit_override": bool(escalation),
            "closure_admitted": closure_admitted,
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

    @staticmethod
    def _checkpoint_for_item(item: Dict[str, Any]) -> Dict[str, Any]:
        """Derive the checkpoint (verification method + success criteria) for one item."""
        category = item.get("category", "")
        title = (item.get("title") or "").lower()
        spec = _CHECKPOINT_METHODS.get(category, {"method": "existence", "success_criteria": "Workstream artifact exists and is non-empty."})
        method = spec["method"]
        if category == "dx":
            method = "type_check" if "type" in title else "lint"
        return {
            "backlog_item_id": item["id"],
            "verification_method": method,
            "success_criteria": spec["success_criteria"],
            "rollback": "Per-item rollback operations recorded by the execution phase (restore_content / remove_file / restore_deleted / move_back).",
        }

    def _build_checkpoints(self, selected_items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Build the per-workstream checkpoint graph for the selected plan (audit P1-13)."""
        return [self._checkpoint_for_item(item) for item in selected_items]

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

        # Canonical RUP_PLAN.json contains only the upstream PlanOutput contract.
        # Skill-only planning metadata (constraints, escalations, override flag)
        # lives in plan-state.json so the canonical artifact remains byte-compatible.
        plan_data = {
            "backlog": backlog,
            "selected_items": selected_ids,
            "execution_order": execution_order,
            "risk_analysis": risk_analysis,
            "estimated_effort": {
                "total_minutes": total_effort,
                "confidence": "high",
                "breakdown": {item["id"]: item["estimated_effort_minutes"] for item in selected_items}
            }
        }

        checkpoints = self._build_checkpoints(selected_items)

        plan_state = {
            "constraints": constraints,
            "selected_for_escalation": selection["selected_for_escalation"],
            "requires_explicit_override": selection["requires_explicit_override"],
            "closure_admitted": selection.get("closure_admitted", []),
            "checkpoints": checkpoints,
        }

        # Save machine-readable state atomically
        self.state_manager.save_json(plan_data, "RUP_PLAN.json")
        self.state_manager.save_json(plan_state, "plan-state.json")

        # Build human-readable markdown matching canonical template; the markdown
        # renderer expects constraints alongside the canonical plan fields.
        render_data = {**plan_data, **plan_state}
        self.artifact_builder.build_markdown("plan.md", render_data, "RUP_PLAN.md")

        return plan_data

