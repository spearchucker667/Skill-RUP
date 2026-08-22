# Operational Workflow: Monorepo Orchestration

## Purpose
Scoped execution across workspace packages (npm/yarn/pnpm workspaces, nx, turborepo, lerna, cargo workspaces, go work) with per-package tooling and dependency-ordered execution.

## Operational Command
```bash
python3 -m runtime.cli run --target <dir> --changed-packages
```

## Canonical Rules & Process
Follow canonical RUP directives for this workflow.

## Raw Protocol Data
```yaml
description: Scoped execution across workspace packages (npm/yarn/pnpm workspaces, nx, turborepo, lerna, cargo workspaces,
  go work) with per-package tooling and dependency-ordered execution.
cli_command: python3 -m runtime.cli run --target <dir> --changed-packages
```

## Validation
Must comply with `rup-schema.json`.
