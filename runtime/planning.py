"""
planning module for RUP deterministic runtime.
"""
from typing import Dict, Any
from pathlib import Path
from .state import StateManager
from .artifact_builder import ArtifactBuilder

class PlanningPhase:
    def __init__(self, target_dir: Path, state_manager: StateManager, artifact_builder: ArtifactBuilder):
        self.target_dir = target_dir
        self.state_manager = state_manager
        self.artifact_builder = artifact_builder

    def execute(self) -> Dict[str, Any]:
        """Run the planning phase based on discovery state."""
        discovery_data = self.state_manager.load_json("RUP_DISCOVERY.json")
        if not discovery_data:
            raise RuntimeError("Missing RUP_DISCOVERY.json. Must run discovery first.")
            
        gaps = discovery_data.get("gaps", [])
        
        # Simple backlog generation based on genuine gaps
        backlog = []
        total_effort = 0
        for i, gap in enumerate(gaps):
            priority = "P0" if gap.get("severity") in ("high", "critical") else "P1"
            effort_str = gap.get("effort_estimate", "medium")
            mins = 15 if effort_str == "small" else 30 if effort_str == "medium" else 60
            total_effort += mins
            
            backlog.append({
                "id": gap.get("id", f"ITEM-{i}"),
                "priority": priority,
                "category": gap.get("category", "general"),
                "title": gap.get("title", "Address gap"),
                "description": gap.get("description", ""),
                "scope": {
                    "files": gap.get("files_affected", []),
                    "packages": []
                },
                "risk": "low" if priority != "P0" else "medium",
                "estimated_effort_minutes": mins,
                "verification_method": "Automated pipeline",
                "dependencies": [],
                "acceptance_criteria": ["Gap is resolved"]
            })
            
        # Select all items for execution
        selected_items = [item["id"] for item in backlog]
        
        plan_data = {
            "backlog": backlog,
            "selected_items": selected_items,
            "execution_order": selected_items,
            "risk_analysis": {
                "breaking_changes_possible": False,
                "requires_manual_review": False,
                "rollback_complexity": "trivial",
                "affected_packages": []
            },
            "estimated_effort": {
                "total_minutes": total_effort,
                "confidence": "high",
                "breakdown": { item["id"]: item["estimated_effort_minutes"] for item in backlog }
            }
        }

        # Save machine-readable state
        self.state_manager.save_json(plan_data, "RUP_PLAN.json")
        
        # Build human-readable markdown
        self.artifact_builder.build_markdown("plan.md", plan_data, "RUP_PLAN.md")
        
        return plan_data
