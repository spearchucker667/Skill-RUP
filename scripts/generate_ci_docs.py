#!/usr/bin/env python3
"""
generate_ci_docs.py - Non-destructive CI workflows and documentation validator.
Safely verifies that required CI workflows and documentation files exist.
"""
import argparse
import sys
from pathlib import Path

REQUIRED_CI = [
    "ci.yml", "validate-skill.yml", "security-scan.yml",
    "forward-tests.yml", "release-package.yml"
]

REQUIRED_DOCS = [
    "INSTALL.md", "USER_GUIDE.md", "PORTABILITY.md", 
    "CAPABILITY_MAPPING.md", "SECURITY_MODEL.md", "ARTIFACT_CONTRACTS.md",
    "DEVELOPMENT.md", "ARCHITECTURE.md", "RELEASES.md", "COMPATIBILITY.md",
    "TROUBLESHOOTING.md", "FAQ.md"
]

def main() -> int:
    parser = argparse.ArgumentParser(description="Check CI and Documentation files.")
    parser.add_argument("--check", action="store_true", default=True, help="Check file existence (default: True)")
    args = parser.parse_args()

    root = Path(__file__).parent.parent.resolve()
    ci_dir = root / ".github" / "workflows"
    docs_dir = root / "docs"

    missing_ci = [f for f in REQUIRED_CI if not (ci_dir / f).exists()]
    missing_docs = [f for f in REQUIRED_DOCS if not (docs_dir / f).exists()]

    if missing_ci or missing_docs:
        if missing_ci:
            print(f"Missing CI workflows: {missing_ci}", file=sys.stderr)
        if missing_docs:
            print(f"Missing documentation: {missing_docs}", file=sys.stderr)
        return 1

    print(f"All {len(REQUIRED_CI)} CI workflows and {len(REQUIRED_DOCS)} documentation files verified.")
    return 0

if __name__ == "__main__":
    sys.exit(main())
