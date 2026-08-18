"""
Repository inventory manager for RUP deterministic runtime.
Performs accurate file inventory, language detection, LOC counting, git history analysis, and license extraction.
"""
import os
import re
import warnings
from pathlib import Path
from typing import Dict, Any, List, Optional
from collections import defaultdict
from .command_runner import run_command

EXT_TO_LANG = {
    '.py': 'python',
    '.js': 'javascript',
    '.mjs': 'javascript',
    '.cjs': 'javascript',
    '.ts': 'typescript',
    '.mts': 'typescript',
    '.cts': 'typescript',
    '.tsx': 'typescript',
    '.jsx': 'javascript',
    '.go': 'go',
    '.rs': 'rust',
    '.java': 'java',
    '.cpp': 'cpp',
    '.c': 'c',
    '.h': 'c',
    '.hpp': 'cpp',
    '.cs': 'csharp',
    '.rb': 'ruby',
    '.php': 'php',
    '.sh': 'shell',
    '.bash': 'shell',
    '.zsh': 'shell',
    '.html': 'html',
    '.css': 'css',
    '.yaml': 'yaml',
    '.yml': 'yaml',
    '.json': 'json',
    '.md': 'markdown'
}

LOCKFILES = {
    'python': ['poetry.lock', 'Pipfile.lock', 'pdm.lock', 'uv.lock'],
    'javascript': ['package-lock.json', 'yarn.lock', 'pnpm-lock.yaml', 'bun.lockb'],
    'typescript': ['package-lock.json', 'yarn.lock', 'pnpm-lock.yaml', 'bun.lockb'],
    'go': ['go.sum'],
    'rust': ['Cargo.lock'],
    'ruby': ['Gemfile.lock'],
    'php': ['composer.lock'],
}

