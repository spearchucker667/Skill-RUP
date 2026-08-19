"""Regression tests for scripts/validate_rup.py."""
from pathlib import Path

from scripts.validate_rup import _find_schema_path, load_derived_schema


def test_derived_schema_autodiscovered_when_schema_omitted():
    """RUP-VALID-001: omitting --schema must still resolve the derived schema."""
    schema_path = _find_schema_path(None)
    assert schema_path is not None
    derived = load_derived_schema(schema_path)
    assert derived is not None
    plan_props = derived.get("$defs", {}).get("PlanOutput", {}).get("properties", {})
    assert "constraints" in plan_props
