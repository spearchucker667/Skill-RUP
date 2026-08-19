#!/usr/bin/env python3
"""
Generate and validate strict downstream extension schemas and markdown templates
for Skill-RUP based on canonical RUP Protocol v3.0.0.
"""
import sys
import json
import difflib
import argparse
import copy
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
            "backlog": {"type": "array", "items": {"$ref": "#/$defs/BacklogItem"}},
            "selected_items": {"type": "array", "items": {"type": "string"}},
            "execution_order": {"type": "array", "items": {"type": "string"}},
            "checkpoints": {"type": "array", "items": {"type": "object"}},
            "risk_analysis": {"$ref": "#/$defs/RiskAnalysis"},
            "estimated_effort": {"type": "object"}
        },
        "required": ["backlog", "selected_items", "execution_order", "risk_analysis"]
    },
    "plan-state": {
        "title": "Plan State Schema",
        "type": "object",
        "properties": {
            "constraints": {
                "type": "object",
                "properties": {
                    "time_budget_minutes": {"type": "integer", "minimum": 1},
                    "max_files": {"type": "integer", "minimum": 1},
                    "risk_tolerance": {"type": "string", "enum": ["low", "medium", "high"]}
                },
                "required": ["time_budget_minutes", "max_files", "risk_tolerance"]
            },
            "selected_for_escalation": {"type": "array", "items": {"type": "string"}},
            "requires_explicit_override": {"type": "boolean"}
        },
        "required": ["constraints", "selected_for_escalation", "requires_explicit_override"]
    },
    "execution": {
        "title": "Execution Output Schema",
        "type": "object",
        "properties": {
            "changes": {"type": "array", "items": {"$ref": "#/$defs/FileChange"}},
            "commits": {"type": "array", "items": {"$ref": "#/$defs/Commit"}},
            "local_verification": {"$ref": "#/$defs/LocalVerification"},
            "artifacts": {"type": "array", "items": {"$ref": "#/$defs/Artifact"}}
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
    "execution-state": {
        "title": "Execution State Schema",
        "type": "object",
        "properties": {
            "recommendations": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "backlog_item_id": {"type": "string"},
                        "subtype": {"type": "string"},
                        "disposition": {
                            "type": "string",
                            "enum": ["AGENT_ONLY", "PARTIAL", "NOT_PORTED", "COMPLETE"]
                        },
                        "rationale": {"type": "string"}
                    },
                    "required": ["backlog_item_id", "subtype", "disposition", "rationale"]
                }
            },
            "dispositions": {"type": "object", "additionalProperties": {"type": "string"}},
            "per_item_completion": {"type": "object", "additionalProperties": {"type": "string"}},
            "rollback_operations": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "op": {"type": "string"},
                        "argv": {"type": "array", "items": {"type": "string"}}
                    },
                    "required": ["op", "argv"]
                }
            }
        },
        "required": ["recommendations", "dispositions", "per_item_completion", "rollback_operations"]
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
                "verification_level": {"type": "string", "enum": ["unverified", "present", "structurally_verified", "runtime_smoke_verified", "behaviorally_verified", "canonical_parity_verified"]},
                "implementation": {"type": "array", "items": {"type": "string"}},
                "required_symbols": {"type": "array", "items": {"type": "string"}},
                "runtime_smoke_tests": {"type": "array", "items": {"type": "string"}},
                "semantic_tests": {"type": "array", "items": {"type": "string"}},
                "translation_type": {"type": "string"},
                "canonical_source": {"type": "object"}
            },
            "required": ["id", "port_status", "verification_level", "implementation", "required_symbols"]
        }
    }
}

