"""
Tests for runtime/capability_map.py.

Covers:
- Canonical capabilities are generated from protocol/rup-protocol.yaml.
- verify_capabilities performs real AST symbol verification.
- Verification levels honestly distinguish runtime smoke tests from semantic tests.
"""
import json
from pathlib import Path

import pytest
import yaml

from runtime.capability_map import (
    CANONICAL_CAPABILITIES,
    PROTOCOL_CAPABILITY_TRANSLATION,
    load_canonical_capabilities,
    verify_capabilities,
    _extract_symbols,
    _verify_implementation,
)
from runtime.source_authority import SOURCE_AUTHORITY


REPO_ROOT = Path(__file__).parent.parent.resolve()


def test_capabilities_generated_from_protocol():
    """H-09: capability IDs and titles must come from the canonical protocol YAML."""
    caps = load_canonical_capabilities(REPO_ROOT)
    ids = {c["id"] for c in caps}

    # Phase steps from protocol
    assert "rup.phase_1_discovery.1.1" in ids
    assert "rup.phase_1_discovery.1.7" in ids
    assert "rup.phase_2_planning.2.1" in ids
    assert "rup.phase_2_planning.2.4" in ids
    assert "rup.phase_4_verification.4.5" in ids  # was missing from hand-curated registry
    assert "rup.phase_4_verification.4.6" in ids

    # Execution dispatcher and cross-cutting capabilities
    assert "rup.phase_3_execution.workstreams" in ids
    assert "rup.guardrails.security" in ids
    assert "rup.state.lifecycle" in ids

    # All capabilities have runtime translation entries
    for cap in caps:
        assert cap["id"] in PROTOCOL_CAPABILITY_TRANSLATION, cap["id"]


def test_canonical_capabilities_include_documentation_verification():
    """The protocol-derived registry must include the Documentation Verification step."""
    caps = load_canonical_capabilities(REPO_ROOT)
    doc = next((c for c in caps if c["id"] == "rup.phase_4_verification.4.5"), None)
    assert doc is not None
    assert doc["name"] == "Documentation Verification"
    assert doc["category"] == "verification"


def test_extract_symbols_finds_top_level_definitions():
    """AST helper returns classes and functions defined in a Python file."""
    symbols = _extract_symbols(REPO_ROOT / "runtime" / "security.py")
    assert "enforce_path_jail" in symbols
    assert "check_prompt_injection" in symbols
    assert "LimitedAliasLoader" in symbols


def test_verify_implementation_detects_missing_symbol():
    """verify_implementation reports missing symbols, not just missing files."""
    result = _verify_implementation(
        REPO_ROOT,
        ["runtime.security"],
        ["enforce_path_jail", "nonexistent_symbol"],
    )
    assert result["files_exist"] is True
    assert result["symbols_verified"] is False
    assert "nonexistent_symbol" in result["missing_symbols"]


def test_verify_capabilities_detects_missing_file():
    """If a required implementation file is missing the capability is unmapped."""
    caps = load_canonical_capabilities(REPO_ROOT)
    # Temporarily point at a non-existent module in the translation.
    original = PROTOCOL_CAPABILITY_TRANSLATION["rup.state.lifecycle"]["modules"]
    PROTOCOL_CAPABILITY_TRANSLATION["rup.state.lifecycle"]["modules"] = ["runtime.nonexistent_module"]
    try:
        result = verify_capabilities(REPO_ROOT)
        state = next(c for c in result["capabilities"] if c["id"] == "rup.state.lifecycle")
        assert state["port_status"] == "unmapped"
        assert state["verification_level"] == "unverified"
        assert any("nonexistent_module.py" in d for d in state["missing_details"])
    finally:
        PROTOCOL_CAPABILITY_TRANSLATION["rup.state.lifecycle"]["modules"] = original


def test_verification_levels_are_honest():
    """H-10: forward smoke tests are labelled runtime_smoke_verified; only semantic tests are behaviorally_verified."""
    result = verify_capabilities(REPO_ROOT)
    by_id = {c["id"]: c for c in result["capabilities"]}

    # Security guardrails have semantic tests.
    security = by_id["rup.guardrails.security"]
    assert security["semantic_tests"]
    assert security["verification_level"] == "behaviorally_verified"

    # Everything else with forward tests is runtime-smoke verified.
    discovery = by_id["rup.phase_1_discovery.1.1"]
    assert discovery["runtime_smoke_tests"]
    assert discovery["verification_level"] == "runtime_smoke_verified"
    assert not discovery["semantic_tests"]


def test_verify_capabilities_counts_are_consistent():
    """Aggregated counts in verify_capabilities match the capability list."""
    result = verify_capabilities(REPO_ROOT)
    assert result["total"] == len(result["capabilities"])
    assert result["ported"] + result["unmapped"] == result["total"]
    assert all(c["port_status"] in ("ported", "unmapped") for c in result["capabilities"])


def test_lineage_json_is_schema_valid():
    """H-12: regenerated provenance/capability-lineage.json validates against its schema."""
    schema_path = REPO_ROOT / "schemas" / "capability-lineage.schema.json"
    lineage_path = REPO_ROOT / "provenance" / "capability-lineage.json"

    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    lineage = json.loads(lineage_path.read_text(encoding="utf-8"))

    from jsonschema import Draft202012Validator

    validator = Draft202012Validator(schema)
    errors = list(validator.iter_errors(lineage))
    assert not errors, [e.message for e in errors]


def test_canonical_source_matches_source_authority():
    """Lineage records cite the pinned upstream commit and version."""
    lineage_path = REPO_ROOT / "provenance" / "capability-lineage.json"
    lineage = json.loads(lineage_path.read_text(encoding="utf-8"))
    for record in lineage:
        src = record["canonical_source"]
        assert src["repository"] == SOURCE_AUTHORITY["canonical_repo"]
        assert src["version"] == SOURCE_AUTHORITY["canonical_version"]
        assert src["commit"] == SOURCE_AUTHORITY["canonical_commit"]
