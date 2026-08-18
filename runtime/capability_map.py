"""
Capability mapping and registry verification for RUP deterministic runtime.

The canonical capability inventory is generated from protocol/rup-protocol.yaml
and merged with a controlled runtime translation table that records which
Python modules, symbols, and tests implement each capability.
"""
import ast
import warnings
from pathlib import Path
from typing import Dict, Any, List, Optional

from .security import safe_load_yaml

# Maps canonical protocol capability IDs to runtime implementation details.
# This is the only hand-curated layer; the capability list itself is parsed
# from protocol/rup-protocol.yaml.
PROTOCOL_CAPABILITY_TRANSLATION: Dict[str, Dict[str, Any]] = {
    "rup.phase_1_discovery.1.1": {
        "modules": ["runtime.inventory", "runtime.discovery"],
        "symbols": ["InventoryManager", "DiscoveryPhase"],
        "runtime_smoke_tests": ["tests/forward/test_discovery.py::test_discovery_execution"],
    },
    "rup.phase_1_discovery.1.2": {
        "modules": ["runtime.tool_detection", "runtime.discovery"],
        "symbols": ["ToolDetector", "DiscoveryPhase"],
        "runtime_smoke_tests": ["tests/forward/test_discovery.py::test_discovery_execution"],
    },
    "rup.phase_1_discovery.1.3": {
        "modules": ["runtime.discovery"],
        "symbols": ["DiscoveryPhase"],
        "runtime_smoke_tests": ["tests/forward/test_discovery.py::test_discovery_execution"],
    },
    "rup.phase_1_discovery.1.4": {
        "modules": ["runtime.discovery", "runtime.redaction"],
        "symbols": ["DiscoveryPhase", "scan_secrets"],
        "runtime_smoke_tests": ["tests/forward/test_discovery.py::test_discovery_execution"],
    },
    "rup.phase_1_discovery.1.5": {
        "modules": ["runtime.discovery"],
        "symbols": ["DiscoveryPhase"],
        "runtime_smoke_tests": ["tests/forward/test_discovery.py::test_discovery_execution"],
    },
    "rup.phase_1_discovery.1.6": {
        "modules": ["runtime.discovery"],
        "symbols": ["DiscoveryPhase"],
        "runtime_smoke_tests": ["tests/forward/test_discovery.py::test_discovery_execution"],
    },
    "rup.phase_1_discovery.1.7": {
        "modules": ["runtime.discovery"],
        "symbols": ["DiscoveryPhase"],
        "runtime_smoke_tests": ["tests/forward/test_discovery.py::test_discovery_execution"],
    },
    "rup.phase_2_planning.2.1": {
        "modules": ["runtime.planning"],
        "symbols": ["PlanningPhase"],
        "runtime_smoke_tests": ["tests/forward/test_plan.py::test_plan_execution"],
    },
    "rup.phase_2_planning.2.2": {
        "modules": ["runtime.planning"],
        "symbols": ["PlanningPhase"],
        "runtime_smoke_tests": ["tests/forward/test_plan.py::test_plan_execution"],
    },
    "rup.phase_2_planning.2.3": {
        "modules": ["runtime.planning"],
        "symbols": ["PlanningPhase"],
        "runtime_smoke_tests": ["tests/forward/test_plan.py::test_plan_execution"],
    },
    "rup.phase_2_planning.2.4": {
        "modules": ["runtime.planning"],
        "symbols": ["PlanningPhase"],
        "runtime_smoke_tests": ["tests/forward/test_plan.py::test_plan_execution"],
    },
    "rup.phase_3_execution.workstreams": {
        "modules": ["runtime.execution"],
        "symbols": ["ExecutionPhase"],
        "runtime_smoke_tests": ["tests/forward/test_execute.py::test_execute_execution"],
    },
    "rup.phase_4_verification.4.1": {
        "modules": ["runtime.verification"],
        "symbols": ["VerificationPhase"],
        "runtime_smoke_tests": ["tests/forward/test_verify.py::test_verify_execution"],
    },
    "rup.phase_4_verification.4.2": {
        "modules": ["runtime.verification"],
        "symbols": ["VerificationPhase"],
        "runtime_smoke_tests": ["tests/forward/test_verify.py::test_verify_execution"],
    },
    "rup.phase_4_verification.4.3": {
        "modules": ["runtime.verification"],
        "symbols": ["VerificationPhase"],
        "runtime_smoke_tests": ["tests/forward/test_verify.py::test_verify_execution"],
    },
    "rup.phase_4_verification.4.4": {
        "modules": ["runtime.verification"],
        "symbols": ["VerificationPhase"],
        "runtime_smoke_tests": ["tests/forward/test_verify.py::test_verify_execution"],
    },
    "rup.phase_4_verification.4.5": {
        "modules": ["runtime.verification"],
        "symbols": ["VerificationPhase"],
        "runtime_smoke_tests": ["tests/forward/test_verify.py::test_verify_execution"],
    },
    "rup.phase_4_verification.4.6": {
        "modules": ["runtime.reporting", "runtime.artifact_builder"],
        "symbols": ["ReportingPhase", "ArtifactBuilder"],
        "runtime_smoke_tests": ["tests/forward/test_report.py::test_report_execution"],
    },
    "rup.guardrails.security": {
        "modules": ["runtime.security", "runtime.redaction"],
        "symbols": ["enforce_path_jail", "check_prompt_injection", "redact_secrets"],
        "runtime_smoke_tests": [],
        "semantic_tests": [
            "tests/test_security_scanning.py::test_prompt_injection_detection",
            "tests/test_security_scanning.py::test_yaml_alias_bomb_rejected",
            "tests/test_security_scanning.py::test_yaml_unsafe_object_rejected",
        ],
    },
    "rup.state.lifecycle": {
        "modules": ["runtime.state", "runtime.models"],
        "symbols": ["StateManager", "RunManifest"],
        "runtime_smoke_tests": ["tests/test_state.py::test_state_trust_boundary"],
    },
}


