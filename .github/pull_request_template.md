## Summary
<!-- Briefly describe the purpose of this PR -->

## Why
<!-- Why is this change necessary? Link to any relevant issues. -->

## Changes
<!-- List the specific technical changes made in this PR -->

## Validation
<!-- How did you test these changes? Provide command output or verification details. -->

## RUP capability/source impact
<!-- Does this require updating capability maps, schemas, or workflows? -->

## Security / compatibility impact
<!-- Does this introduce security risks, secret leakage paths, or break compatibility with older agents? -->

## Checklist
- [ ] I have read the [CONTRIBUTING.md](../CONTRIBUTING.md) guide.
- [ ] I have executed the test suite locally (`pytest tests/`).
- [ ] I have executed schema validation (`python scripts/validate_rup.py all .`).
- [ ] I have regenerated artifacts if necessary (`scripts/generate_workflows.py`, `scripts/generate_schemas_templates.py`, `scripts/build_capability_map.py --check`).
- [ ] I have updated the `CHANGELOG.md`.
- [ ] I have reviewed the code for secret leakage and local-path hygiene.
