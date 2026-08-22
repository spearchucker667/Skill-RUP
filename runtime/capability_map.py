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
#
# ``port_status`` is the curated transfer class and is authoritative:
#   - deterministic : fully ported as deterministic runtime behavior
#   - partial       : scaffolding/partial deterministic implementation
#   - agent_native  : behavior requires model/agent judgment (not automatable)
#   - not_ported    : explicitly not ported to the deterministic runtime
#   - parity_verified: reserved; canonical parity is never auto-claimed.
# Verification evidence (AST symbols, tests) can never upgrade a capability
# beyond its declared class: a NOT_PORTED handler can never be reported PORTED.
PORT_CLASSES = ("deterministic", "partial", "agent_native", "not_ported", "parity_verified")

# Per-capability transfer rationale linking the canonical upstream behavior to
# the downstream implementation that preserves it (audit P1-4). The canonical
# source of truth for every capability is protocol/rup-protocol.yaml (pinned);
# this table explains where the *behavior* was ported to.
TRANSFER_RATIONALE: Dict[str, str] = {
    "rup.phase_1_discovery.1.1": (
        "Repository inventory is reimplemented deterministically in runtime/inventory.py "
        "(jailed walking, language detection, metadata) from the canonical phase-1 contract."
    ),
    "rup.phase_1_discovery.1.2": (
        "Tooling detection is reimplemented in runtime/tool_detection.py (tests, linters, "
        "type checkers, CI, containers, IaC) from the canonical phase-1 tooling contract."
    ),
    "rup.phase_1_discovery.1.3": (
        "Quality assessment is partially ported: inventory plus gap heuristics in "
        "runtime/discovery.py; real coverage/duplication/complexity analysis is agent-native."
    ),
    "rup.phase_1_discovery.1.4": (
        "Security assessment is partially ported: secret scan (runtime/redaction.py) and "
        "lockfile existence; full dependency/SBOM/license analysis is agent-native."
    ),
    "rup.phase_1_discovery.1.5": (
        "Documentation assessment is ported as deterministic existence/gap checks in runtime/discovery.py."
    ),
    "rup.phase_1_discovery.1.6": (
        "Governance assessment is partially ported: existence checks only; semantic "
        "usefulness of CODEOWNERS/SECURITY placeholders is not validated."
    ),
    "rup.phase_1_discovery.1.7": (
        "CI/CD assessment is ported as deterministic workflow-file detection in runtime/discovery.py."
    ),
    "rup.phase_2_planning.2.1": (
        "Backlog creation is ported: gaps become prioritized backlog items in runtime/planning.py."
    ),
    "rup.phase_2_planning.2.2": (
        "Risk analysis is ported: severity-weighted risk scoring per backlog item in runtime/planning.py."
    ),
    "rup.phase_2_planning.2.3": (
        "Work selection is partially ported: budget/risk tolerance respected, but dependency "
        "closure is not enforced (audit P1-12)."
    ),
    "rup.phase_2_planning.2.4": (
        "Execution planning is partially ported: topological ordering emitted, but no "
        "checkpoint graph with verification methods (audit P1-13)."
    ),
    "rup.phase_3_execution.workstreams.bug_fixes": (
        "Agent-native: the canonical reproduce-fix-3x-docs loop requires model reasoning; "
        "runtime/execution.py emits an AGENT_ONLY recommendation (audit P1-8)."
    ),
    "rup.phase_3_execution.workstreams.tests": (
        "Partial: scaffolds pytest.ini and tests/ but does not author substantive tests "
        "(audit P1-9); test authoring is agent-native."
    ),
    "rup.phase_3_execution.workstreams.ci_cd": (
        "Deterministic: generates platform CI workflows from detected package managers in "
        "runtime/execution.py (_handle_ci)."
    ),
    "rup.phase_3_execution.workstreams.security": (
        "Partial: SECURITY.md generation is deterministic; secret rotation is agent-native; "
        "lockfile remediation is partial (runtime/execution.py security handlers)."
    ),
    "rup.phase_3_execution.workstreams.documentation": (
        "Deterministic: README/CONTRIBUTING scaffold generation in runtime/execution.py "
        "(_handle_readme/_handle_contributing)."
    ),
    "rup.phase_3_execution.workstreams.governance": (
        "Partial: CODEOWNERS/LICENSE handling is deterministic but emits placeholder owners "
        "and auto-selects Apache-2.0 (audit P1-30/31/32); legal decisions are agent-native."
    ),
    "rup.phase_3_execution.workstreams.containerization": (
        "Partial: canonical ws_containers Dockerfile/.dockerignore/Compose generation is "
        "deterministic (runtime/execution.py _handle_container); entrypoint/health-check "
        "confirmation remains agent-native."
    ),
    "rup.phase_3_execution.workstreams.observability": (
        "Partial: canonical ws_observability baseline (JSON logging, standard metrics, "
        "OpenTelemetry tracing) is scaffolded deterministically (runtime/execution.py "
        "_handle_observability); runtime instrumentation remains agent-native."
    ),
    "rup.phase_4_verification.4.1": (
        "Deterministic: test gates with 3-run flakiness detection in runtime/verification.py."
    ),
    "rup.phase_4_verification.4.2": (
        "Deterministic: lint/build gates now require rc==0 plus semantic results (RUP-VERIFY-001)."
    ),
    "rup.phase_4_verification.4.3": (
        "Partial: security gates run, but secret scanning can report incomplete coverage and "
        "pattern coverage is below the canonical contract (audit P1-20/21)."
    ),
    "rup.phase_4_verification.4.4": (
        "Deterministic: type-check gate requires rc==0 (RUP-VERIFY-001)."
    ),
    "rup.phase_4_verification.4.5": (
        "Partial: documentation verification is not implemented as a gate (audit P1-5)."
    ),
    "rup.phase_4_verification.4.6": (
        "Deterministic: certification aggregates gate results into RUP_VERIFICATION artifacts "
        "(runtime/verification.py, runtime/artifact_builder.py)."
    ),
    "rup.guardrails.security": (
        "Deterministic: path jail, jailed I/O, prompt-injection scan, secret redaction, and "
        "sandbox gating in runtime/security.py, runtime/redaction.py, runtime/command_runner.py "
        "(RUP-SEC-001/002)."
    ),
    "rup.state.lifecycle": (
        "Deterministic: atomic state persistence, run manifests, and session state in "
        "runtime/state.py and runtime/models.py."
    ),
}

