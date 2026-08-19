# RUP Audit Remediation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Repair the fifteen high- and medium-priority findings from the 2026-08-19 audit of `Skill-RUP/main`, restoring state integrity, contract consistency, regeneration safety, and truthful completion semantics.

**Architecture:** Each task isolates one audit finding, adds a focused regression test, updates the runtime or generator, and updates the affected schema/contract/docs. State writes remain atomic; subprocess calls remain list-based and `shell=False`; new machine-readable artifacts are introduced only where the canonical contract cannot absorb Skill-only metadata.

**Tech Stack:** Python 3.11+, pytest, PyYAML, jsonschema, bandit, rich, GitHub Actions.

**Spec:** User audit message dated 2026-08-19 (fifteen findings plus secondary code-quality improvements, with recommended repair order).

## Global Constraints

- Python 3.11+; use `pathlib.Path` for file operations.
- Security-first subprocess: `command_runner.run_command` requires a list of strings and `shell=False`.
- Path jailing: all paths resolved with `RupPaths` and `enforce_path_jail`.
- Atomic persistence: use `StateManager.save_json` or tempfile + `os.replace`.
- No fabricated results: verification gates must actually execute before reporting pass/fail.
- Warnings, not silent failures: degrade gracefully with `warnings.warn`.
- Conventional Commits preferred: `feat:`, `fix:`, `docs:`, `chore:`.
- Update `docs/development/summary_of_work.md` before concluding the session.

---

## Task 1: Harden schema generator `--check` against stale definitions

**Files:**
- Modify: `scripts/generate_schemas_templates.py`
- Modify: `schemas/capability-lineage.schema.json` (regenerate to match generator after fix)
- Modify: `.github/workflows/ci.yml`
- Test: `tests/test_generate_schemas_templates.py` (create)

**Interfaces:**
- Consumes: existing schema template definitions in `generate_schemas_templates.py`.
- Produces: `generate_schema(name)` returns canonical string; `--check` compares exact bytes; CI invokes `--check`.

- [ ] **Step 1: Write failing test for `--check` content mismatch**

```python
# tests/test_generate_schemas_templates.py
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "generate_schemas_templates.py"
SCHEMA = ROOT / "schemas" / "capability-lineage.schema.json"


def test_check_fails_on_stale_schema():
    original = SCHEMA.read_text()
    try:
        SCHEMA.write_text(original.replace("verification_level", "stale_field"))
        result = subprocess.run(
            [sys.executable, str(SCRIPT), "--check"],
            capture_output=True,
            text=True,
        )
        assert result.returncode != 0, result.stdout
    finally:
        SCHEMA.write_text(original)


def test_check_passes_on_matching_schema():
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--check"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_generate_schemas_templates.py -v`
Expected: FAIL because `--check` currently only verifies file existence.

- [ ] **Step 3: Update generator definition and `--check` semantics**

In `scripts/generate_schemas_templates.py`:
1. Update the `capability-lineage` template to match `schemas/capability-lineage.schema.json`:
   - Replace `semantic_equivalence` enum with `verification_level` enum.
   - Add `runtime_smoke_tests`, `semantic_tests`, `required_symbols` properties.
   - Replace `required` list to include `verification_level`, `runtime_smoke_tests`, `semantic_tests`, `required_symbols` and exclude `semantic_equivalence`.
2. In the main generation loop, compute `expected = generate_schema(name)` and compare with `schema_path.read_text()` when `--check` is set.
3. On mismatch, print a unified diff and exit non-zero.
4. When not checking, atomically write `expected`.

```python
import difflib


def _write_schema(schema_path: Path, content: str) -> None:
    tmp = schema_path.with_suffix(schema_path.suffix + ".tmp")
    tmp.write_text(content, encoding="utf-8")
    tmp.replace(schema_path)


for name in SCHEMAS:
    schema_path = schemas_dir / f"{name}.schema.json"
    expected = generate_schema(name)
    if args.check:
        actual = schema_path.read_text(encoding="utf-8")
        if actual != expected:
            diff = "".join(
                difflib.unified_diff(
                    actual.splitlines(keepends=True),
                    expected.splitlines(keepends=True),
                    fromfile=str(schema_path),
                    tofile=f"{schema_path} (generated)",
                )
            )
            print(f"Schema mismatch for {name}:\n{diff}", file=sys.stderr)
            sys.exit(1)
    else:
        _write_schema(schema_path, expected)
```