def _module_path(module_name: str) -> str:
    """Convert a Python module name to a filesystem path relative to the skill root."""
    return module_name.replace(".", "/") + ".py"


def _extract_symbols(py_path: Path) -> set:
    """Parse a Python file and return the set of top-level class/function names."""
    try:
        tree = ast.parse(py_path.read_text(encoding="utf-8"))
    except SyntaxError as exc:
        warnings.warn(f"Syntax error parsing {py_path}: {exc}")
        return set()
    classes = {node.name for node in ast.walk(tree) if isinstance(node, ast.ClassDef)}
    functions = {node.name for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)}
    return classes.union(functions)


def _verify_implementation(skill_root: Path, modules: List[str], symbols: List[str]) -> Dict[str, Any]:
    """Verify that implementation files exist and required symbols are defined."""
    defined_symbols: set = set()
    all_files_exist = True
    missing_files: List[str] = []
    missing_symbols: List[str] = []

    for module_name in modules:
        rel_path = _module_path(module_name)
        full_path = skill_root / rel_path
        if not full_path.exists():
            all_files_exist = False
            missing_files.append(rel_path)
            continue
        defined_symbols.update(_extract_symbols(full_path))

    if not all_files_exist:
        return {"files_exist": False, "symbols_verified": False, "missing_files": missing_files}

    for symbol in symbols:
        if symbol not in defined_symbols:
            missing_symbols.append(symbol)

    return {
        "files_exist": True,
        "symbols_verified": len(missing_symbols) == 0,
        "missing_files": missing_files,
        "missing_symbols": missing_symbols,
    }


def _determine_verification_level(
    files_exist: bool,
    symbols_verified: bool,
    runtime_smoke_tests: List[str],
    semantic_tests: List[str],
) -> str:
    """
    Determine the honest verification level for a capability.

    Levels:
      - unverified: implementation files missing.
      - present: files exist but required AST symbols are missing.
      - structurally_verified: symbols exist but no tests are listed.
      - runtime_smoke_verified: runtime smoke tests pass (no semantic tests).
      - behaviorally_verified: semantic tests pass.
      - canonical_parity_verified: never auto-claimed; reserved for manual override.
    """
    if not files_exist:
        return "unverified"
    if not symbols_verified:
        return "present"
    if semantic_tests:
        return "behaviorally_verified"
    if runtime_smoke_tests:
        return "runtime_smoke_verified"
    return "structurally_verified"


