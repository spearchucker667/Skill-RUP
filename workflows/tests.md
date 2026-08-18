# Tests Workflow

## Purpose
Add missing tests for critical paths

## Canonical Rules & Process
- Focus on business logic and edge cases
- Follow existing test conventions
- Use AAA pattern: Arrange, Act, Assert
- Mock external dependencies
- Aim for determinism (no flaky tests)

## Raw Protocol Data
```yaml
coverage_targets:
  e2e: Critical paths
  integration: 60%
  unit: 80%
description: Add missing tests for critical paths
guidelines:
- Focus on business logic and edge cases
- Follow existing test conventions
- 'Use AAA pattern: Arrange, Act, Assert'
- Mock external dependencies
- Aim for determinism (no flaky tests)
id: ws_tests
naming_conventions:
  go: Test{Function}_{Scenario}
  javascript: describe/it pattern
  python: test_{function}_{scenario}_{expected}
  rust: test_{function}_{scenario}
priority: P0

```

## Validation
Must comply with `rup-schema.json`.