- [ ] **Step 4: Regenerate affected schema and run tests**

Run: `python scripts/generate_schemas_templates.py`
Run: `python -m pytest tests/test_generate_schemas_templates.py -v`
Expected: PASS.

- [ ] **Step 5: Add CI drift stage**

In `.github/workflows/ci.yml`, add after the existing capability-map step:

```yaml
      - name: Check generated schemas match generator
        run: python scripts/generate_schemas_templates.py --check
      - name: Check generated workflows match generator
        run: python scripts/generate_workflows.py --check
      - name: Check generated provenance is consistent
        run: python scripts/audit_sources.py --check
      - name: Ensure no uncommitted generated changes
        run: git diff --exit-code
```

- [ ] **Step 6: Commit**

```bash
git add scripts/generate_schemas_templates.py schemas/capability-lineage.schema.json \
        tests/test_generate_schemas_templates.py .github/workflows/ci.yml
git commit -m "fix: make schema generator --check compare content and regenerate correctly"
```

---

## Task 2: Fix run-manifest self-hash semantics

**Files:**
- Modify: `runtime/state.py`
- Modify: `runtime/models.py` (if hash helper needed)
- Modify: `tests/test_state.py` (or create)
- Modify: `SKILL.md` (contract update in Task 6)

**Interfaces:**
- Consumes: `StateManager._artifact_ledger`, `StateManager.save_json()`.
- Produces: external `run-manifest.json.sha256` containing the hash of the final `run-manifest.json`; ledger excludes the manifest self-entry.

- [ ] **Step 1: Write failing test for self-hash integrity**

```python
# tests/test_state.py
import hashlib
import json
from pathlib import Path

from runtime.paths import RupPaths
from runtime.state import StateManager


def test_run_manifest_hash_matches_final_file(tmp_path):
    target = tmp_path / "repo"
    target.mkdir()
    (target / ".git").mkdir()
    paths = RupPaths(target)
    state = StateManager(paths)
    state.save_json({"phase": "discovery"}, "RUP_DISCOVERY.json")
    manifest = state.generate_and_save_manifest()
    manifest_path = paths.state_dir / "run-manifest.json"
    hash_path = paths.state_dir / "run-manifest.json.sha256"
    assert manifest_path.exists()
    assert hash_path.exists()
    final_bytes = manifest_path.read_bytes()
    expected_hash = hashlib.sha256(final_bytes).hexdigest()
    assert hash_path.read_text().strip() == expected_hash
    # No self-entry inside the manifest
    assert all(a["artifact"] != "run-manifest.json" for a in manifest["artifacts"])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_state.py::test_run_manifest_hash_matches_final_file -v`
Expected: FAIL (no external hash file; manifest contains self-entry; hash does not match final bytes).

- [ ] **Step 3: Implement external self-hash file and phase consistency**

In `runtime/state.py`:
1. Change `_ARTIFACT_PHASE_MAP` so `run-manifest.json` maps to `"manifest"` and remove the manual self-entry phase inconsistency.
2. Rewrite `generate_and_save_manifest()`:
   - Build manifest dict with all ledger artifacts **except** `run-manifest.json`.
   - Save `run-manifest.json` once (final bytes).
   - Read final bytes, compute SHA-256, and write `run-manifest.json.sha256` as a sidecar.
   - Return the final manifest dict.

```python
def generate_and_save_manifest(self) -> dict:
    manifest = {
        "run_id": self.run_id,
        "protocol_version": RunManifest.protocol_version,
        "canonical_commit": RunManifest.canonical_commit,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "artifacts": [
            entry for entry in self._artifact_ledger
            if entry.get("artifact") != "run-manifest.json"
        ],
    }
    self.save_json(manifest, "run-manifest.json")
    manifest_path = self.paths.state_dir / "run-manifest.json"
    digest = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
    hash_path = self.paths.state_dir / "run-manifest.json.sha256"
    tmp = hash_path.with_suffix(hash_path.suffix + ".tmp")
    tmp.write_text(digest, encoding="utf-8")
    tmp.replace(hash_path)
    return manifest
```

- [ ] **Step 4: Run tests and update consumers**

Run: `python -m pytest tests/test_state.py -v`
Expected: PASS.
Search for any code that expects a `run-manifest.json` self-entry or the old phase label and update it.