PROTOCOL_CAPABILITY_TRANSLATION: Dict[str, Dict[str, Any]] = {
    "rup.phase_1_discovery.1.1": {
        "modules": ["runtime.inventory", "runtime.discovery"],
        "symbols": ["InventoryManager", "DiscoveryPhase"],
        "port_status": "deterministic",
        "runtime_smoke_tests": ["tests/forward/test_discovery.py::test_discovery_execution"],
    },
    "rup.phase_1_discovery.1.2": {
        "modules": ["runtime.tool_detection", "runtime.discovery"],
        "symbols": ["ToolDetector", "DiscoveryPhase"],
        "port_status": "deterministic",
        "runtime_smoke_tests": ["tests/forward/test_discovery.py::test_discovery_execution"],
    },
    "rup.phase_1_discovery.1.3": {
        # Quality assessment: inventory + gap heuristics only; no real coverage /
        # duplication / complexity analysis (audit P1-5).
        "modules": ["runtime.discovery"],
        "symbols": ["DiscoveryPhase"],
        "port_status": "partial",
        "runtime_smoke_tests": ["tests/forward/test_discovery.py::test_discovery_execution"],
    },
    "rup.phase_1_discovery.1.4": {
        # Security assessment: secret scan + lockfile existence only (audit P1-5).
        "modules": ["runtime.discovery", "runtime.redaction"],
        "symbols": ["DiscoveryPhase", "scan_secrets"],
        "port_status": "partial",
        "runtime_smoke_tests": ["tests/forward/test_discovery.py::test_discovery_execution"],
    },
    "rup.phase_1_discovery.1.5": {
        "modules": ["runtime.discovery"],
        "symbols": ["DiscoveryPhase"],
        "port_status": "deterministic",
        "runtime_smoke_tests": ["tests/forward/test_discovery.py::test_discovery_execution"],
    },
    "rup.phase_1_discovery.1.6": {
        # Governance assessment is existence-based; semantic usefulness is not
        # validated (audit P1-32).
        "modules": ["runtime.discovery"],
        "symbols": ["DiscoveryPhase"],
        "port_status": "partial",
        "runtime_smoke_tests": ["tests/forward/test_discovery.py::test_discovery_execution"],
    },
    "rup.phase_1_discovery.1.7": {
        "modules": ["runtime.discovery"],
        "symbols": ["DiscoveryPhase"],
        "port_status": "deterministic",
        "runtime_smoke_tests": ["tests/forward/test_discovery.py::test_discovery_execution"],
    },
    "rup.phase_2_planning.2.1": {
        "modules": ["runtime.planning"],
        "symbols": ["PlanningPhase"],
        "port_status": "deterministic",
        "runtime_smoke_tests": ["tests/forward/test_plan.py::test_plan_execution"],
    },
    "rup.phase_2_planning.2.2": {
        "modules": ["runtime.planning"],
        "symbols": ["PlanningPhase"],
        "port_status": "deterministic",
        "runtime_smoke_tests": ["tests/forward/test_plan.py::test_plan_execution"],
    },
    "rup.phase_2_planning.2.3": {
        # Work selection ignores dependency closure (audit P1-12).
        "modules": ["runtime.planning"],
        "symbols": ["PlanningPhase"],
        "port_status": "partial",
        "runtime_smoke_tests": ["tests/forward/test_plan.py::test_plan_execution"],
    },
    "rup.phase_2_planning.2.4": {
        # Execution planning emits an order but no checkpoint graph (audit P1-13).
        "modules": ["runtime.planning"],
        "symbols": ["PlanningPhase"],
        "port_status": "partial",
        "runtime_smoke_tests": ["tests/forward/test_plan.py::test_plan_execution"],
    },
    # Phase 3 execution workstreams are decomposed individually so a NOT_PORTED
    # handler can never be hidden behind a shared dispatcher capability (audit P1-1).
    "rup.phase_3_execution.workstreams.bug_fixes": {
        # Canonical bug-fix process (reproduce -> fix -> 3x -> docs) is not
        # implemented; the handler emits an AGENT_ONLY recommendation (audit P1-8).
        "modules": ["runtime.execution"],
        "symbols": ["ExecutionPhase", "_handle_bugs"],
        "port_status": "agent_native",
        "semantic_tests": ["tests/test_execution.py::test_bug_workstream_emits_agent_only_recommendation"],
    },
    "rup.phase_3_execution.workstreams.tests": {
        # Scaffolds pytest.ini/tests dir but refuses to author substantive tests
        # (audit P1-9).
        "modules": ["runtime.execution"],
        "symbols": ["ExecutionPhase", "_handle_tests"],
        "port_status": "partial",
        "semantic_tests": ["tests/test_execution.py::test_test_workstream_creates_pytest_ini_and_recommends_tests"],
    },
    "rup.phase_3_execution.workstreams.ci_cd": {
        "modules": ["runtime.execution"],
        "symbols": ["ExecutionPhase", "_handle_ci"],
        "port_status": "deterministic",
        "semantic_tests": ["tests/test_execution.py::test_ci_generator_uses_detected_package_manager"],
    },
    "rup.phase_3_execution.workstreams.security": {
        # SECURITY.md generation is deterministic; secret rotation and lockfile
        # generation are agent-native / partial respectively (audit P1-8/P1-10).
        "modules": ["runtime.execution"],
        "symbols": ["ExecutionPhase", "_handle_security_policy", "_handle_secret_exposure"],
        "port_status": "partial",
        "semantic_tests": ["tests/test_execution.py::test_security_subtypes_dispatch_correctly"],
    },
    "rup.phase_3_execution.workstreams.documentation": {
        "modules": ["runtime.execution"],
        "symbols": ["ExecutionPhase", "_handle_readme", "_handle_contributing"],
        "port_status": "deterministic",
        "semantic_tests": ["tests/test_execution.py::test_rup_only_changes_attributed_to_backlog_items"],
    },
    "rup.phase_3_execution.workstreams.governance": {
        # CODEOWNERS is emitted with commented placeholders and license selection
        # is automatic (audit P1-30/31/32).
        "modules": ["runtime.execution"],
        "symbols": ["ExecutionPhase", "_handle_codeowners", "_handle_license"],
        "port_status": "partial",
        "semantic_tests": ["tests/test_execution.py::test_truncated_license_is_not_generated"],
    },
    "rup.phase_3_execution.workstreams.containerization": {
        "modules": ["runtime.execution"],
        "symbols": ["ExecutionPhase", "_handle_container"],
        "port_status": "partial",
        "semantic_tests": ["tests/test_execution.py::test_containerization_generates_dockerfile"],
    },
    "rup.phase_3_execution.workstreams.observability": {
        "modules": ["runtime.execution"],
        "symbols": ["ExecutionPhase", "_handle_observability"],
        "port_status": "partial",
        "semantic_tests": ["tests/test_execution.py::test_observability_generates_baseline"],
    },
    "rup.phase_4_verification.4.1": {
        "modules": ["runtime.verification"],
        "symbols": ["VerificationPhase"],
        "port_status": "deterministic",
        "runtime_smoke_tests": ["tests/forward/test_verify.py::test_verify_execution"],
    },
    "rup.phase_4_verification.4.2": {
        "modules": ["runtime.verification"],
        "symbols": ["VerificationPhase"],
        "port_status": "deterministic",
        "runtime_smoke_tests": ["tests/forward/test_verify.py::test_verify_execution"],
    },
    "rup.phase_4_verification.4.3": {
        # Security gates run, but secret scanning fails open on oversized files
        # and pattern coverage is below the contract (audit P1-20/21).
        "modules": ["runtime.verification"],
        "symbols": ["VerificationPhase"],
        "port_status": "partial",
        "runtime_smoke_tests": ["tests/forward/test_verify.py::test_verify_execution"],
    },
    "rup.phase_4_verification.4.4": {
        "modules": ["runtime.verification"],
        "symbols": ["VerificationPhase"],
        "port_status": "deterministic",
        "runtime_smoke_tests": ["tests/forward/test_verify.py::test_verify_execution"],
    },
    "rup.phase_4_verification.4.5": {
        # Documentation verification is not implemented as a gate.
        "modules": ["runtime.verification"],
        "symbols": ["VerificationPhase"],
        "port_status": "partial",
        "runtime_smoke_tests": ["tests/forward/test_verify.py::test_verify_execution"],
    },
    "rup.phase_4_verification.4.6": {
        "modules": ["runtime.reporting", "runtime.artifact_builder"],
        "symbols": ["ReportingPhase", "ArtifactBuilder"],
        "port_status": "deterministic",
        "runtime_smoke_tests": ["tests/forward/test_report.py::test_report_execution"],
    },
    "rup.guardrails.security": {
        "modules": ["runtime.security", "runtime.redaction"],
        "symbols": ["enforce_path_jail", "check_prompt_injection", "redact_secrets"],
        "port_status": "deterministic",
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
        "port_status": "deterministic",
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


def _build_capability(cap_id: str, category: str, name: str, translation: Dict[str, Any]) -> Dict[str, Any]:
    """Construct a capability record from the canonical translation table."""
    return {
        "id": cap_id,
        "category": category,
        "name": name,
        "mandatory": True,
        "port_status": translation.get("port_status", "agent_native"),
        "transfer_rationale": TRANSFER_RATIONALE.get(
            cap_id,
            "Canonical behavior defined in protocol/rup-protocol.yaml; downstream implementation in the listed modules.",
        ),
        "modules": translation.get("modules", []),
        "symbols": translation.get("symbols", []),
        "runtime_smoke_tests": translation.get("runtime_smoke_tests", []),
        "semantic_tests": translation.get("semantic_tests", []),
    }


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
            capabilities.append(
                _build_capability(cap_id, category, step.get("name", ""), translation)
            )

        # Phase 3 execution workstreams are decomposed into individual
        # capabilities so a NOT_PORTED handler can never be hidden behind a
        # shared dispatcher capability (audit P1-1). Each workstream carries
        # its own curated port class and semantic acceptance tests.
        workstreams = phase.get("workstreams", {})
        if workstreams and phase_id == "phase_3_execution":
            for ws_key, ws_body in workstreams.items():
                cap_id = f"rup.phase_3_execution.workstreams.{ws_key}"
                translation = PROTOCOL_CAPABILITY_TRANSLATION.get(cap_id, {})
                capabilities.append(
                    _build_capability(
                        cap_id,
                        "execution",
                        ws_body.get("description", ws_key),
                        translation,
                    )
                )

    # Security guardrails capability.
    if guardrails:
        cap_id = "rup.guardrails.security"
        translation = PROTOCOL_CAPABILITY_TRANSLATION.get(cap_id, {})
        capabilities.append(
            _build_capability(cap_id, "security", "Adversarial Defense & Path Jail", translation)
        )

    # Runtime state management is not explicitly a protocol phase but is required
    # by every phase output template (run manifest, session state).
    cap_id = "rup.state.lifecycle"
    translation = PROTOCOL_CAPABILITY_TRANSLATION.get(cap_id, {})
    capabilities.append(
        _build_capability(cap_id, "state", "Run Manifest & State Management", translation)
    )

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

        # The curated port class is authoritative and can never be upgraded by
        # verification evidence: a NOT_PORTED handler stays NOT_PORTED even when
        # its symbols exist and its semantic tests pass. Missing implementation
        # files/symbols are the only way to move a capability to "unmapped".
        declared_class = cap.get("port_status", "agent_native")
        if declared_class not in PORT_CLASSES:
            warnings.warn(f"{cap_id}: unknown port class {declared_class!r}; treating as agent_native")
            declared_class = "agent_native"
        if not impl["files_exist"] or not impl["symbols_verified"]:
            status = "unmapped"
            unmapped += 1
        else:
            status = declared_class

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
            "port_class": declared_class,
            "port_status": status,
            "verification_level": verification_level,
            "modules": cap["modules"],
            "symbols": cap["symbols"],
            "runtime_smoke_tests": cap.get("runtime_smoke_tests", []),
            "semantic_tests": cap.get("semantic_tests", []),
            "missing_details": missing_details,
        })

    by_class: Dict[str, int] = {}
    by_level: Dict[str, int] = {}
    for cap in results:
        by_class[cap["port_status"]] = by_class.get(cap["port_status"], 0) + 1
        by_level[cap["verification_level"]] = by_level.get(cap["verification_level"], 0) + 1

    return {
        "total": len(results),
        "unmapped": unmapped,
        # Only fully-claimed classes count as "ported"; partial/agent-native/
        # not-ported capabilities are reported separately (audit P1-2).
        "ported": by_class.get("deterministic", 0) + by_class.get("parity_verified", 0),
        "by_class": by_class,
        "by_verification_level": by_level,
        "capabilities": results,
    }
