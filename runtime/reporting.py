"""
reporting module for RUP deterministic runtime.
"""
from typing import Dict, Any
from pathlib import Path
from .state import StateManager
from .artifact_builder import ArtifactBuilder

class ReportingPhase:
    def __init__(self, target_dir: Path, state_manager: StateManager, artifact_builder: ArtifactBuilder):
        self.target_dir = target_dir
        self.state_manager = state_manager
        self.artifact_builder = artifact_builder

    def execute(self) -> Dict[str, Any]:
        """Run the reporting phase based on all previous states."""
        # Read prior state files
        discovery_data = self.state_manager.load_json("RUP_DISCOVERY.json")
        plan_data = self.state_manager.load_json("RUP_PLAN.json")
        execution_data = self.state_manager.load_json("RUP_EXECUTION.json")
        verification_data = self.state_manager.load_json("RUP_VERIFICATION.json")
        
        if not (discovery_data and plan_data and execution_data and verification_data):
            raise RuntimeError("Missing previous lifecycle phase states. Cannot generate final report.")
            
        # Stub logic to aggregate data into the final report format
        report_data = {
            "summary": {
                "overall_status": verification_data.get("verification_results", {}).get("overall_status", "unknown"),
                "total_items_processed": len(plan_data.get("selected_items", [])),
                "total_changes": len(execution_data.get("changes", []))
            },
            "phases_completed": ["discovery", "plan", "execution", "verification"],
            "handoff_instructions": "Review RUP_FINAL_REPORT.md for details and merge the resulting PR."
        }

        # Save machine-readable state
        self.state_manager.save_json(report_data, "RUP_FINAL_REPORT.json")
        
        # Build human-readable markdown
        self.artifact_builder.build_markdown("final-report.md", report_data, "RUP_FINAL_REPORT.md")
        
        return report_data
