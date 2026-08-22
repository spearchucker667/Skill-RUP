# Skill-RUP Capability Mapping & Provenance

**Canonical Source**: `https://github.com/spearchucker667/RUP-Protocol` (v3.0.0 @ `c3d6f703`)

**Total Capabilities**: 27 | **Deterministic**: 14 | **Partial**: 12 | **Agent-native**: 1 | **Not ported**: 0 | **Parity verified**: 0 | **Unmapped**: 0

| Capability ID | Title | Status | Verification Level | Transfer Rationale |
|---------------|-------|--------|--------------------|--------------------|
| `rup.phase_1_discovery.1.1` | Repository Inventory | DETERMINISTIC | runtime_smoke_verified | Repository inventory is reimplemented deterministically in runtime/inventory.py (jailed walking, language detection, metadata) from the canonical phase-1 contract. |
| `rup.phase_1_discovery.1.2` | Tooling Detection | DETERMINISTIC | runtime_smoke_verified | Tooling detection is reimplemented in runtime/tool_detection.py (tests, linters, type checkers, CI, containers, IaC) from the canonical phase-1 tooling contract. |
| `rup.phase_1_discovery.1.3` | Quality Assessment | PARTIAL | runtime_smoke_verified | Quality assessment is partially ported: inventory plus gap heuristics in runtime/discovery.py; real coverage/duplication/complexity analysis is agent-native. |
| `rup.phase_1_discovery.1.4` | Security Assessment | PARTIAL | runtime_smoke_verified | Security assessment is partially ported: secret scan (runtime/redaction.py) and lockfile existence; full dependency/SBOM/license analysis is agent-native. |
| `rup.phase_1_discovery.1.5` | Documentation Assessment | DETERMINISTIC | runtime_smoke_verified | Documentation assessment is ported as deterministic existence/gap checks in runtime/discovery.py. |
| `rup.phase_1_discovery.1.6` | Governance Assessment | PARTIAL | runtime_smoke_verified | Governance assessment is partially ported: existence checks only; semantic usefulness of CODEOWNERS/SECURITY placeholders is not validated. |
| `rup.phase_1_discovery.1.7` | Gap Analysis | DETERMINISTIC | runtime_smoke_verified | CI/CD assessment is ported as deterministic workflow-file detection in runtime/discovery.py. |
| `rup.phase_2_planning.2.1` | Backlog Generation | DETERMINISTIC | runtime_smoke_verified | Backlog creation is ported: gaps become prioritized backlog items in runtime/planning.py. |
| `rup.phase_2_planning.2.2` | Risk Analysis | DETERMINISTIC | runtime_smoke_verified | Risk analysis is ported: severity-weighted risk scoring per backlog item in runtime/planning.py. |
| `rup.phase_2_planning.2.3` | Work Selection | PARTIAL | runtime_smoke_verified | Work selection is partially ported: budget/risk tolerance respected, but dependency closure is not enforced (audit P1-12). |
| `rup.phase_2_planning.2.4` | Execution Planning | PARTIAL | runtime_smoke_verified | Execution planning is partially ported: topological ordering emitted, but no checkpoint graph with verification methods (audit P1-13). |
| `rup.phase_3_execution.workstreams.bug_fixes` | Fix identified bugs with regression tests | AGENT_NATIVE | behaviorally_verified | Agent-native: the canonical reproduce-fix-3x-docs loop requires model reasoning; runtime/execution.py emits an AGENT_ONLY recommendation (audit P1-8). |
| `rup.phase_3_execution.workstreams.tests` | Add missing tests for critical paths | PARTIAL | behaviorally_verified | Partial: scaffolds pytest.ini and tests/ but does not author substantive tests (audit P1-9); test authoring is agent-native. |
| `rup.phase_3_execution.workstreams.ci_cd` | Add or fix CI/CD workflows | DETERMINISTIC | behaviorally_verified | Deterministic: generates platform CI workflows from detected package managers in runtime/execution.py (_handle_ci). |
| `rup.phase_3_execution.workstreams.security` | Address security gaps | PARTIAL | behaviorally_verified | Partial: SECURITY.md generation is deterministic; secret rotation is agent-native; lockfile remediation is partial (runtime/execution.py security handlers). |
| `rup.phase_3_execution.workstreams.documentation` | Improve documentation | DETERMINISTIC | behaviorally_verified | Deterministic: README/CONTRIBUTING scaffold generation in runtime/execution.py (_handle_readme/_handle_contributing). |
| `rup.phase_3_execution.workstreams.governance` | Add governance and automation | PARTIAL | behaviorally_verified | Partial: CODEOWNERS/LICENSE handling is deterministic but emits placeholder owners and auto-selects Apache-2.0 (audit P1-30/31/32); legal decisions are agent-native. |
| `rup.phase_3_execution.workstreams.containerization` | Add containerization best practices | PARTIAL | behaviorally_verified | Partial: canonical ws_containers Dockerfile/.dockerignore/Compose generation is deterministic (runtime/execution.py _handle_container); entrypoint/health-check confirmation remains agent-native. |
| `rup.phase_3_execution.workstreams.observability` | Add logging, metrics, tracing | PARTIAL | behaviorally_verified | Partial: canonical ws_observability baseline (JSON logging, standard metrics, OpenTelemetry tracing) is scaffolded deterministically (runtime/execution.py _handle_observability); runtime instrumentation remains agent-native. |
| `rup.phase_4_verification.4.1` | Test Verification | DETERMINISTIC | runtime_smoke_verified | Deterministic: test gates with 3-run flakiness detection in runtime/verification.py. |
| `rup.phase_4_verification.4.2` | Lint Verification | DETERMINISTIC | runtime_smoke_verified | Deterministic: lint/build gates now require rc==0 plus semantic results (RUP-VERIFY-001). |
| `rup.phase_4_verification.4.3` | Security Verification | PARTIAL | runtime_smoke_verified | Partial: security gates run, but secret scanning can report incomplete coverage and pattern coverage is below the canonical contract (audit P1-20/21). |
| `rup.phase_4_verification.4.4` | Build Verification | DETERMINISTIC | runtime_smoke_verified | Deterministic: type-check gate requires rc==0 (RUP-VERIFY-001). |
| `rup.phase_4_verification.4.5` | Documentation Verification | PARTIAL | runtime_smoke_verified | Partial: documentation verification is not implemented as a gate (audit P1-5). |
| `rup.phase_4_verification.4.6` | Report Generation | DETERMINISTIC | runtime_smoke_verified | Deterministic: certification aggregates gate results into RUP_VERIFICATION artifacts (runtime/verification.py, runtime/artifact_builder.py). |
| `rup.guardrails.security` | Adversarial Defense & Path Jail | DETERMINISTIC | behaviorally_verified | Deterministic: path jail, jailed I/O, prompt-injection scan, secret redaction, and sandbox gating in runtime/security.py, runtime/redaction.py, runtime/command_runner.py (RUP-SEC-001/002). |
| `rup.state.lifecycle` | Run Manifest & State Management | DETERMINISTIC | runtime_smoke_verified | Deterministic: atomic state persistence, run manifests, and session state in runtime/state.py and runtime/models.py. |
