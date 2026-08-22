# Operational Workflow: Rollback & Reversion

## Purpose
Deterministic reversion of executed changes from the structured, platform-neutral rollback operations recorded in execution-state.json (restore_content / remove_file / restore_deleted / move_back).

## Operational Command
```bash
python3 -m runtime.cli rollback --target <dir>
```

## Canonical Rules & Process
Follow canonical RUP directives for this workflow.

## Raw Protocol Data
```yaml
description: Deterministic reversion of executed changes from the structured, platform-neutral rollback operations recorded
  in execution-state.json (restore_content / remove_file / restore_deleted / move_back).
cli_command: python3 -m runtime.cli rollback --target <dir>
```

## Validation
Must comply with `rup-schema.json`.
