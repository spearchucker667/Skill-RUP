#!/usr/bin/env python3
import os
from pathlib import Path

workflows = [
    "discovery", "planning", "execution", "verification", "reporting", 
    "rollback", "handoff", "quick-run", "hotfix", "monorepo", 
    "security-remediation", "ci-cd-upgrade", "documentation-upgrade", 
    "test-upgrade", "governance-upgrade", "container-iac", "advanced-quality"
]

template = """# {title} Workflow

## Purpose
TBD

## Preconditions
TBD

## Inputs
TBD

## Source Protocol Sections
- Provenance trace required here.

## Allowed Mutations
TBD

## Prohibited Mutations
TBD

## Steps
1. TBD

## Artifacts
TBD

## Validation
TBD

## Failure Behavior
TBD

## Handoff State
TBD
"""

def main():
    root = Path("/Users/super_user/Projects/Skill-RUP")
    wf_dir = root / "workflows"
    wf_dir.mkdir(exist_ok=True, parents=True)
    
    for wf in workflows:
        path = wf_dir / f"{wf}.md"
        title = wf.replace("-", " ").title()
        with open(path, "w") as f:
            f.write(template.format(title=title))
            
    print(f"Generated {len(workflows)} workflow files in {wf_dir}")

if __name__ == "__main__":
    main()
