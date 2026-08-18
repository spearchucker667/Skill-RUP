# Skill-RUP Capability Mapping & Provenance

**Canonical Source**: `https://github.com/spearchucker667/RUP-Protocol` (v3.0.0 @ `c3d6f703`)

**Total Capabilities**: 19 | **Ported & Verified**: 19 | **Incomplete**: 0

| Capability ID | Title | Implementation | Status | Verification Level | Behavioral Tests |
|---------------|-------|----------------|--------|--------------------|------------------|
| `rup.phase_1_discovery.1.1` | Repository Inventory | `runtime/inventory.py`, `runtime/discovery.py` | PORTED | behaviorally_verified | `tests/forward/test_discovery.py::test_discovery_execution` |
| `rup.phase_1_discovery.1.2` | Tooling Detection | `runtime/tool_detection.py`, `runtime/discovery.py` | PORTED | behaviorally_verified | `tests/forward/test_discovery.py::test_discovery_execution` |
| `rup.phase_1_discovery.1.3` | Quality Assessment | `runtime/discovery.py` | PORTED | behaviorally_verified | `tests/forward/test_discovery.py::test_discovery_execution` |
| `rup.phase_1_discovery.1.4` | Security Assessment | `runtime/discovery.py`, `runtime/redaction.py` | PORTED | behaviorally_verified | `tests/forward/test_discovery.py::test_discovery_execution` |
| `rup.phase_1_discovery.1.5` | Documentation Assessment | `runtime/discovery.py` | PORTED | behaviorally_verified | `tests/forward/test_discovery.py::test_discovery_execution` |
| `rup.phase_1_discovery.1.6` | Governance Assessment | `runtime/discovery.py` | PORTED | behaviorally_verified | `tests/forward/test_discovery.py::test_discovery_execution` |
| `rup.phase_1_discovery.1.7` | Gap Analysis & Scoring | `runtime/discovery.py` | PORTED | behaviorally_verified | `tests/forward/test_discovery.py::test_discovery_execution` |
| `rup.phase_2_planning.2.1` | Backlog Generation | `runtime/planning.py` | PORTED | behaviorally_verified | `tests/forward/test_plan.py::test_plan_execution` |
| `rup.phase_2_planning.2.2` | Risk Analysis | `runtime/planning.py` | PORTED | behaviorally_verified | `tests/forward/test_plan.py::test_plan_execution` |
| `rup.phase_2_planning.2.3` | Work Selection & Budgeting | `runtime/planning.py` | PORTED | behaviorally_verified | `tests/forward/test_plan.py::test_plan_execution` |
| `rup.phase_2_planning.2.4` | Execution Planning & Checkpoints | `runtime/planning.py` | PORTED | behaviorally_verified | `tests/forward/test_plan.py::test_plan_execution` |
| `rup.phase_3_execution.workstreams` | Workstream Dispatch & Fix Implementation | `runtime/execution.py` | PORTED | behaviorally_verified | `tests/forward/test_execute.py::test_execute_execution` |
| `rup.phase_4_verification.4.1` | Test Verification (3-run & flakiness) | `runtime/verification.py` | PORTED | behaviorally_verified | `tests/forward/test_verify.py::test_verify_execution` |
| `rup.phase_4_verification.4.2` | Lint Verification | `runtime/verification.py` | PORTED | behaviorally_verified | `tests/forward/test_verify.py::test_verify_execution` |
| `rup.phase_4_verification.4.3` | Security Verification | `runtime/verification.py` | PORTED | behaviorally_verified | `tests/forward/test_verify.py::test_verify_execution` |
| `rup.phase_4_verification.4.4` | Build & Type Verification | `runtime/verification.py` | PORTED | behaviorally_verified | `tests/forward/test_verify.py::test_verify_execution` |
| `rup.phase_4_verification.4.6` | Final Report Generation | `runtime/reporting.py`, `runtime/artifact_builder.py` | PORTED | behaviorally_verified | `tests/forward/test_report.py::test_report_execution` |
| `rup.guardrails.security` | Adversarial Defense & Path Jail | `runtime/security.py`, `runtime/redaction.py` | PORTED | behaviorally_verified | `tests/test_security_scanning.py::test_prompt_injection_detection`, `tests/test_security_scanning.py::test_yaml_alias_bomb_rejected`, `tests/test_security_scanning.py::test_yaml_unsafe_object_rejected` |
| `rup.state.lifecycle` | Run Manifest & State Management | `runtime/state.py`, `runtime/models.py` | PORTED | behaviorally_verified | `tests/test_state.py::test_state_trust_boundary` |
