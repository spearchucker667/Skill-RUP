# Development Guide

This guide is for those developing the Skill-RUP framework itself.

## Architecture
The framework acts as an autonomous shell executing RUP Protocol workflows. 
- `scripts/`: Tooling for schema and workflow generation. Run `forward_test.py` locally to emulate an agent loop.
- `runtime/`: The actual execution logic for discovery, planning, execution, and verification.

## Testing Locally
Run the unit/integration tests using pytest:
```bash
pytest tests/
```

Run the multi-agent simulation to check behavior against the current target directory:
```bash
python scripts/forward_test.py --fixtures .
```

## Adding Capabilities
Whenever a canonical node in `rup-protocol.yaml` updates:
1. Update `protocol/rup-protocol.yaml`
2. Run `python scripts/generate_workflows.py`
3. Run `python scripts/generate_schemas_templates.py`
4. Run `python scripts/build_capability_map.py --check`

This guarantees lineage and capability mapping remain accurate.
