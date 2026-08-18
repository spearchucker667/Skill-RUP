# Bug Fixes Workflow

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
id: ws_bugs
priority: P0
description: Fix identified bugs with regression tests
process:
- step: Select bug from backlog
  details: Highest severity, lowest complexity
- step: Write failing test
  details: Test must reproduce the bug
- step: Implement minimal fix
  details: Prefer targeted over broad changes
- step: Verify test passes
  details: Run 3x to check for flakiness
- step: Update documentation
  details: Add to changelog, update affected docs
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
```

## Validation
Must comply with `rup-schema.json`.
