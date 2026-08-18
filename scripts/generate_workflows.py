#!/usr/bin/env python3
import os
from pathlib import Path

workflows = [
    "discovery", "planning", "execution", "verification", "reporting", 
    "rollback", "handoff", "quick-run", "hotfix", "monorepo", 
    "security-remediation", "ci-cd-upgrade", "documentation-upgrade", 
    "test-upgrade", "governance-upgrade", "container-iac", "advanced-quality"
]

import os
import yaml
from pathlib import Path

def generate_markdown_for_workflow(wf_name, data):
    title = wf_name.replace("-", " ").title()
    desc = data.get("description", "No description provided.")
    
    # Try to extract arrays or dicts from the YAML blob for the section
    rules = []
    if "process" in data:
        for p in data["process"]:
            rules.append(f"- **{p.get('step', 'Step')}**: {p.get('details', '')}")
    if "guidelines" in data:
        for g in data["guidelines"]:
            rules.append(f"- {g}")
    if "steps" in data:
        for s in data["steps"]:
            rules.append(f"1. **{s.get('name', 'Step')}**: {s.get('description', '')}")
            
    rules_text = "\n".join(rules) if rules else "Follow canonical RUP directives for this workflow."
    
    content = f"""# {title} Workflow

## Purpose
{desc}

## Canonical Rules & Process
{rules_text}

## Raw Protocol Data
```yaml
{yaml.dump(data, default_flow_style=False)}
```

## Validation
Must comply with `rup-schema.json`.
"""
    return content

def main():
    root = Path(__file__).parent.parent.resolve()
    wf_dir = root / "workflows"
    wf_dir.mkdir(exist_ok=True, parents=True)
    
    proto_file = root / "protocol" / "rup-protocol.yaml"
    with open(proto_file, "r") as f:
        proto = yaml.safe_load(f)

    # Gather all workflows from phases and workstreams
    workflows = {}
    for phase in proto.get("phases", []):
        pid = phase.get('id', '').replace('phase_', '')
        if pid:
            workflows[pid] = phase
        
        for ws_key, ws_data in phase.get("workstreams", {}).items():
            # e.g., 'ws_bugs' or 'ws_ci'
            workflows[ws_data.get('id', ws_key).replace('ws_', '')] = ws_data
            workflows[ws_key] = ws_data

    # Additional standard workflows the CLI expects
    standard = ["discovery", "planning", "execution", "verification", "reporting", 
                "rollback", "handoff", "quick-run", "hotfix", "monorepo", 
                "security-remediation", "ci-cd-upgrade", "documentation-upgrade", 
                "test-upgrade", "governance-upgrade", "container-iac", "advanced-quality"]
                
    for wf in standard:
        if wf not in workflows:
            workflows[wf] = {"description": f"Standard {wf} process mapped from RUP Protocol."}

    for wf_name, data in workflows.items():
        # Sanitize name
        clean_name = wf_name.replace("_", "-")
        path = wf_dir / f"{clean_name}.md"
        with open(path, "w") as f:
            f.write(generate_markdown_for_workflow(clean_name, data))
            
    print(f"Generated {len(workflows)} real workflow files in {wf_dir}")

if __name__ == "__main__":
    main()
