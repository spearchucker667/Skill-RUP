"""
inventory module for RUP deterministic runtime.
"""
from pathlib import Path
from typing import Dict, Any, List

import os
from collections import defaultdict

class InventoryManager:
    def __init__(self, target_dir: Path):
        self.target_dir = target_dir

    def _walk_files(self):
        """Walks files ignoring common ignored dirs."""
        ignored = {'.git', '.venv', 'node_modules', '__pycache__', 'dist', 'build'}
        for root, dirs, files in os.walk(self.target_dir):
            dirs[:] = [d for d in dirs if d not in ignored]
            for file in files:
                yield Path(root) / file

    def detect_languages(self) -> List[Dict[str, Any]]:
        """Detect languages by counting extensions."""
        ext_map = {
            '.py': 'python',
            '.js': 'javascript',
            '.ts': 'typescript',
            '.go': 'go',
            '.rs': 'rust',
            '.java': 'java',
            '.cpp': 'cpp',
            '.c': 'c',
            '.cs': 'csharp',
            '.rb': 'ruby'
        }
        
        counts = defaultdict(int)
        total_loc = 0
        
        for file in self._walk_files():
            ext = file.suffix.lower()
            lang = ext_map.get(ext)
            if lang:
                try:
                    with open(file, 'r', encoding='utf-8') as f:
                        lines = sum(1 for _ in f)
                        counts[lang] += lines
                        total_loc += lines
                except Exception:
                    pass
                    
        languages = []
        if total_loc > 0:
            for lang, lines in counts.items():
                languages.append({
                    "name": lang,
                    "percentage": round((lines / total_loc) * 100, 2),
                    "lockfile_present": self._check_lockfile(lang)
                })
            languages.sort(key=lambda x: x['percentage'], reverse=True)
        else:
            languages.append({"name": "unknown", "percentage": 100, "lockfile_present": False})
            
        return languages

    def _check_lockfile(self, lang: str) -> bool:
        locks = {
            'python': ['poetry.lock', 'Pipfile.lock', 'requirements.txt'],
            'javascript': ['package-lock.json', 'yarn.lock', 'pnpm-lock.yaml'],
            'typescript': ['package-lock.json', 'yarn.lock', 'pnpm-lock.yaml'],
            'go': ['go.sum'],
            'rust': ['Cargo.lock']
        }
        for f in locks.get(lang, []):
            if (self.target_dir / f).exists():
                return True
        return False
        
    def detect_tooling(self, languages: List[Dict[str, Any]]) -> Dict[str, str]:
        """Simple toolchain detector based on files."""
        tooling = {}
        # Python
        if (self.target_dir / "pytest.ini").exists() or (self.target_dir / "tests").is_dir():
            tooling["test_framework"] = "pytest"
        if (self.target_dir / ".ruff.toml").exists() or (self.target_dir / "ruff.toml").exists():
            tooling["linter"] = "ruff"
            
        # JS/TS
        if (self.target_dir / "jest.config.js").exists():
            tooling["test_framework"] = "jest"
        if (self.target_dir / ".eslintrc.js").exists() or (self.target_dir / ".eslintrc.json").exists():
            tooling["linter"] = "eslint"
            
        return tooling

    def get_repo_metadata(self) -> Dict[str, Any]:
        """Generate high-level repository metadata."""
        total_files = sum(1 for _ in self._walk_files())
        langs = self.detect_languages()
        
        total_loc = 0
        for file in self._walk_files():
            try:
                if file.is_file():
                    with open(file, 'r', encoding='utf-8') as f:
                        total_loc += sum(1 for _ in f)
            except Exception:
                pass
                
        # Determine repo type
        repo_type = "application"
        if (self.target_dir / "setup.py").exists() or (self.target_dir / "package.json").exists() and not (self.target_dir / "src" / "index.html").exists():
            repo_type = "library"
        if list(self.target_dir.glob("packages/*")):
            repo_type = "monorepo"

        return {
            "name": self.target_dir.name,
            "primary_language": langs[0]["name"] if langs else "unknown",
            "repo_type": repo_type,
            "loc": total_loc,
            "file_count": total_files
        }
