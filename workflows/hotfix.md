# Operational Workflow: Hotfix

## Purpose
Isolated, surgical fix for production regressions with minimal change footprint.

## Operational Command
```bash
python3 -m runtime.cli run --target <dir> --max-files 3 --risk-tolerance low
```

## Canonical Rules & Process
Follow canonical RUP directives for this workflow.

## Raw Protocol Data
```yaml
description: Isolated, surgical fix for production regressions with minimal change footprint.
cli_command: python3 -m runtime.cli run --target <dir> --max-files 3 --risk-tolerance low
```

## Validation
Must comply with `rup-schema.json`.
