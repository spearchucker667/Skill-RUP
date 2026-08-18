# Contributing to Skill-RUP

We welcome contributions to Skill-RUP!

## Project Scope
Skill-RUP is a portable agent skill that translates RUP Protocol v3 into an agent-readable workflow and deterministic runtime. The scope of this project is the runtime implementation and the agent interface (`SKILL.md`), **not** the underlying RUP Protocol.

## Local Setup & Prerequisites
- Python 3.11+
- `pip install pyyaml jsonschema pytest`

## Architecture Orientation
- `protocol/`: The exact synchronized RUP protocol and schema. Do not manually edit.
- `SKILL.md`: The agent-facing instruction file.
- `workflows/`: Separated workflows dynamically generated from the protocol.
- `schemas/`: Standalone JSON schemas extracted from the protocol.
- `runtime/`: Python execution engine (discovery, planning, execution, verification, reporting).
- `scripts/`: Tooling to validate and build the skill.

## Source-Authority Rules & Protocol Updates
If you wish to change the underlying methodology, you must contribute to the [upstream RUP Protocol repository](https://github.com/spearchucker667/RUP-Protocol). Once merged upstream, you can submit a PR here to update the `protocol/` directory and run the generators.

## Generated-File Policy
When updating the canonical protocol or runtime behavior, you **must** run the generation scripts to update the capability map, schemas, and workflows:
```bash
python scripts/generate_workflows.py
python scripts/generate_schemas_templates.py
python scripts/build_capability_map.py --check
```

## Testing & Validation
All code must pass the test suite and schema validation:
```bash
pytest tests/
python scripts/validate_rup.py all .
python scripts/forward_test.py --fixtures .
```

## Pull Request Expectations
1. Use the provided PR template.
2. Adhere to the code and documentation style.
3. Validate your changes locally.
4. If modifying runtime capabilities, ensure they pass the security scanning and the forward tests.
5. If making a security-sensitive change, review the Security Policy.

## Filing Issues
Please use the provided GitHub Issue forms for Bugs, Features, or Documentation. Do not submit security vulnerabilities via public issues.

## Commit Convention
We prefer standard Conventional Commits (e.g., `feat:`, `fix:`, `docs:`, `chore:`).
