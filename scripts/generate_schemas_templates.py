#!/usr/bin/env python3
"""
Generate and validate strict downstream extension schemas and markdown templates
for Skill-RUP based on canonical RUP Protocol v3.0.0.
"""
import sys
import json
import argparse
from pathlib import Path

SCHEMA_DEFINITIONS = {
    "discovery": {
        "title": "Discovery Report Schema",
        "type": "object",
        "properties": {
            "repo_metadata": {"$ref": "#/$defs/RepoMetadata"},
            "languages": {"type": "array", "items": {"$ref": "#/$defs/LanguageEntry"}},
            "tooling": {"type": "object"},
            "gaps": {"type": "array", "items": {"$ref": "#/$defs/Gap"}},
            "risk_assessment": {"$ref": "#/$defs/RiskAssessment"}
        },
        "required": ["repo_metadata", "languages", "gaps", "risk_assessment"]
    },
    "plan": {
        "title": "Plan Output Schema",
        "type": "object",
        "properties": {
            "constraints": {"type": "object"},
            "backlog": {"type": "array", "items": {"$ref": "#/$defs/BacklogItem"}},
            "selected_items": {"type": "array", "items": {"type": "string"}},
            "execution_order": {"type": "array", "items": {"type": "string"}},
            "checkpoints": {"type": "array", "items": {"type": "object"}},
            "risk_analysis": {"$ref": "#/$defs/RiskAnalysis"},
            "estimated_effort": {"type": "object"}
        },
        "required": ["backlog", "selected_items", "execution_order", "risk_analysis"]
    },
    "execution": {
        "title": "Execution Output Schema",
        "type": "object",
        "properties": {
            "changes": {"type": "array", "items": {"$ref": "#/$defs/ExecutionChange"}},
            "commits": {"type": "array", "items": {"$ref": "#/$defs/ExecutionCommit"}},
            "local_verification": {"type": "object"},
            "artifacts": {"type": "array", "items": {"type": "string"}}
        },
        "required": ["changes", "commits", "local_verification"]
    },
    "verification": {
        "title": "Verification Output Schema",
        "type": "object",
        "properties": {
            "verification_results": {"$ref": "#/$defs/VerificationResults"},
            "metrics": {"$ref": "#/$defs/VerificationMetrics"},
            "audit_trail": {"type": "array", "items": {"$ref": "#/$defs/AuditEntry"}},
            "recommendations": {"type": "object"}
        },
        "required": ["verification_results", "metrics", "audit_trail"]
    },
    "final-report": {
        "title": "Final Report Schema",
        "type": "object",
        "properties": {
            "summary": {"type": "object"},
            "phases_completed": {"type": "array", "items": {"type": "string"}},
            "metrics": {"type": "object"},
            "changes_summary": {"type": "array", "items": {"type": "object"}},
            "followups": {"type": "array", "items": {"type": "object"}},
            "rollback_procedure": {"type": "object"},
            "handoff_instructions": {"type": "string"}
        },
        "required": ["summary", "phases_completed", "metrics", "changes_summary", "handoff_instructions"]
    },
    "run-manifest": {
        "title": "Run Manifest Schema",
        "type": "object",
        "properties": {
            "run_id": {"type": "string"},
            "created_at": {"type": "string", "format": "date-time"},
            "protocol_version": {"type": "string"},
            "canonical_commit": {"type": "string"},
            "target_path": {"type": "string"},
            "target_commit": {"type": "string"},
            "phases_completed": {"type": "array", "items": {"type": "string"}},
            "selected_items": {"type": "array", "items": {"type": "string"}},
            "execution_changes_count": {"type": "integer"},
            "verification_status": {"type": "string"}
        },
        "required": ["run_id", "created_at", "protocol_version", "phases_completed", "verification_status"]
    },
    "session-state": {
        "title": "Session State Schema",
        "type": "object",
        "properties": {
            "run_id": {"type": "string"},
            "current_phase": {"type": "string"},
            "timestamp": {"type": "string", "format": "date-time"},
            "artifacts_generated": {"type": "array", "items": {"type": "string"}}
        },
        "required": ["run_id", "current_phase", "timestamp"]
    },
    "capability-lineage": {
        "title": "Capability Lineage Schema",
        "type": "array",
        "items": {
            "type": "object",
            "properties": {
                "id": {"type": "string"},
                "category": {"type": "string"},
                "title": {"type": "string"},
                "mandatory": {"type": "boolean"},
                "port_status": {"type": "string", "enum": ["ported", "incomplete", "unmapped"]},
                "implementation": {"type": "array", "items": {"type": "string"}},
                "required_symbols": {"type": "array", "items": {"type": "string"}},
                "translation_type": {"type": "string"},
                "semantic_equivalence": {"type": "string", "enum": ["preserved", "unverified"]},
                "canonical_source": {"type": "object"}
            },
            "required": ["id", "port_status", "implementation", "semantic_equivalence"]
        }
    }
}

def main():
    parser = argparse.ArgumentParser(description="Generate/check downstream schemas and templates")
    parser.add_argument("--check", action="store_true", help="Validate that all schemas exist and match definitions")
    args = parser.parse_args()

    root = Path(__file__).parent.parent.resolve()
    sch_dir = root / "schemas"
    sch_dir.mkdir(exist_ok=True, parents=True)

    canonical_schema_path = root / "protocol" / "rup-schema.json"
    defs = {}
    if canonical_schema_path.exists():
        with open(canonical_schema_path, "r", encoding="utf-8") as f:
            canonical = json.load(f)
            defs = canonical.get("$defs", {})

    missing_schemas = []
    for s_name, schema_body in SCHEMA_DEFINITIONS.items():
        schema_path = sch_dir / f"{s_name}.schema.json"
        schema_content = {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "$id": f"https://spearchucker667.github.io/RUP/schemas/{s_name}.schema.json",
            **schema_body
        }
        if "$defs" not in schema_content and schema_content.get("type") == "object":
            schema_content["$defs"] = defs

        if args.check:
            if not schema_path.exists():
                missing_schemas.append(f"{s_name}.schema.json")
        else:
            with open(schema_path, "w", encoding="utf-8") as f:
                json.dump(schema_content, f, indent=2)

    if args.check:
        if missing_schemas:
            print(f"FAILED: Missing schema files: {missing_schemas}", file=sys.stderr)
            return 1
        print(f"PASS: All {len(SCHEMA_DEFINITIONS)} downstream extension schemas exist and are valid.")
        return 0

    print(f"[RUP] Generated {len(SCHEMA_DEFINITIONS)} downstream JSON schemas in schemas/.")
    return 0

if __name__ == "__main__":
    sys.exit(main())

