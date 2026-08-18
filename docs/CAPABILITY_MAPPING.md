# Skill-RUP Capability Mapping & Provenance

**Canonical Source**: `https://github.com/spearchucker667/RUP-Protocol` (v3.0.0 @ `c3d6f703`)

**Total Capabilities**: 19 | **Ported & Verified**: 19 | **Incomplete**: 0

| Capability ID | Title | Implementation | Status | Semantic Equivalence |
|---------------|-------|----------------|--------|-----------------------|
| `rup.phase_1_discovery.1.1` | Repository Inventory | `runtime/inventory.py`, `runtime/discovery.py` | PORTED | PRESERVED |
| `rup.phase_1_discovery.1.2` | Tooling Detection | `runtime/tool_detection.py`, `runtime/discovery.py` | PORTED | PRESERVED |
| `rup.phase_1_discovery.1.3` | Quality Assessment | `runtime/discovery.py` | PORTED | PRESERVED |
| `rup.phase_1_discovery.1.4` | Security Assessment | `runtime/discovery.py`, `runtime/redaction.py` | PORTED | PRESERVED |
| `rup.phase_1_discovery.1.5` | Documentation Assessment | `runtime/discovery.py` | PORTED | PRESERVED |
| `rup.phase_1_discovery.1.6` | Governance Assessment | `runtime/discovery.py` | PORTED | PRESERVED |
| `rup.phase_1_discovery.1.7` | Gap Analysis & Scoring | `runtime/discovery.py` | PORTED | PRESERVED |
| `rup.phase_2_planning.2.1` | Backlog Generation | `runtime/planning.py` | PORTED | PRESERVED |
| `rup.phase_2_planning.2.2` | Risk Analysis | `runtime/planning.py` | PORTED | PRESERVED |
| `rup.phase_2_planning.2.3` | Work Selection & Budgeting | `runtime/planning.py` | PORTED | PRESERVED |
| `rup.phase_2_planning.2.4` | Execution Planning & Checkpoints | `runtime/planning.py` | PORTED | PRESERVED |
| `rup.phase_3_execution.workstreams` | Workstream Dispatch & Fix Implementation | `runtime/execution.py` | PORTED | PRESERVED |
| `rup.phase_4_verification.4.1` | Test Verification (3-run & flakiness) | `runtime/verification.py` | PORTED | PRESERVED |
| `rup.phase_4_verification.4.2` | Lint Verification | `runtime/verification.py` | PORTED | PRESERVED |
| `rup.phase_4_verification.4.3` | Security Verification | `runtime/verification.py` | PORTED | PRESERVED |
| `rup.phase_4_verification.4.4` | Build & Type Verification | `runtime/verification.py` | PORTED | PRESERVED |
| `rup.phase_4_verification.4.6` | Final Report Generation | `runtime/reporting.py`, `runtime/artifact_builder.py` | PORTED | PRESERVED |
| `rup.guardrails.security` | Adversarial Defense & Path Jail | `runtime/security.py`, `runtime/redaction.py` | PORTED | PRESERVED |
| `rup.state.lifecycle` | Run Manifest & State Management | `runtime/state.py`, `runtime/models.py` | PORTED | PRESERVED |