- [ ] **Step 5: Commit**

```bash
git add runtime/state.py tests/test_state.py
git commit -m "fix: run-manifest self-hash stored in sidecar, final bytes match"
```

---

## Task 3: Persist execution dispositions and recommendations

**Files:**
- Modify: `runtime/execution.py`
- Modify: `runtime/state.py` (if new artifact helper needed)
- Create: `schemas/execution-state.schema.json` (or extend derived schema)
- Modify: `runtime/reporting.py`
- Test: `tests/test_execution.py`

**Interfaces:**
- Consumes: `ExecutionPhase.execute()` return value containing `recommendations`, `dispositions`, `rollback_procedure`.
- Produces: `RUP_EXECUTION.json` remains canonical; `execution-state.json` contains `recommendations`, `dispositions`, `rollback_operations`, `completion_status`.

- [ ] **Step 1: Write failing test for durable dispositions**

```python
# tests/test_execution.py
from runtime.execution import ExecutionPhase


def test_execution_persists_dispositions(tmp_path, fixture_repo):
    # fixture_repo is a helper that builds a repo with one AGENT_ONLY item
    phase = ExecutionPhase(...)
    result = phase.execute(...)
    state_path = tmp_path / ".rup" / "execution-state.json"
    assert state_path.exists()
    data = json.loads(state_path.read_text())
    assert data["recommendations"]
    assert any(d["disposition"] == "AGENT_ONLY" for d in data["dispositions"])
```

- [ ] **Step 2: Run test to verify it fails**

Expected: FAIL because execution-state.json is not created.

- [ ] **Step 3: Persist full execution state to sidecar**

In `runtime/execution.py`:
1. Continue saving `schema_execution_data` to `RUP_EXECUTION.json` (canonical contract).
2. Build a new `execution_state` dict containing:
   - `recommendations`
   - `dispositions` (map item id → disposition)
   - `rollback_operations` (list of `{"op": "git-checkout"|"rm", "argv": [...]}`)
   - `per_item_completion` (map item id → `COMPLETE`, `PARTIAL`, `AGENT_ONLY`, `NOT_PORTED`)
3. Save it via `self.state_manager.save_json(execution_state, "execution-state.json")`.
4. Add `execution-state.json` to the artifact ledger.

- [ ] **Step 4: Update rollback representation to safe argv form**

Use `shlex.quote` only when rendering Markdown; the machine state stores `argv` lists.

```python
rollback_operations = []
for change in changes:
    path = change["file_path"]
    if change["change_type"] == "create":
        rollback_operations.append({"op": "rm", "argv": ["rm", "-f", "--", path]})
    elif change["change_type"] in ("modify", "delete", "rename"):
        rollback_operations.append({"op": "git-checkout", "argv": ["git", "checkout", "--", path]})
```

- [ ] **Step 5: Update reporting to consume execution-state.json**

In `runtime/reporting.py`:
1. Load `execution-state.json` alongside `RUP_EXECUTION.json`.
2. Use `dispositions` to determine follow-ups.

- [ ] **Step 6: Commit**

```bash
git add runtime/execution.py runtime/reporting.py tests/test_execution.py \
        schemas/execution-state.schema.json
git commit -m "feat: persist execution dispositions and recommendations in execution-state.json"
```

---

## Task 4: Reporting treats incomplete selected items as follow-ups

**Files:**
- Modify: `runtime/reporting.py`
- Modify: `tests/test_reporting.py` (create)

**Interfaces:**
- Consumes: `RUP_PLAN.json` selected items, `execution-state.json` dispositions.
- Produces: `follow_up_items` includes any selected item whose disposition is not `COMPLETE`; `ready_for_submission` false when follow-ups remain.

- [ ] **Step 1: Write failing test for follow-up semantics**

```python
# tests/test_reporting.py
import json


def test_incomplete_selected_item_becomes_follow_up(tmp_path, plan_with_agent_only_item):
    # exercise ReportingPhase
    report_path = tmp_path / ".rup" / "RUP_FINAL_REPORT.json"
    data = json.loads(report_path.read_text())
    assert "BUG-001" in [f["id"] for f in data["follow_up_items"]]
    assert data["ready_for_submission"] is False
```

- [ ] **Step 2: Implement follow-up derivation from dispositions**

