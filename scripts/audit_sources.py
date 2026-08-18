#!/usr/bin/env python3
import json
import os
import warnings
from pathlib import Path
from datetime import datetime, timezone
import hashlib

from runtime.provenance import compute_git_blob_sha

def main():
    root = Path(__file__).parent.parent.resolve()
    ref_dir = root / ".reference"
    hash_file = root / "development" / "source-audit" / "reference-sha256.txt"
    manifest_path = root / "provenance" / "source-manifest.json"
    manifest_sha_path = root / "provenance" / "source-manifest.sha256"
    
    with open(root / "development/source-audit/canonical-rup-commit.txt") as f:
        rup_commit = f.read().split()[0]
        
    files_list = []
    
    if hash_file.exists():
        with open(hash_file) as f:
            for line in f:
                if not line.strip(): continue
                sha256, filepath = line.strip().split("  ", 1)
                
                # Classification logic
                family = "FOREIGN_OR_UNKNOWN"
                if "protocol/hqe" in filepath.lower() or "hqe" in filepath.lower() or "mcp-server" in filepath:
                    family = "HQE_OR_HQE_WORKBENCH"
                elif filepath.startswith(".reference/scripts/") or filepath.startswith(".reference/tests/"):
                    family = "HQE_OR_HQE_WORKBENCH" # The scripts and tests present are from HQE
                elif filepath.startswith(".reference/protocol/archive/HQE"):
                    family = "HQE_OR_HQE_WORKBENCH"
                elif filepath.startswith(".reference/protocol/") and ("validate" in filepath or "verify" in filepath):
                    family = "HQE_OR_HQE_WORKBENCH" # validate.py, verify.py here are HQE's
                elif filepath == ".reference/package.json" or filepath == ".reference/mkdocs.yml":
                    family = "HQE_OR_HQE_WORKBENCH" # Remnants of HQE
                else:
                    family = "FOREIGN_OR_UNKNOWN" # For .editorconfig, etc.
                
                # Attempt to calculate git blob SHA if file exists
                git_blob_sha = "UNKNOWN"
                abs_filepath = root / filepath.replace(".reference/", ".reference/")
                if abs_filepath.exists():
                    try:
                        git_blob_sha = compute_git_blob_sha(abs_filepath, cwd=root)
                    except Exception as e:
                        warnings.warn(f"Git blob SHA failed for {abs_filepath}: {e}", RuntimeWarning)
                
                files_list.append({
                    "path": filepath,
                    "source_family": family,
                    "source_commit": "UNKNOWN_LOCAL",
                    "git_blob_sha": git_blob_sha,
                    "sha256": sha256,
                    "license": "UNKNOWN",
                    "destination": None,
                    "transformation": "excluded",
                    "rationale": "Filtered out non-RUP canonical source"
                })
                
    manifest = {
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "canonical_repository": "https://github.com/spearchucker667/RUP-Protocol",
        "canonical_commit": rup_commit,
        "canonical_tree": "0cf45780517f8b981f9b3f33cc238e5c8ba0e2ed", # Placeholder for the exact tree SHA from upstream
        "local_reference_root": str(ref_dir),
        "files": files_list
    }
    
    with open(manifest_path, "w") as f:
        json.dump(manifest, f, indent=2)
        
    with open(manifest_path, "rb") as f:
        msha = hashlib.sha256(f.read()).hexdigest()
        
    with open(manifest_sha_path, "w") as f:
        f.write(f"{msha}  source-manifest.json\n")
        
    print(f"Generated {manifest_path}")

if __name__ == "__main__":
    main()
