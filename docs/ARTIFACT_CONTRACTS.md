# Artifact Contracts

The Skill-RUP framework establishes strict, deterministic contracts for every artifact generated or consumed during the AI lifecycle.

## Machine-Readable States
All deterministic state is preserved in JSON format conforming to strict JSON Schemas (Draft 2020-12):
- `RUP_DISCOVERY.json`: Output of discovery phase. Governed by `schemas/discovery.schema.json`.
- `RUP_PLAN.json`: Output of the planning phase. Governed by `schemas/plan.schema.json`.
- `RUP_EXECUTION.json`: Output of the execution phase. Governed by `schemas/execution.schema.json`.
- `RUP_VERIFICATION.json`: Verification and testing outcomes. Governed by `schemas/verification.schema.json`.

## Human-Readable Reports
- Markdown equivalent reports (`RUP_DISCOVERY.md`, `RUP_PLAN.md`, etc.) are synthesized from JSON state for human review.
- These reports provide diffs, rationale, and execution context.

## Schema Validation
At any point, the integrity of an artifact can be validated via `validate_rup.py`:
```bash
python scripts/validate_rup.py schema schemas/discovery.schema.json RUP_DISCOVERY.json
```
Failure to conform to the schema constitutes an automatic pipeline failure in `forward_test.py` and the `validate-skill` GitHub workflow.
