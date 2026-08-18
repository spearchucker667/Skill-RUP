"""
inventory module for RUP deterministic runtime.
"""
from pathlib import Path
from typing import Dict, Any, List

class InventoryManager:
    def __init__(self, target_dir: Path):
        self.target_dir = target_dir
        
    def detect_languages(self) -> List[Dict[str, Any]]:
        """Simple language detector based on lockfiles and extensions."""
        languages = []
        if (self.target_dir / "package.json").exists() or (self.target_dir / "package-lock.json").exists():
            languages.append({"name": "javascript/typescript", "percentage": 100, "lockfile_present": True})
            
        if (self.target_dir / "requirements.txt").exists() or (self.target_dir / "pyproject.toml").exists():
            languages.append({"name": "python", "percentage": 100, "lockfile_present": True})
            
        if (self.target_dir / "go.mod").exists():
            languages.append({"name": "go", "percentage": 100, "lockfile_present": True})
            
        if not languages:
            languages.append({"name": "unknown", "percentage": 100, "lockfile_present": False})
            
        return languages
        
    def detect_tooling(self, languages: List[Dict[str, Any]]) -> Dict[str, str]:
        """Simple toolchain detector."""
        tooling = {}
        for lang in languages:
            if lang["name"] == "python":
                if (self.target_dir / "pytest.ini").exists():
                    tooling["test_framework"] = "pytest"
                if (self.target_dir / ".ruff.toml").exists() or (self.target_dir / "ruff.toml").exists():
                    tooling["linter"] = "ruff"
        return tooling

    def get_repo_metadata(self) -> Dict[str, Any]:
        """Generate high-level repository metadata."""
        # A simple placeholder calculation for LOC and file counts
        py_files = list(self.target_dir.glob("**/*.py"))
        js_files = list(self.target_dir.glob("**/*.js"))
        ts_files = list(self.target_dir.glob("**/*.ts"))
        total_files = len(py_files) + len(js_files) + len(ts_files)
        
        return {
            "name": self.target_dir.name,
            "primary_language": self.detect_languages()[0]["name"],
            "repo_type": "application",
            "loc": total_files * 100, # Mock estimation
            "file_count": total_files
        }