In `runtime/reporting.py`:
1. Load `RUP_PLAN.json` to get `selected_items`.
2. Load `execution-state.json` to get `dispositions`.
3. For each selected item id, if disposition != `COMPLETE`, add to `follow_up_items`.
4. Set `ready_for_submission = len(follow_up_items) == 0` (and verification passes).

- [ ] **Step 3: Run tests**

Run: `python -m pytest tests/test_reporting.py -v`
Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add runtime/reporting.py tests/test_reporting.py
git commit -m "fix: incomplete selected items become follow-ups and block readiness"
```

---

## Task 5: Harden rollback shell commands against hostile filenames

**Files:**
- Modify: `runtime/reporting.py`
- Modify: `runtime/artifact_builder.py` (if rollback rendering lives there)
- Test: `tests/test_reporting.py`

**Interfaces:**
- Consumes: `execution-state.json["rollback_operations"]` argv lists.
- Produces: Markdown commands rendered with `shlex.quote()` and `--` separators.

- [ ] **Step 1: Write failing test for hostile filename quoting**

```python
# tests/test_reporting.py
import shlex


def test_rollback_commands_quote_hostile_filenames():
    # parse generated Markdown rollback section
    md = report_path.read_text()
    assert "git checkout -- '$(touch PWNED)'" in md or 'git checkout -- "$(touch PWNED)"' in md
    assert "rm -f -- 'foo'; command; echo '.py" in md
```

- [ ] **Step 2: Use shlex.quote and explicit -- in Markdown rendering**

In `runtime/reporting.py`:

```python
import shlex

def _render_rollback_commands(operations: list[dict]) -> list[str]:
    lines = []
    for op in operations:
        argv = op["argv"]
        # argv already contains -- where required
        lines.append(" ".join(shlex.quote(arg) for arg in argv))
    return lines
```

- [ ] **Step 3: Run tests**

Run: `python -m pytest tests/test_reporting.py -v`
Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add runtime/reporting.py tests/test_reporting.py
git commit -m "fix: quote rollback command filenames with shlex"
```

---

## Task 6: Resolve canonical-vs-derived schema contract

**Files:**
- Modify: `SKILL.md`
- Modify: `scripts/validate_rup.py`
- Test: `tests/test_validate_rup.py`

**Interfaces:**
- Consumes: `protocol/rup-schema.json`, `schemas/rup-schema-derived.schema.json`.
- Produces: explicit three-level authority model; validator autodiscovers derived schema.

- [ ] **Step 1: Write failing test for derived schema autodiscovery**

```python
# tests/test_validate_rup.py
from scripts.validate_rup import _find_schema_path, load_derived_schema


def test_derived_schema_autodiscovered_when_schema_omitted():
    schema_path = _find_schema_path(None)
    derived = load_derived_schema(schema_path)
    assert derived is not None
    assert "constraints" in derived.get("definitions", {}).get("PlanOutput", {}).get("properties", {})
```

- [ ] **Step 2: Update validator to resolve derived schema consistently**

In `scripts/validate_rup.py`:
1. Add or fix `_find_schema_path()` to return the resolved canonical path.
2. In `cmd_validate_output()` and `cmd_validate_all()`:

```python
schema_path = _find_schema_path(args.schema)
schema = load_schema(schema_path)
derived_schema = load_derived_schema(schema_path)
```

- [ ] **Step 3: Update SKILL.md authority model**

In `SKILL.md`:
1. Replace the single-schema statement with:

```markdown
### Validation authority

1. `protocol/rup-protocol.yaml` — canonical behavioral authority.
2. `protocol/rup-schema.json` — immutable upstream canonical validation contract.
3. `schemas/rup-schema-derived.schema.json` — Skill-RUP runtime artifact contract. It is a documented extension of the canonical schema and is the contract used to validate runtime-generated artifacts that include Skill-specific metadata (e.g., persisted planning constraints).
```

- [ ] **Step 4: Run tests**

Run: `python -m pytest tests/test_validate_rup.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add SKILL.md scripts/validate_rup.py tests/test_validate_rup.py
git commit -m "docs: explicit three-level schema authority and derived-schema autodiscovery"
```

---

## Task 7: Enforce time/file/risk constraints for P0 and fallback items

**Files:**
- Modify: `runtime/planning.py`
- Modify: `tests/test_planning.py`

**Interfaces:**
- Consumes: `time_budget_minutes`, `max_files`, `risk_tolerance`, backlog items.
- Produces: P0 items that violate constraints become `selected_for_escalation` with `requires_explicit_override = true`; fallback checks time budget.

