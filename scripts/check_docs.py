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

    # 2. Check for forbidden strings
    for md_file in root.rglob("*.md"):
        if any(ignored in md_file.parts for ignored in [".reference", "node_modules", "development", ".work orders"]):
            continue
        if md_file.name.startswith("SKILL_RUP_GITHUB_DOCS"):
            continue
            
        try:
            content = md_file.read_text(encoding="utf-8")
            for fb in FORBIDDEN_STRINGS:
                if fb in content:
                    errors.append(f"Forbidden string '{fb}' found in {md_file.relative_to(root)}")
        except Exception as e:
            errors.append(f"Could not read {md_file.relative_to(root)}: {e}")

    if errors:
        print("Documentation validation failed:")
        for err in set(errors):
            print(f"  - {err}")
        sys.exit(1)
    
    print("Documentation validation passed.")
    sys.exit(0)

if __name__ == "__main__":
    main()
