#!/usr/bin/env python3
"""
Packaging script for RUP-Skill.
Deterministically bundles the core capability into a single artifact,
explicitly ignoring the .reference/ cross-contamination folder.
"""

import zipfile
import hashlib
from pathlib import Path
import os

def hash_file(filepath: Path) -> str:
    sha256 = hashlib.sha256()
    with open(filepath, "rb") as f:
        for chunk in iter(lambda: f.read(4096), b""):
            sha256.update(chunk)
    return sha256.hexdigest()

def package_skill(root_dir: Path, out_path: Path):
    out_path.parent.mkdir(parents=True, exist_ok=True)
    
    # Exclude logic
    def should_include(path: Path) -> bool:
        rel_path = path.relative_to(root_dir).parts
        if not rel_path:
            return True
            
        # Ignore these specific top-level directories
        ignore_dirs = {".reference", ".git", ".github", "tests", "dist", "build", ".venv"}
        if rel_path[0] in ignore_dirs:
            return False
            
        # Ignore pycache
        if "__pycache__" in rel_path:
            return False
            
        return True

    print(f"Packaging skill into {out_path}...")
    manifest = {}
    
    with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for root, dirs, files in os.walk(root_dir):
            root_path = Path(root)
            
            # Prune dirs in place for os.walk
            dirs[:] = [d for d in dirs if should_include(root_path / d)]
            
            for f in files:
                file_path = root_path / f
                if not should_include(file_path):
                    continue
                    
                arcname = file_path.relative_to(root_dir)
                if arcname.name == out_path.name:
                    continue # Don't pack the zip itself
                    
                zf.write(file_path, arcname)
                manifest[str(arcname)] = hash_file(file_path)

    # Write manifest
    manifest_path = root_dir / "dist" / "manifest.json"
    import json
    with open(manifest_path, "w") as f:
        json.dump(manifest, f, indent=2)
        
    print(f"Successfully packaged {len(manifest)} files.")
    print(f"Archive SHA-256: {hash_file(out_path)}")

if __name__ == "__main__":
    root = Path(__file__).parent.parent
    dist_dir = root / "dist"
    package_skill(root, dist_dir / "rup-skill-v3.0.0.zip")
