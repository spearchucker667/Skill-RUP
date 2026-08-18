# Troubleshooting

## Missing Dependencies
**Symptom:** `ModuleNotFoundError: No module named 'yaml'`
**Cause:** Required pip packages are missing.
**Resolution:** Run `pip install pyyaml jsonschema`.

## Validation Failures
**Symptom:** Schema validation fails during the `verify` phase.
**Cause:** The generated `RUP_*.json` artifact does not comply with the Draft 2020-12 schema.
**Resolution:** Inspect the exact JSON output against `protocol/rup-schema.json`. Ensure the agent did not hallucinate properties.

## Path Jail Escapes
**Symptom:** `PermissionError: Path traversal detected`
**Cause:** The agent attempted to write or read a file outside the designated workspace.
**Resolution:** This is a security feature. Correct the agent's instructions to ensure it only operates within the workspace.
