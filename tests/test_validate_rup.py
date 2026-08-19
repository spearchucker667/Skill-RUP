"""Regression tests for scripts/validate_rup.py."""
import argparse
from pathlib import Path

from scripts.validate_rup import (
    _find_schema_path,
    cmd_validate_all,
    load_derived_schema,
)


def test_derived_schema_autodiscovered_when_schema_omitted():
    """RUP-VALID-001: omitting --schema must still resolve the derived schema."""
    schema_path = _find_schema_path(None)
    assert schema_path is not None
    derived = load_derived_schema(schema_path)
    assert derived is not None
    plan_state_props = derived.get("$defs", {}).get("PlanState", {}).get("properties", {})
    assert "constraints" in plan_state_props


def test_execution_state_validated_against_derived_schema(tmp_path: Path):
    """RUP-VALID-002: execution-state.json must use schemas/execution-state.schema.json.

    A file whose name contains ``execution`` but is a Skill-only sidecar must not
    be misrouted to the canonical ``ExecutionOutput`` contract.
    """
    invalid = {
        # Deliberately omit required "recommendations".
        "dispositions": {},
        "per_item_completion": {},
        "rollback_operations": [],
    }
    (tmp_path / "execution-state.json").write_text(
        __import__("json").dumps(invalid), encoding="utf-8"
    )

    args = argparse.Namespace(
        directory=str(tmp_path),
        schema=None,
        verbose=False,
        allow_empty=False,
    )
    rc = cmd_validate_all(args)
    assert rc == 1, "Expected validation to fail for invalid execution-state.json"
