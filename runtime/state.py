"""
state module for RUP deterministic runtime.
"""
import json
from pathlib import Path
from typing import Any, Dict
from .paths import RupPaths
from .security import enforce_path_jail

class StateManager:
    def __init__(self, paths: RupPaths):
        self.paths = paths
        
    def _get_artifact_path(self, filename: str) -> Path:
        """Get the secure path for a generated JSON artifact."""
        return self.paths.get_target_path(filename)
        
    def save_json(self, data: Dict[str, Any], filename: str) -> None:
        """Save state to a JSON file securely using atomic replacement."""
        import os
        import tempfile
        out_path = self._get_artifact_path(filename)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        
        fd, temp_path = tempfile.mkstemp(dir=out_path.parent, prefix=".", suffix=".tmp")
        try:
            with open(fd, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
            os.replace(temp_path, out_path)
        except Exception:
            os.unlink(temp_path)
            raise
            
    def load_json(self, filename: str) -> Dict[str, Any]:
        """Load state from a JSON file safely."""
        in_path = self._get_artifact_path(filename)
        if not in_path.exists():
            return {}
            
        with open(in_path, "r", encoding="utf-8") as f:
            return json.load(f)
            
    def load_protocol(self) -> Dict[str, Any]:
        """Load the canonical protocol definition."""
        from .security import safe_load_yaml
        proto_path = self.paths.protocol_dir / "rup-protocol.yaml"
        return safe_load_yaml(proto_path)