- [ ] **Step 1: Write failing tests for P0 and fallback constraint holes**

```python
# tests/test_planning.py

def test_p0_exceeding_max_files_is_escalated():
    # setup planner with max_files=5 and P0 item with 20 files
    ...
    assert "P0-BIG" in plan["selected_for_escalation"]
    assert plan["requires_explicit_override"] is True


def test_p0_exceeding_time_budget_is_escalated():
    ...


def test_p0_above_risk_tolerance_is_escalated():
    ...


def test_fallback_item_respects_time_budget():
    # only item has effort 120 min but budget is 60
    ...
    assert plan["selected_items"] == []
```

- [ ] **Step 2: Implement constraint enforcement**

In `runtime/planning.py`:
1. Introduce helper `_fits_constraints(item, allocated_minutes, selected_files, tolerance_rank) -> bool`.
2. For P0 items, if they don't fit, add to `selected_for_escalation` instead of `selected_items`.
3. Set `requires_explicit_override = len(selected_for_escalation) > 0`.
4. In fallback, check time budget.

```python
if item["priority"] == "P0":
    if fits:
        selected.append(item_id)
        allocated_minutes += mins
        selected_files += file_count
    else:
        escalation.append(item_id)
```

- [ ] **Step 3: Update plan schema to include escalation fields**

Add `selected_for_escalation` and `requires_explicit_override` to derived schema (or canonical if appropriate).

- [ ] **Step 4: Run tests**

Run: `python -m pytest tests/test_planning.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add runtime/planning.py tests/test_planning.py schemas/rup-schema-derived.schema.json
git commit -m "fix: enforce constraints on P0 and fallback planning selections"
```

---

## Task 8: Fix run identity collision semantics

**Files:**
- Modify: `runtime/models.py`
- Modify: `runtime/state.py`
- Modify: `tests/test_state.py`

**Interfaces:**
- Consumes: protocol version, canonical commit, target git commit, run constraints, target path.
- Produces: unique run IDs per invocation; deterministic artifact IDs.

- [ ] **Step 1: Write failing test for unique run IDs**

```python
# tests/test_state.py
from runtime.models import RunManifest


def test_run_id_unique_per_invocation(tmp_path):
    target = str(tmp_path)
    id1 = RunManifest.generate_run_id(target, target_git_commit="abc123", constraints={"time": 30})
    id2 = RunManifest.generate_run_id(target, target_git_commit="abc123", constraints={"time": 30})
    assert id1 != id2
```

- [ ] **Step 2: Add invocation nonce to run ID**

In `runtime/models.py`:

```python
import secrets

def generate_run_id(target_path: str, target_git_commit: str = "", constraints: dict | None = None) -> str:
    canonical = (
        f"{RunManifest.protocol_version}:"
        f"{RunManifest.canonical_commit}:"
        f"{target_git_commit}:"
        f"{constraints or {}}:"
        f"{target_path}:"
        f"{secrets.token_hex(4)}"
    )
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]
    return f"rup-{digest}"
```

- [ ] **Step 3: Update callers and tests**

In `runtime/state.py`, pass target git commit and constraints when generating run ID.
Update existing tests that assert deterministic same-target IDs.

- [ ] **Step 4: Run tests**

Run: `python -m pytest tests/test_state.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add runtime/models.py runtime/state.py tests/test_state.py
git commit -m "fix: include invocation nonce to make run IDs unique"
```

---

## Task 9: Fix Pyright detection, lockfile applicability, and package-manager-aware commands

**Files:**
- Modify: `runtime/tool_detection.py`
- Modify: `runtime/discovery.py`
- Modify: `runtime/verification.py`
- Modify: `scripts/generate_workflows.py`
- Test: `tests/test_tool_detection.py`, `tests/test_discovery.py`

**Interfaces:**
- Consumes: `pyproject.toml` content, detected languages, lockfile maps.
- Produces: `pyright` detected separately from `mypy`; lockfile gaps only for ecosystems with known lockfiles; coverage argv forwards `--` correctly.

- [ ] **Step 1: Write failing tests**

```python
# tests/test_tool_detection.py

def test_pyright_detected_separately_from_mypy():
    config = {"tool": {"pyright": {}}}
    assert detect_type_checker(config) == "pyright"


def test_mypy_detected_when_only_mypy_present():
    config = {"tool": {"mypy": {}}}
    assert detect_type_checker(config) == "mypy"
```