# Skill-only definitions that extend the canonical schema without modifying it.
PLAN_STATE_DEF = {
    "title": "Plan State",
    "description": "Skill-RUP planning sidecar: constraints, escalations, and override flags that extend but do not alter the canonical PlanOutput contract.",
    "type": "object",
    "required": ["constraints", "selected_for_escalation", "requires_explicit_override"],
    "properties": {
        "constraints": {
            "type": "object",
            "required": ["time_budget_minutes", "max_files", "risk_tolerance"],
            "properties": {
                "time_budget_minutes": {"type": "integer", "minimum": 1},
                "max_files": {"type": "integer", "minimum": 1},
                "risk_tolerance": {"type": "string", "enum": ["low", "medium", "high"]}
            }
        },
        "selected_for_escalation": {"type": "array", "items": {"type": "string"}},
        "requires_explicit_override": {"type": "boolean"}
    },
    "additionalProperties": False
}


def _build_derived_schema(canonical: dict) -> dict:
    """Create the Skill-RUP derived umbrella schema from the canonical schema.

    The derived schema keeps the canonical $defs intact and adds Skill-only
    extensions (``PlanState`` and per-result tool metadata) so the canonical
    file can remain a byte-for-byte upstream copy.
    """
    derived = copy.deepcopy(canonical)
    derived["$id"] = "https://spearchucker667.github.io/RUP/schemas/rup-schema-derived.schema.json"
    derived["title"] = "RUP Protocol Schema — Skill-RUP Derived Runtime Contract"
    derived["description"] = (
        "Skill-RUP runtime artifact contract. Extends the canonical upstream "
        "schema with sidecars and runtime-only metadata while keeping canonical "
        "output definitions compatible with protocol/rup-schema.json."
    )
    derived["$defs"]["PlanState"] = PLAN_STATE_DEF
    vr = derived["$defs"].get("VerificationResult", {})
    if "properties" in vr:
        vr["properties"]["tool"] = {"type": ["string", "null"]}
    return derived


def _atomic_write(path: Path, content: str) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(content, encoding="utf-8")
    tmp.replace(path)


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

    mismatches = []
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

        expected = json.dumps(schema_content, indent=2, sort_keys=False) + "\n"
        if args.check:
            if not schema_path.exists():
                missing_schemas.append(f"{s_name}.schema.json")
                continue
            actual = schema_path.read_text(encoding="utf-8")
            if actual != expected:
                diff = "".join(
                    difflib.unified_diff(
                        actual.splitlines(keepends=True),
                        expected.splitlines(keepends=True),
                        fromfile=str(schema_path),
                        tofile=f"{schema_path} (generated)",
                    )
                )
                mismatches.append(f"Schema mismatch for {s_name}:\n{diff}")
        else:
            _atomic_write(schema_path, expected)

    # Generate/check the Skill-RUP derived umbrella schema.
    derived_schema_path = sch_dir / "rup-schema-derived.schema.json"
    if canonical_schema_path.exists():
        with open(canonical_schema_path, "r", encoding="utf-8") as f:
            canonical = json.load(f)
        derived_expected = _build_derived_schema(canonical)
        derived_text = json.dumps(derived_expected, indent=2, sort_keys=False) + "\n"
        if args.check:
            if not derived_schema_path.exists():
                missing_schemas.append("rup-schema-derived.schema.json")
            else:
                actual = derived_schema_path.read_text(encoding="utf-8")
                if actual != derived_text:
                    diff = "".join(
                        difflib.unified_diff(
                            actual.splitlines(keepends=True),
                            derived_text.splitlines(keepends=True),
                            fromfile=str(derived_schema_path),
                            tofile=f"{derived_schema_path} (generated)",
                        )
                    )
                    mismatches.append(f"Schema mismatch for rup-schema-derived:\n{diff}")
        else:
            _atomic_write(derived_schema_path, derived_text)

    if args.check:
        if missing_schemas:
            print(f"FAILED: Missing schema files: {missing_schemas}", file=sys.stderr)
            return 1
        if mismatches:
            for mismatch in mismatches:
                print(mismatch, file=sys.stderr)
            return 1
        print(f"PASS: All {len(SCHEMA_DEFINITIONS)} downstream extension schemas exist and match definitions.")
        return 0

    print(f"[RUP] Generated {len(SCHEMA_DEFINITIONS)} downstream JSON schemas in schemas/.")
    return 0

if __name__ == "__main__":
    sys.exit(main())

