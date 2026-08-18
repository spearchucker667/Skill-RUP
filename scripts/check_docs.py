#!/usr/bin/env python3
import os
import sys
from pathlib import Path

REQUIRED_FILES = [
    "README.md",
    "CONTRIBUTING.md",
    "SECURITY.md",
    "CODE_OF_CONDUCT.md",
    "SUPPORT.md",
    "CHANGELOG.md",
    "GOVERNANCE.md",
    "THIRD_PARTY_NOTICES.md",
    "docs/README.md",
    "docs/INSTALL.md",
    "docs/USER_GUIDE.md",
    "docs/ARCHITECTURE.md",
    "docs/ARTIFACT_CONTRACTS.md",
    "docs/PORTABILITY.md",
    "docs/SECURITY_MODEL.md",
    "docs/DEVELOPMENT.md",
    "docs/RELEASES.md",
    "docs/COMPATIBILITY.md",
    "docs/TROUBLESHOOTING.md",
    "docs/FAQ.md"
]

FORBIDDEN_STRINGS = [
    "/Users/",
    "super_user",
    "TODO",
    "TBD",
    "FIXME",
    "placeholder"
]

def main():
    root = Path(__file__).parent.parent.resolve()
    errors = []

    # 1. Check required files
    for req in REQUIRED_FILES:
        if not (root / req).exists():
            errors.append(f"Missing required file: {req}")

    # 2. Check for forbidden strings in markdown and Python files
    scan_extensions = ["*.md", "*.py"]
    scan_dirs = ["", "scripts", "runtime", "tests"]  # root and specific directories
    
    for pattern in scan_extensions:
        for file_path in root.rglob(pattern):
            # Skip ignored directories and the check script itself
            if any(ignored in file_path.parts for ignored in [".reference", "node_modules", "development", ".work orders", ".git", ".venv", "__pycache__"]):
                continue
            if file_path.name.startswith("SKILL_RUP_GITHUB_DOCS"):
                continue
            if file_path.name == "check_docs.py":
                continue
            # Skip known false positives (legitimate use of the word "placeholder")
            if file_path.name in ["planning.py", "execution.py", "test_execution.py", "audit_sources.py", "check_docs.py"]:
                continue
            
            try:
                content = file_path.read_text(encoding="utf-8")
                for fb in FORBIDDEN_STRINGS:
                    if fb in content:
                        errors.append(f"Forbidden string '{fb}' found in {file_path.relative_to(root)}")
            except Exception as e:
                errors.append(f"Could not read {file_path.relative_to(root)}: {e}")

    if errors:
        print("Documentation validation failed:")
        for err in set(errors):
            print(f"  - {err}")
        sys.exit(1)
    
    print("Documentation validation passed.")
    sys.exit(0)

if __name__ == "__main__":
    main()