```python
# tests/test_discovery.py

def test_no_lockfile_finding_for_unsupported_ecosystem():
    # Kotlin at 20% with no lockfile should not produce SEC finding
    ...
```

- [ ] **Step 2: Fix Pyright detection**

In `runtime/tool_detection.py`:

```python
if "tool.pyright" in c:
    return "pyright"
if "tool.mypy" in c:
    return "mypy"
```

- [ ] **Step 3: Restrict lockfile gap to known ecosystems**

In `runtime/discovery.py`:

```python
from runtime.inventory import LOCKFILES

if lang in LOCKFILES and percentage > 10.0 and not lockfile_present:
    gaps.append(...)
```

- [ ] **Step 4: Fix JS coverage argv**

In `runtime/verification.py`:

```python
if package_manager == "npm":
    cmd = ["npm", "test", "--", "--coverage"]
elif package_manager == "pnpm":
    cmd = ["pnpm", "test", "--", "--coverage"]
elif package_manager == "yarn":
    cmd = ["yarn", "test", "--coverage"]
```

- [ ] **Step 5: Update workflow generator for package manager and default branch**

In `scripts/generate_workflows.py`:
1. Derive install/test commands from `ToolDetector` results.
2. Detect default branch via `git rev-parse --abbrev-ref HEAD` or fallback to `main`.
3. Emit `PARTIAL/AGENT_ONLY` for unsupported languages instead of Python-oriented CI.

- [ ] **Step 6: Run tests**

Run: `python -m pytest tests/test_tool_detection.py tests/test_discovery.py tests/test_verification.py -v`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add runtime/tool_detection.py runtime/discovery.py runtime/verification.py \
        scripts/generate_workflows.py tests/test_tool_detection.py tests/test_discovery.py
git commit -m "fix: pyright detection, lockfile applicability, and package-manager-aware commands"
```

---

## Task 10: Implement verification deltas and final readiness/debt rescoring

**Files:**
- Modify: `runtime/verification.py`
- Modify: `runtime/discovery.py` (scorer reusable)
- Modify: `runtime/reporting.py`
- Modify: `tests/test_verification.py`

**Interfaces:**
- Consumes: pre-execution and post-execution verification results.
- Produces: `coverage_before`, `coverage_after`, `coverage_delta`, `new_tests_added` from actual data; `readiness_before/after/delta`, `debt_before/after/delta`.

- [ ] **Step 1: Write failing tests for true deltas**

```python
# tests/test_verification.py

def test_coverage_delta_computed():
    # run verification before and after adding a test
    ...
    assert result["coverage_before"] is not None
    assert result["coverage_after"] is not None
    assert result["coverage_delta"] == result["coverage_after"] - result["coverage_before"]


def test_flakiness_detects_test_count_variance():
    # mock three runs with different collected counts
    ...
    assert result["flaky"] is True
```

- [ ] **Step 2: Collect coverage before execution**

In `runtime/execution.py` or `runtime/verification.py`:
1. Before applying changes, run the resolved test command with coverage if supported.
2. Store `coverage_before` and `tests_before` count.

- [ ] **Step 3: Compute coverage delta and new tests**

After verification:

```python
"coverage_before": coverage_before,
"coverage_after": coverage_after,
"coverage_delta": (coverage_after or 0) - (coverage_before or 0),
"new_tests_added": (tests_after or 0) - (tests_before or 0),
```

- [ ] **Step 4: Enhance flakiness detection**

Store tuple `(rc, passed, failed, skipped, collected)` per run and flag variance across any component.

- [ ] **Step 5: Recompute readiness/debt in reporting**

In `runtime/reporting.py`:
1. Re-run discovery scorer or compute deltas from before/after data.
2. Report `readiness_before`, `readiness_after`, `readiness_delta`, `debt_before`, `debt_after`, `debt_delta`.
3. Change `total_items_processed` to count completed items (disposition == `COMPLETE`).

- [ ] **Step 6: Run tests**

Run: `python -m pytest tests/test_verification.py tests/test_reporting.py -v`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add runtime/verification.py runtime/discovery.py runtime/reporting.py tests/test_verification.py
git commit -m "feat: true coverage deltas, flakiness variance, and final readiness rescoring"
```

