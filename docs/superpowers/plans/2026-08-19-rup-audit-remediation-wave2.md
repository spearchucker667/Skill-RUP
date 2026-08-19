# RUP Audit Remediation Wave 2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans or superpowers:subagent-driven-development to implement this plan task-by-task.

**Goal:** Repair the integration defects and GitHub Actions issues identified in the 2026-08-19 wave-2 audit of `Skill-RUP/main`.

**Spec:** User audit message dated 2026-08-19 (wave 2), including twelve numbered findings plus workflow/packaging recommendations.

## Global Constraints

- Python 3.11+; use `pathlib.Path`.
- Security-first subprocess (`shell=False`, list argv).
- Atomic persistence via `StateManager.save_json` or tempfile + `os.replace`.
- No fabricated results.
- Update `docs/development/summary_of_work.md` before concluding.

---

## Task 1: Fix `release-package.yml` workflow syntax and harden release job

**Files:**
- `.github/workflows/release-package.yml`

**Steps:**
1. Move `permissions` from step scope to `jobs.package.permissions`.
2. Pin third-party actions to full commit SHAs.
3. Remove redundant external `sha256sum` step (package script already emits `.sha256`).
4. Add validation stage: pytest, generator/provenance checks, validator, `git diff --exit-code`.
5. Run `skills-ref validate` against the extracted package contents, not a raw source copy.
6. Add `timeout-minutes`, `concurrency`, and pip caching.

---

## Task 2: Distinguish new-run vs resume lifecycle semantics

**Files:**
- `runtime/state.py`
- `runtime/cli.py`

**Steps:**
1. Make `StateManager` accept a `resume: bool` flag (default `False`).
2. Only call `_recover_run_id()` when `resume=True`.
3. `run`/`all` commands create fresh `StateManager(resume=False)`.
4. Phase-only commands (`discovery`, `plan`, `execute`, `verify`, `report`) default to `resume=False`; add a `--resume` flag to allow recovery of an incomplete session.
5. Update tests to assert fresh IDs for `all` and recovered IDs for `--resume`.

---

## Task 3: Exclude checksum sidecar from manifest ledger

**Files:**
- `runtime/state.py`

**Steps:**
1. Exclude both `run-manifest.json` and `run-manifest.json.sha256` from `artifacts` in `generate_and_save_manifest()`.
2. In `_rebuild_artifact_ledger()`, use `_infer_artifact_type()` and skip `.sha256` sidecars.
3. Add a regression test that runs two lifecycles against the same target and asserts the second manifest does not contain the old checksum sidecar.

---

## Task 4: Enforce P0 escalation as a lifecycle and readiness gate

**Files:**
- `runtime/cli.py`
- `runtime/reporting.py`

**Steps:**
1. After planning in `run_full_lifecycle()`, check `requires_explicit_override`.
2. If true and no override flag is provided, halt before execution, emit a clear diagnostic, and set exit status non-zero.
3. Add a CLI flag `--override-escalation` (or similar) to allow explicit continuation.
4. In reporting, block `ready_for_submission` whenever `selected_for_escalation` is non-empty, regardless of verification status.
5. Add tests for halted lifecycle and blocked readiness.

---

## Task 5: Make `execution-state.json` handling fail-closed

**Files:**
- `runtime/reporting.py`

**Steps:**
1. Default missing completion to `UNKNOWN` (not `COMPLETE`).
2. If selected items exist and `execution-state.json` is missing/malformed, treat all selected items as incomplete and block readiness.
3. Update tests to assert fail-closed behavior.

---

## Task 6: Fix validator routing for `execution-state.json`

**Files:**
- `scripts/validate_rup.py`
- `schemas/execution-state.schema.json`

**Steps:**
1. Add exact derived-artifact mapping `"execution-state.json": "execution-state"` ahead of fuzzy `"execution"` detection.
2. Add a test that validates a deliberately invalid `execution-state.json` and expects failure.
3. Ensure `_derived_schema_name()` prioritizes exact matches.

---

## Task 7: Split extended planning metadata into `plan-state.json`

**Files:**
- `runtime/planning.py`
- `runtime/cli.py`
- `runtime/reporting.py`
- `schemas/rup-schema-derived.schema.json`
- `SKILL.md`

**Steps:**
1. Keep `RUP_PLAN.json` canonical (backlog, selected_items, execution_order, risk_analysis, estimated_effort).
2. Persist Skill-only fields `constraints`, `selected_for_escalation`, `requires_explicit_override` into `plan-state.json`.
3. Update reporting and CLI to load `plan-state.json`.
4. Update `schemas/rup-schema-derived.schema.json` to give it a unique `$id` and include `plan-state` and `execution-state` schemas.
5. Regenerate derived schema under generator control.

---

## Task 8: Bring derived umbrella schema under generator control

**Files:**
- `scripts/generate_schemas_templates.py`
- `schemas/rup-schema-derived.schema.json`

**Steps:**
1. Generate `rup-schema-derived.schema.json` as canonical upstream schema + deterministic extension overlay.
2. Include `execution-state` and `plan-state` definitions in the generated output.
3. Ensure `--check` compares the generated derived schema bytes.
4. Add CI check that derived schema matches generator.

---

## Task 9: Strengthen provenance transfer-manifest coverage

**Files:**
- `runtime/provenance.py`

**Steps:**
1. In `verify_transfer_manifest()`, assert recorded source paths equal the full reconstructed upstream tree path set.
2. Verify source blob identity for omitted records as well as transferred records.
3. Update tests.

---

## Task 10: Fix remaining runtime gaps

**Files:**
- `runtime/tool_detection.py` — Pyright vs mypy detection.
- `runtime/discovery.py` — lockfile applicability for Java/Kotlin/Swift/C#/etc.
- `runtime/verification.py` — true `coverage_before`, `new_tests_added`, `violations_before`, multi-dimensional flakiness.
- `runtime/planning.py` — dependency cycle detection.
- `runtime/execution.py` — package-manager-aware CI, default branch, unsupported ecosystems.

**Steps:**
1. Verify/repair each item; add focused regression tests.

---

## Task 11: Harden packaging verification

**Files:**
- `scripts/package_skill.py`

**Steps:**
1. Add exact member-set check (`actual == declared + manifest`).
2. Validate external `.sha256` sidecar during `--verify`.
3. Add regression tests.

---

## Task 12: Refactor GitHub Actions topology

**Files:**
- `.github/workflows/ci.yml`
- `.github/workflows/forward-tests.yml`
- `.github/workflows/validate-skill.yml`
- `.github/workflows/security-scan.yml`

**Steps:**
1. In `ci.yml`, split OS test matrix from a single Ubuntu `integrity` job (generators, provenance, validator, actionlint, `git diff`).
2. Add a `required` aggregate job.
3. Add `permissions`, `concurrency`, timeouts, pip caching, and action SHA pinning.
4. In `forward-tests.yml`, add a Windows runner matrix (at minimum one fixture).
5. In `validate-skill.yml`, validate the packaged artifact after extraction, not raw source.
6. In `security-scan.yml`, add global `permissions: contents: read`, keep CodeQL `security-events: write`, add caching/concurrency/timeouts, pin actions.
7. Add `actionlint` to the integrity job.

---

## Task 13: Final integration and quality gates

**Files:**
- `docs/development/summary_of_work.md`

**Steps:**
1. Run full test suite.
2. Run bandit.
3. Run generator/provenance/validator checks and `git diff --exit-code`.
4. Update summary_of_work.md.
5. Final commit.
