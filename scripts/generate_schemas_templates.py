#!/usr/bin/env python3
import os
import json
from pathlib import Path

schemas = [
    "discovery", "plan", "execution", "verification", "final-report",
    "rollback", "handoff", "run-manifest", "session-state",
    "capability-map", "provenance"
]

templates = [
    "discovery-report.md", "plan.md", "execution-report.md",
    "verification-report.md", "final-report.md", "rollback-plan.md",
    "agent-handoff.md", "migration.md", "incident-playbook.md",
    "session-state.json"
]

def main():
    root = Path("/Users/super_user/Projects/Skill-RUP")
    sch_dir = root / "schemas"
    tmp_dir = root / "templates"
    
    sch_dir.mkdir(exist_ok=True, parents=True)
    tmp_dir.mkdir(exist_ok=True, parents=True)
    
    for s in schemas:
        path = sch_dir / f"{s}.schema.json"
        with open(path, "w") as f:
            json.dump({
                "$schema": "https://json-schema.org/draft/2020-12/schema",
                "$id": f"https://spearchucker667.github.io/RUP/schemas/{s}.schema.json",
                "title": f"{s.title()} Schema",
                "type": "object"
            }, f, indent=2)
            
    for t in templates:
        path = tmp_dir / t
        with open(path, "w") as f:
            if t.endswith(".json"):
                json.dump({"_comment": f"Template for {t}"}, f, indent=2)
            else:
                f.write(f"# {t.replace('.md', '').replace('-', ' ').title()}\n\nTemplate content TBD.\n")
                
    print(f"Generated {len(schemas)} schemas and {len(templates)} templates.")

if __name__ == "__main__":
    main()
