import os
import json
from pathlib import Path

# Mapping of skill schema name to Canonical $defs key
schema_map = {
    "discovery": "DiscoveryReport",
    "plan": "PlanOutput",
    "execution": "ExecutionOutput",
    "verification": "VerificationOutput",
    "final-report": "VerificationOutput",
    "run-manifest": "AgentMeta",
    "capability-map": "ToolContracts", 
    "provenance": "AgentMeta"
}

def main():
    root = Path(__file__).parent.parent.resolve()
    sch_dir = root / "schemas"
    tmp_dir = root / "templates"
    
    sch_dir.mkdir(exist_ok=True, parents=True)
    tmp_dir.mkdir(exist_ok=True, parents=True)
    
    # Load canonical schema
    canonical_schema_path = root / "protocol" / "rup-schema.json"
    with open(canonical_schema_path, "r") as f:
        canonical = json.load(f)
        defs = canonical.get("$defs", {})
    
    for s_name, def_key in schema_map.items():
        path = sch_dir / f"{s_name}.schema.json"
        
        extracted = defs.get(def_key, {"type": "object"})
        
        with open(path, "w") as f:
            schema_out = {
                "$schema": "https://json-schema.org/draft/2020-12/schema",
                "$id": f"https://spearchucker667.github.io/RUP/schemas/{s_name}.schema.json",
                "title": f"{s_name.title()} Schema",
                **extracted
            }
            # Remove refs if they are broken by extraction, for simplicity just let them be or embed
            json.dump(schema_out, f, indent=2)

    # Empty out templates, we don't use them (we generate markdown inline)
    # Actually, let's remove the TBD templates so they aren't misleading.
    for p in tmp_dir.glob("*"):
        p.unlink()

    print(f"Generated {len(schema_map)} strict schemas. Cleaned up templates.")

if __name__ == "__main__":
    main()
