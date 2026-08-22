# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [3.0.2] - 2026-08-22
### Changed
- The `iac_scan` verification gate now implements the full canonical
  `iac_validator` contract surface: `terraform init -backend=false` +
  `terraform validate` for Terraform configs (run from the directory containing
  the `.tf` files), `pulumi preview --non-interactive` for Pulumi projects, and
  the `security` operation via tfsec or checkov (MEDIUM+ findings fail the
  gate). Missing tooling is reported `unavailable` with an explicit follow-up
  (never a fabricated pass); provider-bound `terraform init` is reported
  `unavailable` rather than performing network acquisition.
- Discovery emits `IAC-001` (missing Infrastructure-as-Code) under the
  canonical `performance` gap dimension; the `ops_workstreams` forward fixture
  exercises the Terraform scaffold end-to-end.
- Added a `terraform-validation` CI job that generates the baseline through the
  runtime and proves `terraform init` + `terraform validate` pass; the
  generated baseline uses the `hashicorp/null` provider so the proof runs
  offline with no credentials.

## [3.0.1] - 2026-08-21
### Changed
- Ported the IaC handler (`_handle_iac`) from `NOT_PORTED` to a deterministic
  `PARTIAL` scaffold: canonical Terraform baseline (`terraform/main.tf` with
  pinned `hashicorp/aws` provider, `variables.tf`, `outputs.tf`), additive only
  — existing `*.tf` or Pulumi projects are never overwritten. The canonical
  `iac_validator` contract (validate/lint/security/cost) is surfaced as the
  follow-up agent step. No execution handler remains `NOT_PORTED`.
- Discovery emits `CONT-001` / `OBS-001` gaps (classified under the canonical
  `performance` / `dx` dimensions) and execution routes them by gap id to the
  `ws_containers` / `ws_observability` handlers; the `ops_workstreams` forward
  fixture exercises both through the full CLI lifecycle.
- Refreshed `dist/rup-skill-v3.0.0.zip` to track current HEAD.

## [3.0.0] - 2026-08-21
### Added
- Complete RUP Protocol v3.0.0 synchronization.
- Agent workflow projections in `workflows/`.
- Strict schema extraction for state artifacts.
- Deterministic Python 3.11+ runtime for Discovery, Planning, Execution, Verification, and Reporting.
- Robust security jailing and prompt-injection detection.
- Deep capability mapping and validation tracking.
- Test suites covering integration and portability.

### Security (RUP-SEC-001/002)
- Universal jailed I/O primitives (`iter_jailed_files`, `open_jailed_read`,
  `atomic_jailed_write`, `jailed_mkdir`, `jailed_unlink`) for every target
  read/write, including execution handlers, state migration, tool detection,
  provenance hashing, and packaging (symlinked members rejected).
- Default `<target>/.rup` state root resolved and containment-verified.
- Pre-execution adversarial trust gate, `--allow-exec`, and
  `--sandbox required|preferred|off` (default `required`); scrubbed subprocess
  environment, bounded and secret-redacted output.
- Secret scanning with structured coverage status (strict mode fails closed on
  incomplete coverage), gitleaks/trufflehog merged when installed, and expanded
  built-in token patterns (GitLab, npm, PyPI, Stripe, Google, AWS session).
- Offline JS/TS tool resolution (local `.bin`, `npm exec --offline`,
  `pnpm/yarn exec`, `npx --no-install`); network acquisition refused.

### Runtime
- Planning constraints propagate from `plan-state.json` to execution and run
  IDs; `ExecutionPhase` enforces the escalation guard itself.
- Verification gates require explicit `command_succeeded` (rc==0) alongside
  semantic results.
- Per-workstream capability classes (deterministic/partial/agent_native/
  not_ported) that verification evidence can never upgrade.
- Dependency closure in work selection; per-workstream checkpoint graph
  enforced per item by execution.
- Transactional rollback: content baseline (HEAD + per-path hashes),
  baseline-dirty-path write refusal, content-addressed backups, per-item
  platform-neutral operations, and a `rollback` CLI phase.
- Monorepo workspace package graph (npm/yarn/pnpm, lerna, nx, turborepo,
  cargo, go.work) with `--workspace` / `--changed-packages` scoping,
  per-package tooling, per-package writes, and aggregate reporting.
- Provenance reports omissions separately from transfer passes with
  per-capability rationale; capability lineage carries transfer rationale.

### Changed
- Refactored `SKILL.md` to properly route sub-workflows and enforce schema validation.
- Restructured `runtime/` to strictly return typed outputs and adhere to Schema Draft 2020-12.
- Ported the containerization (`ws_containers`) and observability (`ws_observability`)
  workstreams from `NOT_PORTED` to `PARTIAL`: canonical multi-stage Dockerfile /
  `.dockerignore` / Compose scaffolding (language-aware, never overwrites user
  files) and an observability baseline (JSON structured logging, standard
  metrics, OpenTelemetry tracing with W3C Trace Context). All 27 canonical
  capabilities now have implementation; 0 remain `not_ported`.
- Discovery now flags missing container configuration (`CONT-001`, classified
  under the canonical `performance` gap dimension) and a missing observability
  baseline (`OBS-001`, under `dx`) since the canonical Gap category enum has no
  dedicated slots; execution routes those gap ids to the `ws_containers` /
  `ws_observability` handlers. New `ops_workstreams` forward fixture exercises
  both handlers through the full CLI lifecycle.

[3.0.0]: https://github.com/spearchucker667/Skill-RUP/compare/338c5675dab2479a3a4f2ac6d70fd0a12c250847...v3.0.0
[3.0.1]: https://github.com/spearchucker667/Skill-RUP/compare/v3.0.0...v3.0.1
[3.0.2]: https://github.com/spearchucker667/Skill-RUP/compare/v3.0.1...v3.0.2