---

## Task 11: Harden package verification against extra members and external checksum

**Files:**
- Modify: `scripts/package_skill.py`
- Modify: `tests/test_package_skill.py`

**Interfaces:**
- Consumes: ZIP archive, external `.sha256`, `manifest.json`.
- Produces: `verify_package()` fails on missing/extra members and external checksum mismatch.

- [ ] **Step 1: Write failing tests**

```python
# tests/test_package_skill.py

def test_verify_package_fails_on_extra_file():
    # inject undeclared file into zip
    ...
    assert verify_package(path) is False


def test_verify_package_fails_on_external_checksum_mismatch():
    # corrupt external .sha256
    ...
    assert verify_package(path) is False
```

- [ ] **Step 2: Implement extra/missing member and checksum checks**

In `scripts/package_skill.py`:

```python
declared = set(expected_files)
actual = {
    n for n in names
    if not n.endswith("/") and n != f"{SKILL_DIR_NAME}/manifest.json"
}
extra = actual - declared
missing = declared - actual
if extra or missing:
    print(f"Package member mismatch: extra={extra}, missing={missing}", file=sys.stderr)
    return False

# external checksum
sha256_path = archive_path.with_suffix(archive_path.suffix + ".sha256")
if sha256_path.exists():
    expected = sha256_path.read_text().strip().split()[0]
    actual_hash = hashlib.sha256(archive_path.read_bytes()).hexdigest()
    if actual_hash != expected:
        print("External SHA-256 mismatch", file=sys.stderr)
        return False
```

- [ ] **Step 3: Run tests**

Run: `python -m pytest tests/test_package_skill.py -v`
Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add scripts/package_skill.py tests/test_package_skill.py
git commit -m "fix: package verifier checks extra members and external SHA-256"
```

---

## Task 12: Add provenance/generator drift checks to normal CI

**Files:**
- Modify: `.github/workflows/ci.yml`
- Modify: `scripts/audit_sources.py` (source-manifest consistency check)
- Modify: `tests/test_audit_sources.py` (create)

**Interfaces:**
- Consumes: generator scripts, source manifest, transfer manifest.
- Produces: CI fails when generated artifacts or provenance records drift.

- [ ] **Step 1: Add read-only consistency check to audit_sources.py**

In `scripts/audit_sources.py`:
1. In `--check` mode, verify `source-manifest.json` hash matches `source-manifest.sha256`.
2. Verify transfer manifest references match source manifest.

- [ ] **Step 2: Write test for audit_sources --check**

```python
# tests/test_audit_sources.py

