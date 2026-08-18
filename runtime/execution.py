"""
execution module for RUP deterministic runtime.
"""
from typing import Dict, Any
from pathlib import Path
from .state import StateManager
from .artifact_builder import ArtifactBuilder
from .command_runner import run_command

class ExecutionPhase:
    def __init__(self, target_dir: Path, state_manager: StateManager, artifact_builder: ArtifactBuilder):
        self.target_dir = target_dir
        self.state_manager = state_manager
        self.artifact_builder = artifact_builder

    def execute(self) -> Dict[str, Any]:
        """Run the execution phase by checking genuine git diffs."""
        plan_data = self.state_manager.load_json("RUP_PLAN.json")
        if not plan_data:
            raise RuntimeError("Missing RUP_PLAN.json. Must run plan first.")
            
        changes = []
        commits = []
        
        # Detect uncommitted changes via git status
        try:
            rc, stdout, stderr = run_command(["git", "status", "--porcelain"], cwd=self.target_dir)
            if rc == 0:
                for line in stdout.splitlines():
                    if not line.strip():
                        continue
                    code = line[:2]
                    file_path = line[3:]
                    
                    change_type = "modify"
                    if "??" in code or "A" in code:
                        change_type = "create"
                    elif "D" in code:
                        change_type = "delete"
                    elif "R" in code:
                        change_type = "rename"
                        
                    changes.append({
                        "file_path": file_path,
                        "change_type": change_type,
                        "rationale": "Detected uncommitted change",
                        "backlog_item_id": plan_data.get("selected_items", [""])[0] if plan_data.get("selected_items") else "UNKNOWN"
                    })
        except Exception:
            pass # Git might not be initialized
            
        # Extract recent commits (last 5)
        try:
            rc, stdout, stderr = run_command(["git", "log", "-n", "5", "--oneline"], cwd=self.target_dir)
            if rc == 0:
                for line in stdout.splitlines():
                    if not line.strip():
                        continue
                    parts = line.split(" ", 1)
                    commits.append({
                        "hash": parts[0],
                        "message": parts[1] if len(parts) > 1 else "",
                        "files": [],
                        "type": "commit",
                        "breaking": "BREAKING CHANGE" in line,
                        "backlog_item_ids": []
                    })
        except Exception:
            pass
            
        execution_data = {
            "changes": changes,
            "commits": commits,
            "local_verification": {
                "tests": {"executed": False, "passed": False},
                "lint": {"executed": False, "passed": False},
                "build": {"executed": False, "passed": False},
                "type_check": {"executed": False, "passed": False}
            },
            "artifacts": []
        }

        # Save machine-readable state
        self.state_manager.save_json(execution_data, "RUP_EXECUTION.json")
        
        # Build human-readable markdown
        self.artifact_builder.build_markdown("execution-report.md", execution_data, "RUP_EXECUTION.md")
        
        return execution_data
