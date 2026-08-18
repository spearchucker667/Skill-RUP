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
        
        # Simple backlog generation based on gaps
        backlog = []
        for i, gap in enumerate(gaps):
            backlog.append({
                "id": f"ITEM-00{i+1}",
                "priority": "P0" if gap.get("severity") == "high" else "P1",
                "title": gap.get("title", "Address gap")
            })
            
        # Select all items for execution
        selected_items = [item["id"] for item in backlog]
        
        plan_data = {
            "backlog": backlog,
            "selected_items": selected_items,
            "execution_order": selected_items,
            "estimated_effort": {
                "total_minutes": len(selected_items) * 30,
                "confidence": "medium"
            }
        }

        # Save machine-readable state
        self.state_manager.save_json(plan_data, "RUP_PLAN.json")
        
        # Build human-readable markdown
        self.artifact_builder.build_markdown("plan.md", plan_data, "RUP_PLAN.md")
        
        return plan_data