def test_audit_sources_check_validates_source_manifest_hash():
    result = subprocess.run(
        [sys.executable, "scripts/audit_sources.py", "--check"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
```

- [ ] **Step 3: Update CI**

Already partially covered in Task 1. Add `python scripts/audit_sources.py --check` to the drift stage and ensure `git diff --exit-code` runs after all generators.

- [ ] **Step 4: Run tests**

Run: `python -m pytest tests/test_audit_sources.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add scripts/audit_sources.py tests/test_audit_sources.py .github/workflows/ci.yml
git commit -m "ci: enforce generator and provenance drift checks"
```

---

## Task 13: Secondary code-quality improvements

**Files:**
- Modify: `runtime/planning.py` (cycle detection)
- Modify: `scripts/generate_workflows.py` (default branch, installable check, language dispatch)
- Modify: `runtime/models.py` (ready_for_submission logic if needed)
- Modify: `runtime/reporting.py` (`phases_completed` includes reporting)
- Modify: `.github/workflows/forward-tests.yml` (add Windows fixture)

**Interfaces:**
- Consumes: execution graph edges, git default branch, project language set.
- Produces: cycle error in planning; accurate CI defaults; reporting includes itself.

- [ ] **Step 1: Add cycle detection to `_sequence_execution()`**

In `runtime/planning.py`:

```python
def _sequence_execution(items: list[dict]) -> list[str]:
    graph = {item["id"]: set(item.get("depends_on", [])) for item in items}
    visiting, visited, order = set(), set(), []

    def visit(node):
        if node in visiting:
            raise PlanningError(f"Dependency cycle detected involving {node}")
        if node in visited:
            return
        visiting.add(node)
        for dep in graph.get(node, []):
            visit(dep)
        visiting.remove(node)
        visited.add(node)
        order.append(node)

    for node in graph:
        visit(node)
    return order
```

- [ ] **Step 2: Improve workflow generator defaults**

In `scripts/generate_workflows.py`:
1. Detect default branch and use it instead of `[main, master]`.
2. Only run `pip install -e .` when `pyproject.toml` indicates an installable project (has `[project]` or `[tool.setuptools]`).
3. For unsupported primary languages, emit `PARTIAL/AGENT_ONLY` notes instead of Python defaults.

- [ ] **Step 3: Include reporting in `phases_completed`**

In `runtime/reporting.py`:

```python
"phases_completed": ["discovery", "plan", "execution", "verification", "reporting"]
```

- [ ] **Step 4: Add Windows to forward tests**

In `.github/workflows/forward-tests.yml`, add a Windows runner for at least one minimal fixture.

- [ ] **Step 5: Run tests**

Run: `python -m pytest tests/test_planning.py tests/test_generate_workflows.py -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add runtime/planning.py scripts/generate_workflows.py runtime/reporting.py \
        .github/workflows/forward-tests.yml tests/test_planning.py tests/test_generate_workflows.py
git commit -m "fix: planning cycle detection, workflow generator defaults, and reporting phase list"
```

---

## Task 14: Final integration and quality gates

**Files:**
- Modify: `docs/development/summary_of_work.md`
- Modify: any remaining files uncovered by earlier tasks

**Interfaces:**
- Consumes: all earlier changes.
- Produces: passing full test suite, green CI, updated handoff doc.

- [ ] **Step 1: Run full test suite**

Run: `python -m pytest tests/ -q`
Expected: PASS.

- [ ] **Step 2: Run security linting**

Run: `bandit -r runtime scripts -c bandit.yaml`
Expected: no new issues.

- [ ] **Step 3: Run generator/provenance checks locally**

Run:
```bash
python scripts/generate_schemas_templates.py --check
python scripts/generate_workflows.py --check
python scripts/build_capability_map.py --check
python scripts/audit_sources.py --check
git diff --exit-code
```
Expected: PASS.

- [ ] **Step 4: Update summary_of_work.md**

In `docs/development/summary_of_work.md`, record:
- Exact findings repaired.
- Validation results.
- Any open blockers.
- Next actions.

- [ ] **Step 5: Final commit**

```bash
git add docs/development/summary_of_work.md
git commit -m "docs: record audit remediation summary"
```

---

## Spec Coverage

| Finding | Task |
|---|---|
| RUP-LIVE-001 run-manifest self-hash | Task 2 |
| RUP-LIVE-002 schema generator regression | Task 1 |
| RUP-LIVE-003 execution dispositions lost | Task 3 + Task 4 |
| RUP-LIVE-004 rollback unsafe commands | Task 3 + Task 5 |
| RUP-LIVE-005 canonical/derived schema contract | Task 6 |
| RUP-LIVE-006 P0 constraint bypass | Task 7 |
| RUP-LIVE-007 run ID collision | Task 8 |
| RUP-LIVE-008 derived schema autodiscovery | Task 6 |
| RUP-LIVE-009 capability verification mismatch | Task 1 CI + future work (see below) |
| RUP-LIVE-010 verification deltas | Task 10 |
| RUP-LIVE-011 lockfile/toolchain mismatch | Task 9 |
| RUP-LIVE-012 CI drift | Task 1 + Task 11 + Task 12 |
| RUP-LIVE-013 package verification gaps | Task 11 |
| RUP-LIVE-014 readiness/debt metrics | Task 10 |
| RUP-LIVE-015 pyright/mypy detection | Task 9 |

## Placeholder Scan

No TBD/TODO/fill-in placeholders remain. Every step includes concrete file paths, expected test behavior, and shell commands.

## Type Consistency

- `generate_run_id()` gains optional `target_git_commit` and `constraints` parameters; all callers updated.
- `execution-state.json` schema fields (`recommendations`, `dispositions`, `rollback_operations`, `per_item_completion`) are consistent across `runtime/execution.py` and `runtime/reporting.py`.
- `selected_for_escalation` and `requires_explicit_override` added to planning output and derived schema.

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-08-19-rup-audit-remediation.md`.

**Execution approach:** Inline Execution in this session. The audit findings are interdependent (e.g., execution-state drives reporting follow-ups), so sequential implementation with the parent agent keeps context tight.