def load_canonical_capabilities(skill_root: Path) -> List[Dict[str, Any]]:
    """
    Load the canonical capability inventory from protocol/rup-protocol.yaml and
    merge it with the controlled runtime translation table.
    """
    proto_path = skill_root / "protocol" / "rup-protocol.yaml"
    if not proto_path.exists():
        raise FileNotFoundError(f"Canonical protocol not found: {proto_path}")

    proto = safe_load_yaml(proto_path)
    phases = proto.get("phases", [])
    guardrails = proto.get("guardrails", {})

    capabilities: List[Dict[str, Any]] = []

    # Phase steps become capabilities.
    for phase in phases:
        phase_id = phase.get("id", "")
        # Strip the "phase_N_" prefix so "phase_4_verification" becomes "verification".
        category = phase_id.split("_", 2)[-1] if phase_id.startswith("phase_") else phase_id
        steps = phase.get("steps", [])
        for step in steps:
            step_id = step.get("id", "")
            cap_id = f"rup.{phase_id}.{step_id}"
            translation = PROTOCOL_CAPABILITY_TRANSLATION.get(cap_id, {})
            capabilities.append({
                "id": cap_id,
                "category": category,
                "name": step.get("name", ""),
                "mandatory": True,
                "modules": translation.get("modules", []),
                "symbols": translation.get("symbols", []),
                "runtime_smoke_tests": translation.get("runtime_smoke_tests", []),
                "semantic_tests": translation.get("semantic_tests", []),
            })

        # Phase 3 execution workstreams are handled by a single dispatcher capability
        # because the runtime execution phase orchestrates all workstreams.
        workstreams = phase.get("workstreams", {})
        if workstreams and phase_id == "phase_3_execution":
            cap_id = "rup.phase_3_execution.workstreams"
            translation = PROTOCOL_CAPABILITY_TRANSLATION.get(cap_id, {})
            capabilities.append({
                "id": cap_id,
                "category": "execution",
                "name": "Workstream Dispatch & Fix Implementation",
                "mandatory": True,
                "modules": translation.get("modules", []),
                "symbols": translation.get("symbols", []),
                "runtime_smoke_tests": translation.get("runtime_smoke_tests", []),
                "semantic_tests": translation.get("semantic_tests", []),
            })

    # Security guardrails capability.
    if guardrails:
        cap_id = "rup.guardrails.security"
        translation = PROTOCOL_CAPABILITY_TRANSLATION.get(cap_id, {})
        capabilities.append({
            "id": cap_id,
            "category": "security",
            "name": "Adversarial Defense & Path Jail",
            "mandatory": True,
            "modules": translation.get("modules", []),
            "symbols": translation.get("symbols", []),
            "runtime_smoke_tests": translation.get("runtime_smoke_tests", []),
            "semantic_tests": translation.get("semantic_tests", []),
        })

    # Runtime state management is not explicitly a protocol phase but is required
    # by every phase output template (run manifest, session state).
    cap_id = "rup.state.lifecycle"
    translation = PROTOCOL_CAPABILITY_TRANSLATION.get(cap_id, {})
    capabilities.append({
        "id": cap_id,
        "category": "state",
        "name": "Run Manifest & State Management",
        "mandatory": True,
        "modules": translation.get("modules", []),
        "symbols": translation.get("symbols", []),
        "runtime_smoke_tests": translation.get("runtime_smoke_tests", []),
        "semantic_tests": translation.get("semantic_tests", []),
    })

    return capabilities


# Import-time default generated from the canonical protocol in this repo.
ROOT = Path(__file__).parent.parent.resolve()
CANONICAL_CAPABILITIES: List[Dict[str, Any]] = load_canonical_capabilities(ROOT)


def verify_capabilities(skill_root: Path) -> Dict[str, Any]:
    """Verify that all canonical capabilities have implemented modules and symbols."""
    capabilities = load_canonical_capabilities(skill_root)
    results = []
    unmapped = 0

    for cap in capabilities:
        cap_id = cap["id"]
        impl = _verify_implementation(skill_root, cap["modules"], cap["symbols"])

        if not impl["files_exist"]:
            status = "unmapped"
            unmapped += 1
        elif not impl["symbols_verified"]:
            status = "unmapped"
            unmapped += 1
        else:
            status = "ported"

        verification_level = _determine_verification_level(
            impl["files_exist"],
            impl["symbols_verified"],
            cap.get("runtime_smoke_tests", []),
            cap.get("semantic_tests", []),
        )

        missing_details = impl.get("missing_files", []) + impl.get("missing_symbols", [])

        results.append({
            "id": cap_id,
            "category": cap["category"],
            "name": cap["name"],
            "mandatory": cap["mandatory"],
            "port_status": status,
            "verification_level": verification_level,
            "modules": cap["modules"],
            "symbols": cap["symbols"],
            "runtime_smoke_tests": cap.get("runtime_smoke_tests", []),
            "semantic_tests": cap.get("semantic_tests", []),
            "missing_details": missing_details,
        })

    return {
        "total": len(results),
        "ported": len(results) - unmapped,
        "unmapped": unmapped,
        "capabilities": results,
    }
