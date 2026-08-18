# Operational Workflow: Monorepo Orchestration

## Purpose
Scoped execution across workspace packages (pnpm, nx, turborepo, cargo workspaces, go work).

## Operational Command
```bash
python3 -m runtime.cli run --target <dir>
```

## Canonical Rules & Process
Follow canonical RUP directives for this workflow.

## Raw Protocol Data
```yaml
description: Scoped execution across workspace packages (pnpm, nx, turborepo, cargo workspaces, go work).
cli_command: python3 -m runtime.cli run --target <dir>
```

## Validation
Must comply with `rup-schema.json`.
