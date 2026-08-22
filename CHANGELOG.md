# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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

[3.0.0]: https://github.com/spearchucker667/Skill-RUP/compare/338c5675dab2479a3a4f2ac6d70fd0a12c250847...v3.0.0
