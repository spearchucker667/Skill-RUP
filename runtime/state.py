"""
State management, run manifest generation, and atomic persistence for RUP deterministic runtime.
"""
import json
import os
import tempfile
import datetime
from pathlib import Path
from typing import Any, Dict, Optional, List
from .paths import RupPaths
from .models import RunManifest, SessionState
from .security import enforce_path_jail, safe_load_yaml, safe_load_json
from .command_runner import run_command

class StateManager:
    def __init__(self, paths: RupPaths, run_id: Optional[str] = None):
        self.paths = paths
        self.run_id = run_id or RunManifest.generate_run_id()
        self._session_state: Optional[SessionState] = None

    def _get_artifact_path(self, filename: str) -> Path:
        """Get the secure path for an artifact, placing state in .rup/ state directory."""
        return self.paths.get_state_path(filename)

    def save_json(self, data: Dict[str, Any], filename: str) -> Path:
        """Save state to a JSON file securely using atomic replacement."""
        out_path = self._get_artifact_path(filename)
        out_path.parent.mkdir(parents=True, exist_ok=True)

        fd, temp_path = tempfile.mkstemp(dir=out_path.parent, prefix=".rup_tmp_", suffix=".json")
        try:
            with open(fd, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
            os.replace(temp_path, out_path)
        except Exception:
            if os.path.exists(temp_path):
                os.unlink(temp_path)
            raise

        self._record_artifact(filename)
        return out_path

    def load_json(self, filename: str) -> Dict[str, Any]:
        """Load state from a JSON file safely from state directory or target directory."""
        in_path = self._get_artifact_path(filename)
        if not in_path.exists():
            # Fallback to target root if previously written there
            fallback_path = self.paths.get_target_path(filename)
            if fallback_path.exists():
                in_path = fallback_path
            else:
                return {}

        return safe_load_json(in_path)

    def load_protocol(self) -> Dict[str, Any]:
        """Load the canonical protocol definition."""
        proto_path = self.paths.protocol_dir / "rup-protocol.yaml"
        return safe_load_yaml(proto_path)

    def _get_target_commit(self) -> str:
        """Get target repository commit SHA if git is initialized."""
        try:
            rc, stdout, _ = run_command(["git", "rev-parse", "HEAD"], cwd=self.paths.target_dir)
            if rc == 0 and stdout.strip():
                return stdout.strip()
        except Exception:
            pass
        return "UNKNOWN_UNCOMMITTED"

    def generate_and_save_manifest(
        self,
        phases_completed: List[str],
        selected_items: List[str],
        execution_changes_count: int,
        verification_status: str
    ) -> Dict[str, Any]:
        """Create and persist a complete RunManifest artifact."""
        now_str = datetime.datetime.now(datetime.timezone.utc).isoformat()
        if not now_str.endswith("Z"):
            now_str = now_str.replace("+00:00", "Z")

        manifest = {
            "run_id": self.run_id,
            "created_at": now_str,
            "protocol_version": "3.0.0",
            "canonical_commit": "c3d6f70375db15d53db2fba76d70b5b7c9cf98bb",
            "target_path": str(self.paths.target_dir),
            "target_commit": self._get_target_commit(),
            "phases_completed": phases_completed,
            "selected_items": selected_items,
            "execution_changes_count": execution_changes_count,
            "verification_status": verification_status
        }
        self.save_json(manifest, "run-manifest.json")
        return manifest

    def update_session_state(self, phase: str) -> Dict[str, Any]:
        """Update and persist current lifecycle session state."""
        now_str = datetime.datetime.now(datetime.timezone.utc).isoformat()
        if not now_str.endswith("Z"):
            now_str = now_str.replace("+00:00", "Z")

        state = {
            "run_id": self.run_id,
            "current_phase": phase,
            "timestamp": now_str,
            "artifacts_generated": self._get_generated_artifacts()
        }
        self.save_json(state, "session-state.json")
        return state

    def _record_artifact(self, filename: str) -> None:
        pass

    def _get_generated_artifacts(self) -> List[str]:
        artifacts = []
        for p in self.paths.state_dir.glob("*.json"):
            artifacts.append(p.name)
        for p in self.paths.state_dir.glob("*.md"):
            artifacts.append(p.name)
        return sorted(artifacts)

