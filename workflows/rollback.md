# Operational Workflow: Rollback & Reversion

## Purpose
Deterministic reversion of executed changes using baseline git checkpoints and cleanup commands.

## Operational Command
```bash
git checkout -- <modified_files> && rm -f <created_files>
```

## Canonical Rules & Process
Follow canonical RUP directives for this workflow.

## Raw Protocol Data
```yaml
description: Deterministic reversion of executed changes using baseline git checkpoints and cleanup commands.
cli_command: git checkout -- <modified_files> && rm -f <created_files>
```

## Validation
Must comply with `rup-schema.json`.
