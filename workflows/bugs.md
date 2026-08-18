# Bugs Workflow

## Purpose
Fix identified bugs with regression tests

## Canonical Rules & Process
- **Select bug from backlog**: Highest severity, lowest complexity
- **Write failing test**: Test must reproduce the bug
- **Implement minimal fix**: Prefer targeted over broad changes
- **Verify test passes**: Run 3x to check for flakiness
- **Update documentation**: Add to changelog, update affected docs

## Raw Protocol Data
```yaml
bug_report_template: '## Bug: {title}


  **Severity**: {severity}

  **File**: {file}:{line}

  **Root Cause**: {root_cause}


  ### Reproduction

  ```{language}

  {reproduction_code}

  ```


  ### Fix

  {fix_description}


  ### Regression Test

  {test_name} in {test_file}

  '
description: Fix identified bugs with regression tests
id: ws_bugs
priority: P0
process:
- details: Highest severity, lowest complexity
  step: Select bug from backlog
- details: Test must reproduce the bug
  step: Write failing test
- details: Prefer targeted over broad changes
  step: Implement minimal fix
- details: Run 3x to check for flakiness
  step: Verify test passes
- details: Add to changelog, update affected docs
  step: Update documentation

```

## Validation
Must comply with `rup-schema.json`.
