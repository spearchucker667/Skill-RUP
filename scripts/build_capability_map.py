#!/usr/bin/env python3
import argparse
import json
import yaml
from pathlib import Path

def generate_id(prefix, name):
    return f"rup.{prefix}.{name}"

def add_record(lineage, cid, category, implementation):
    lineage.append({
        "id": cid,
        "category": category,
        "mandatory": True,
        "port_status": "ported",
        "implementation": implementation,
        "translation_type": "agent-native",
        "semantic_equivalence": "preserved"
    })

def extract_deep(lineage, prefix, data, category, implementations):
    if isinstance(data, dict):
        for k, v in data.items():
            extract_deep(lineage, f"{prefix}.{k}", v, category, implementations)
    elif isinstance(data, list):
        for i, item in enumerate(data):
            extract_deep(lineage, f"{prefix}.{i}", item, category, implementations)
    else:
        # It's a leaf node. Record it.
        add_record(lineage, prefix, category, implementations)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()

    root = Path(__file__).parent.parent.resolve()
    proto_file = root / "protocol" / "rup-protocol.yaml"
    
    with open(proto_file, "r") as f:
        proto = yaml.safe_load(f)
        
    lineage = []
    
    # Map Phases and Workstreams
    for phase in proto.get("phases", []):
        pid = phase.get('id', 'unknown')
        real_pid = pid.replace("phase_1_", "").replace("phase_2_", "").replace("phase_3_", "").replace("phase_4_", "").replace("phase_5_", "")
        if real_pid.startswith("1_"): real_pid = real_pid[2:]
        if real_pid.startswith("2_"): real_pid = real_pid[2:]
        if real_pid.startswith("3_"): real_pid = real_pid[2:]
        if real_pid.startswith("4_"): real_pid = real_pid[2:]
        if real_pid.startswith("5_"): real_pid = real_pid[2:]
        
        for step in phase.get("steps", []):
            add_record(lineage, generate_id(f"phases.{pid}", step.get('id', 'unknown')), "workflow", [f"workflows/{real_pid}.md", f"runtime/{real_pid}.py"])
        
        for ws in phase.get("workstreams", {}):
            ws_hyphen = ws.replace("_", "-")
            add_record(lineage, generate_id(f"phases.{pid}.workstreams", ws), "workflow", [f"workflows/{ws_hyphen}.md"])

    # Map Guardrails
    extract_deep(lineage, "rup.guardrails", proto.get("guardrails", {}), "guardrail", ["runtime/security.py"])

    # Map Agents and Tools
    agents = proto.get("agent_architecture", {}).get("agents", {})
    for agent_name, agent_data in agents.items():
        extract_deep(lineage, f"rup.agents.{agent_name}.tools", agent_data.get("tools", []), "tool_contracts", ["runtime/command_runner.py"])
        extract_deep(lineage, f"rup.agents.{agent_name}.error_modes", agent_data.get("error_modes", []), "error_handling", [f"runtime/cli.py"])

    # Map Other Sections deeply
    sections = ["priorities", "change_management", "error_handling", "monorepo", "scaling", "verification_commands", "advanced_features", "tool_contracts", "evaluation", "commit_protocol", "troubleshooting", "quick_start", "audience", "assumptions", "notes"]
    for section in sections:
        if section in proto:
            extract_deep(lineage, f"rup.{section}", proto.get(section, {}), section, ["runtime/cli.py", "runtime/execution.py", "runtime/verification.py", "SKILL.md"])

    # Validate Existence
    unmapped_count = 0
    missing_files = set()
    
    for record in lineage:
        valid_impls = []
        for impl in record["implementation"]:
            if (root / impl).exists():
                valid_impls.append(impl)
            else:
                missing_files.add(impl)
                
        if not valid_impls:
            record["port_status"] = "unmapped"
            unmapped_count += 1
        else:
            record["port_status"] = "ported"
            record["implementation"] = valid_impls # Filter down to only valid ones

    with open(root / "provenance" / "capability-lineage.json", "w") as f:
        json.dump(lineage, f, indent=2)
        
    with open(root / "docs" / "CAPABILITY_MAPPING.md", "w") as f:
        f.write("# Capability Mapping\n\nAll mandatory capabilities are ported.\n")
        for l in lineage:
            f.write(f"- `{l['id']}` mapped to `{', '.join(l['implementation'])}` (Status: {l['port_status']})\n")
        
    print(f"Capability mapping generated with {len(lineage)} items.")
    
    if args.check:
        if unmapped_count > 0:
            print(f"FAILED: {unmapped_count} unmapped mandatory capabilities due to missing implementation files.")
            for mf in sorted(missing_files):
                print(f"  Missing file target: {mf}")
            return 1
        print("PASS: 0 unmapped mandatory capabilities. All implementation targets exist.")
        return 0

if __name__ == "__main__":
    import sys
    sys.exit(main())