class InventoryManager:
    def __init__(self, target_dir: Path):
        self.target_dir = target_dir
        self._cached_inventory: Optional[Dict[str, Any]] = None

    def _walk_files(self):
        """Walks files ignoring standard ignore directories."""
        ignored = {'.git', '.venv', 'venv', 'env', 'node_modules', '__pycache__', 'dist', 'build', '.rup', '.reference', '.pytest_cache'}
        for root, dirs, files in os.walk(self.target_dir):
            dirs[:] = [d for d in dirs if d not in ignored]
            for file in sorted(files):
                yield Path(root) / file

    def analyze_inventory(self) -> Dict[str, Any]:
        """Perform a single comprehensive pass over the repository."""
        if self._cached_inventory is not None:
            return self._cached_inventory

        counts = defaultdict(int)
        file_counts = defaultdict(int)
        total_loc = 0
        total_files = 0

        for file_path in self._walk_files():
            total_files += 1
            ext = file_path.suffix.lower()
            lang = EXT_TO_LANG.get(ext)

            if file_path.stat().st_size > 2 * 1024 * 1024:
                continue  # Skip large data/binary files from LOC

            try:
                with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                    lines = sum(1 for _ in f)
                total_loc += lines
                if lang:
                    counts[lang] += lines
                    file_counts[lang] += 1
            except Exception as e:
                warnings.warn(f"Inventory line-count failed for {file_path}: {e}", RuntimeWarning, stacklevel=2)

        # Language breakdown
        languages = []
        code_loc = sum(counts.values())
        if code_loc > 0:
            for lang, lines in counts.items():
                pct = round((lines / code_loc) * 100, 2)
                languages.append({
                    "name": lang,
                    "percentage": pct,
                    "lockfile_present": self._check_lockfile(lang)
                })
            languages.sort(key=lambda x: x['percentage'], reverse=True)
        else:
            languages.append({"name": "unknown", "percentage": 100.0, "lockfile_present": False})

        # Git metadata
        git_meta = self._get_git_metadata()

        # License detection
        license_name = self._detect_license()

        # Repo type classification
        repo_type = self._classify_repo_type(languages)

        primary_lang = languages[0]["name"] if languages else "unknown"

        self._cached_inventory = {
            "name": self.target_dir.name,
            "primary_language": primary_lang,
            "repo_type": repo_type,
            "loc": total_loc,
            "file_count": total_files,
            "languages": languages,
            "contributors": git_meta.get("contributors", 1),
            "last_commit": git_meta.get("last_commit", ""),
            "open_issues": 0,
            "license": license_name
        }
        return self._cached_inventory

    def _check_lockfile(self, lang: str) -> bool:
        """Strict lockfile presence check."""
        for f in LOCKFILES.get(lang, []):
            if (self.target_dir / f).exists():
                return True
        return False

    def _get_git_metadata(self) -> Dict[str, Any]:
        """Query git history if repository is version-controlled.

        Degrades gracefully for fixture directories, non-git targets, or any
        git command failure. Inventory generation must never abort the run.
        """
        meta = {"contributors": 1, "last_commit": "N/A"}

        git_dir = self.target_dir / ".git"
        if not git_dir.exists():
            return meta

        try:
            # Last commit
            rc, stdout, _ = run_command(["git", "log", "-1", "--format=%cd (%h)", "--date=short"], cwd=self.target_dir)
            if rc == 0 and stdout.strip():
                meta["last_commit"] = stdout.strip()

            # Contributor count
            rc, stdout, _ = run_command(["git", "shortlog", "-sn", "HEAD"], cwd=self.target_dir)
            if rc == 0 and stdout.strip():
                contributors = len(stdout.strip().splitlines())
                meta["contributors"] = max(1, contributors)
        except Exception as e:
            # Keep inventory resilient for fixtures and non-repo targets.
            warnings.warn(f"Git metadata query failed: {e}", RuntimeWarning, stacklevel=2)
            return meta

        return meta

    def _detect_license(self) -> str:
        """Detect open source license from repository files."""
        candidates = ["LICENSE", "LICENSE.md", "LICENSE.txt", "COPYING"]
        for c in candidates:
            p = self.target_dir / c
            if p.exists():
                try:
                    content = p.read_text(encoding="utf-8", errors="ignore")
                    if "Apache License" in content and "2.0" in content:
                        return "Apache-2.0"
                    if "MIT License" in content or "Permission is hereby granted, free of charge" in content:
                        return "MIT"
                    if "CC0 1.0" in content or "Creative Commons Zero" in content:
                        return "CC0-1.0"
                    if "GNU GENERAL PUBLIC LICENSE" in content:
                        if "Version 3" in content:
                            return "GPL-3.0"
                        return "GPL"
                    if "BSD 3-Clause" in content:
                        return "BSD-3-Clause"
                    if "BSD 2-Clause" in content:
                        return "BSD-2-Clause"
                    return "Custom / Identified"
                except Exception as e:
                    warnings.warn(f"License read failed for {p}: {e}", RuntimeWarning, stacklevel=2)
        return "UNKNOWN"

    def _classify_repo_type(self, languages: List[Dict[str, Any]]) -> str:
        """Classify repository type: monorepo, library, cli, service, application."""
        # Monorepo
        if (self.target_dir / "pnpm-workspace.yaml").exists() or (self.target_dir / "lerna.json").exists() or (self.target_dir / "go.work").exists():
            return "monorepo"
        if list(self.target_dir.glob("packages/*")):
            return "monorepo"

        # CLI
        if (self.target_dir / "bin").is_dir() or (self.target_dir / "cli.py").exists() or (self.target_dir / "runtime" / "cli.py").exists():
            return "cli"

        # Library
        if (self.target_dir / "setup.py").exists():
            return "library"
        pkg_json = self.target_dir / "package.json"
        if pkg_json.exists():
            try:
                import json
                data = json.loads(pkg_json.read_text(encoding="utf-8", errors="ignore"))
                if "main" in data or "module" in data or "types" in data:
                    if not (self.target_dir / "src" / "index.html").exists():
                        return "library"
            except Exception as e:
                warnings.warn(f"package.json classification failed: {e}", RuntimeWarning, stacklevel=2)

        if (self.target_dir / "Cargo.toml").exists():
            if (self.target_dir / "src" / "lib.rs").exists() and not (self.target_dir / "src" / "main.rs").exists():
                return "library"

        return "application"

    def detect_languages(self) -> List[Dict[str, Any]]:
        return self.analyze_inventory()["languages"]

    def get_repo_metadata(self) -> Dict[str, Any]:
        inv = self.analyze_inventory()
        return {
            "name": inv["name"],
            "primary_language": inv["primary_language"],
            "repo_type": inv["repo_type"],
            "loc": inv["loc"],
            "file_count": inv["file_count"],
            "contributors": inv["contributors"],
            "last_commit": inv["last_commit"],
            "open_issues": inv["open_issues"],
            "license": inv["license"]
        }

