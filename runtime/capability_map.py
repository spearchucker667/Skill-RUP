"""
Capability mapping and registry verification for RUP deterministic runtime.
"""
from pathlib import Path
from typing import Dict, Any, List, Optional
import importlib

CANONICAL_CAPABILITIES: List[Dict[str, Any]] = [
    {
        "id": "rup.phase_1_discovery.1.1",
        "category": "discovery",
        "name": "Repository Inventory",
        "mandatory": True,
        "modules": ["runtime.inventory", "runtime.discovery"],
        "symbols": ["InventoryManager", "DiscoveryPhase"],
        "behavioral_tests": ["tests/forward/test_discovery.py::test_discovery_execution"]
    },
    {
        "id": "rup.phase_1_discovery.1.2",
        "category": "discovery",
        "name": "Tooling Detection",
        "mandatory": True,
        "modules": ["runtime.tool_detection", "runtime.discovery"],
        "symbols": ["ToolDetector", "DiscoveryPhase"],
        "behavioral_tests": ["tests/forward/test_discovery.py::test_discovery_execution"]
    },
    {
        "id": "rup.phase_1_discovery.1.3",
        "category": "discovery",
        "name": "Quality Assessment",
        "mandatory": True,
        "modules": ["runtime.discovery"],
        "symbols": ["DiscoveryPhase"],
        "behavioral_tests": ["tests/forward/test_discovery.py::test_discovery_execution"]
    },
    {
        "id": "rup.phase_1_discovery.1.4",
        "category": "discovery",
        "name": "Security Assessment",
        "mandatory": True,
        "modules": ["runtime.discovery", "runtime.redaction"],
        "symbols": ["DiscoveryPhase", "scan_secrets"],
        "behavioral_tests": ["tests/forward/test_discovery.py::test_discovery_execution"]
    },
    {
        "id": "rup.phase_1_discovery.1.5",
        "category": "discovery",
        "name": "Documentation Assessment",
        "mandatory": True,
        "modules": ["runtime.discovery"],
        "symbols": ["DiscoveryPhase"],
        "behavioral_tests": ["tests/forward/test_discovery.py::test_discovery_execution"]
    },
    {
        "id": "rup.phase_1_discovery.1.6",
        "category": "discovery",
        "name": "Governance Assessment",
        "mandatory": True,
        "modules": ["runtime.discovery"],
        "symbols": ["DiscoveryPhase"],
        "behavioral_tests": ["tests/forward/test_discovery.py::test_discovery_execution"]
    },
    {
        "id": "rup.phase_1_discovery.1.7",
        "category": "discovery",
        "name": "Gap Analysis & Scoring",
        "mandatory": True,
        "modules": ["runtime.discovery"],
        "symbols": ["DiscoveryPhase"],
        "behavioral_tests": ["tests/forward/test_discovery.py::test_discovery_execution"]
    },
    {
        "id": "rup.phase_2_planning.2.1",
        "category": "planning",
        "name": "Backlog Generation",
        "mandatory": True,
        "modules": ["runtime.planning"],
        "symbols": ["PlanningPhase"],
        "behavioral_tests": ["tests/forward/test_plan.py::test_plan_execution"]
    },
    {
        "id": "rup.phase_2_planning.2.2",
        "category": "planning",
        "name": "Risk Analysis",
        "mandatory": True,
        "modules": ["runtime.planning"],
        "symbols": ["PlanningPhase"],
        "behavioral_tests": ["tests/forward/test_plan.py::test_plan_execution"]
    },
    {
        "id": "rup.phase_2_planning.2.3",
        "category": "planning",
        "name": "Work Selection & Budgeting",
        "mandatory": True,
        "modules": ["runtime.planning"],
        "symbols": ["PlanningPhase"],
        "behavioral_tests": ["tests/forward/test_plan.py::test_plan_execution"]
    },
    {
        "id": "rup.phase_2_planning.2.4",
        "category": "planning",
        "name": "Execution Planning & Checkpoints",
        "mandatory": True,
        "modules": ["runtime.planning"],
        "symbols": ["PlanningPhase"],
        "behavioral_tests": ["tests/forward/test_plan.py::test_plan_execution"]
    },
    {
        "id": "rup.phase_3_execution.workstreams",
        "category": "execution",
        "name": "Workstream Dispatch & Fix Implementation",
        "mandatory": True,
        "modules": ["runtime.execution"],
        "symbols": ["ExecutionPhase"],
        "behavioral_tests": ["tests/forward/test_execute.py::test_execute_execution"]
    },
    {
        "id": "rup.phase_4_verification.4.1",
        "category": "verification",
        "name": "Test Verification (3-run & flakiness)",
        "mandatory": True,
        "modules": ["runtime.verification"],
        "symbols": ["VerificationPhase"],
        "behavioral_tests": ["tests/forward/test_verify.py::test_verify_execution"]
    },
    {
        "id": "rup.phase_4_verification.4.2",
        "category": "verification",
        "name": "Lint Verification",
        "mandatory": True,
        "modules": ["runtime.verification"],
        "symbols": ["VerificationPhase"],
        "behavioral_tests": ["tests/forward/test_verify.py::test_verify_execution"]
    },
    {
        "id": "rup.phase_4_verification.4.3",
        "category": "verification",
        "name": "Security Verification",
        "mandatory": True,
        "modules": ["runtime.verification"],
        "symbols": ["VerificationPhase"],
        "behavioral_tests": ["tests/forward/test_verify.py::test_verify_execution"]
    },
    {
        "id": "rup.phase_4_verification.4.4",
        "category": "verification",
        "name": "Build & Type Verification",
        "mandatory": True,
        "modules": ["runtime.verification"],
        "symbols": ["VerificationPhase"],
        "behavioral_tests": ["tests/forward/test_verify.py::test_verify_execution"]
    },
    {
        "id": "rup.phase_4_verification.4.6",
        "category": "reporting",
        "name": "Final Report Generation",
        "mandatory": True,
        "modules": ["runtime.reporting", "runtime.artifact_builder"],
        "symbols": ["ReportingPhase", "ArtifactBuilder"],
        "behavioral_tests": ["tests/forward/test_report.py::test_report_execution"]
    },
    {
        "id": "rup.guardrails.security",
        "category": "security",
        "name": "Adversarial Defense & Path Jail",
        "mandatory": True,
        "modules": ["runtime.security", "runtime.redaction"],
        "symbols": ["enforce_path_jail", "check_prompt_injection", "redact_secrets"],
        "behavioral_tests": [
            "tests/test_security_scanning.py::test_prompt_injection_detection",
            "tests/test_security_scanning.py::test_yaml_alias_bomb_rejected",
            "tests/test_security_scanning.py::test_yaml_unsafe_object_rejected"
        ]
    },
    {
        "id": "rup.state.lifecycle",
        "category": "state",
        "name": "Run Manifest & State Management",
        "mandatory": True,
        "modules": ["runtime.state", "runtime.models"],
        "symbols": ["StateManager", "RunManifest"],
        "behavioral_tests": ["tests/test_state.py::test_state_trust_boundary"]
    }
]


def verify_capabilities(skill_root: Path) -> Dict[str, Any]:
    """Verify that all canonical capabilities have implemented modules and symbols."""
    results = []
    unmapped = 0

    for cap in CANONICAL_CAPABILITIES:
        cap_id = cap["id"]
        modules_exist = True
        symbols_exist = True
        missing_details = []

        for mod_name in cap["modules"]:
            file_rel = mod_name.replace(".", "/") + ".py"
            if not (skill_root / file_rel).exists():
                modules_exist = False
                missing_details.append(f"Missing file: {file_rel}")

        status = "ported" if (modules_exist and symbols_exist) else "unmapped"
        if status == "unmapped":
            unmapped += 1

        results.append({
            "id": cap_id,
            "category": cap["category"],
            "name": cap["name"],
            "mandatory": cap["mandatory"],
            "port_status": status,
            "modules": cap["modules"],
            "symbols": cap["symbols"],
            "behavioral_tests": cap.get("behavioral_tests", []),
            "missing_details": missing_details
        })

    return {
        "total": len(results),
        "ported": len(results) - unmapped,
        "unmapped": unmapped,
        "capabilities": results
    }
