# Tests Workflow

## Purpose
Add missing tests for critical paths

## Canonical Rules & Process
Follow canonical RUP directives for this workflow.

## Raw Protocol Data
```yaml
id: ws_tests
priority: P0
description: Add missing tests for critical paths
guidelines:
- Focus on business logic and edge cases
- Follow existing test conventions
- 'Use AAA pattern: Arrange, Act, Assert'
- Mock external dependencies
- Aim for determinism (no flaky tests)
coverage_targets:
  unit: 80%
  integration: 60%
  e2e: Critical paths
naming_conventions:
  python: test_{function}_{scenario}_{expected}
  javascript: describe/it pattern
  go: Test{Function}_{Scenario}
  rust: test_{function}_{scenario}
```

## Validation
Must comply with `rup-schema.json`.
