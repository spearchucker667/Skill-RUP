# Skill-RUP P0 Blocker Remediation Design

**Date:** 2026-08-19  
**Target commit:** `a1c8314f9177d873878f408f3f04227db256e798`  
**Scope:** The four P0 findings from the 2026-08-19 static source audit.

## 1. RUP-XFER-001 — Execution reads planning constraints from `plan-state.json`

### Problem
`ExecutionPhase.execute()` loads constraints from `RUP_PLAN.json`, but the canonical/derived schema separation moved Skill-only planning state (`constraints`, `selected_for_escalation`, `requires_explicit_override`) into `plan-state.json`. This allows execution to use default bounds (`max_files=20`, `risk_tolerance="medium"`) even when planning was invoked with stricter values.

### Design
- In `runtime/execution.py`, load `plan-state.json` via `StateManager.load_json("plan-state.json")`.
- Use `plan_state.get("constraints", {})` as the authoritative source for `max_files`, `risk_tolerance`, and `time_budget`.
- Keep a fallback read from `RUP_PLAN.json` only for legacy artifacts, emitting a `warnings.warn` deprecation notice.
- Add a real integration test in `tests/test_execution.py` that runs `PlanningPhase` with `max_files=1` and `risk_tolerance="low"`, persists state, then runs `ExecutionPhase` against the same `StateManager`, asserting the constraints propagated correctly.

### Acceptance
- `pytest tests/test_execution.py` includes a test proving planner-to-executor constraint propagation.
- Existing execution tests continue to pass.

## 2. RUP-VERIFY-001 — Tool gates fail closed on command failure

### Problem
`_count_lint_violations()` parses stdout lines into violation counts. If the linter exits non-zero but prints nothing to stdout, `violations = 0`, and `_gate_passed("lint")` treats lint as passing because it only checks `violations_after == 0`.

### Design
- Extend the lint/build/type-check result dictionaries to include a `command_succeeded: bool` field (`rc == 0`).
- Update `_gate_passed()` helpers to require both `command_succeeded == True` and the relevant success metric (e.g., `violations_after == 0`).
- Treat any non-zero return code as a gate failure, even when parsed violations are zero.
- Add a test in `tests/test_verification.py` that mocks a linter returning `rc=1` with empty stdout and asserts the lint gate reports failure.

### Acceptance
- A linter crashing or missing executable cannot be certified as passing.
- All existing verification tests still pass.

## 3. RUP-SEC-001 — File symlinks bypass the target-repository jail

### Problem
Inventory, discovery, verification, secret scanning, and packaging read repository files directly via `Path.read_text()` / `stat()` without resolving symlinks against the target root. A file symlink pointing outside the repo can leak external files.

### Design
- Add `runtime/security.py::iter_jailed_files(root: Path)` that yields only regular files whose resolved real path is contained within `root.resolve()`.
- For each candidate, if `candidate.is_symlink()`, resolve the target and call `enforce_path_jail(root, target)` before yielding.
- Migrate the following consumers to use the jailed iterator:
  - `runtime/inventory.py`
  - `runtime/discovery.py`
  - `runtime/verification.py` (`_project_files`)
  - `runtime/redaction.py` secret scanner
  - `runtime/provenance.py` file hashing
- Add a unit test and a forward fixture with a file symlink to an external sentinel file, asserting the walker rejects it and no scanner reads the target.

### Acceptance
- A file symlink to `/etc/passwd` or an external sentinel is never read as part of target analysis.
- Existing symlink fixture still passes (directory symlinks remain outside scope).

## 4. RUP-SEC-002 — Untrusted target code executes before the adversarial-content gate

### Problem
Verification runs tests/builds/type-checks before the prompt-injection/adversarial scan, allowing repository-controlled code to execute before static adversarial analysis completes.

### Design
- In `runtime/cli.py::run_full_lifecycle`, reorder so that static adversarial/prompt-injection scanning runs immediately after discovery and before any gate that executes target code.
- Add CLI flags:
  - `--allow-exec` — required when the runtime would otherwise refuse to execute target-controlled commands.
  - `--sandbox {required,preferred,off}` — default `required`; if `required` and no sandbox is available, refuse execution gates.
- In `runtime/command_runner.py`, default to a scrubbed environment allowlist and cap captured stdout/stderr to a configurable bound.
- Add a regression test with adversarial instructions in a target file; assert execution halts before tests/build run unless `--allow-exec` is supplied.

### Acceptance
- By default, a repository containing adversarial instructions cannot trigger test/build execution.
- `--allow-exec` explicitly opts into execution gates.

## Validation Plan

After implementation, run:

```bash
python -m pytest tests/ -q
python scripts/generate_schemas_templates.py --check
python scripts/generate_workflows.py --check
python scripts/build_capability_map.py --check
python scripts/audit_sources.py --check
python scripts/validate_rup.py --schema protocol/rup-schema.json all .
bandit -r runtime scripts -c bandit.yaml
python -m compileall runtime scripts
```

All must pass before the sub-project is considered complete.
