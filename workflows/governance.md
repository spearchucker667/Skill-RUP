# Governance Workflow

## Purpose
Add governance and automation

## Canonical Rules & Process
Follow canonical RUP directives for this workflow.

## Raw Protocol Data
```yaml
adr_template: '# ADR {number}: {title}


  ## Status

  {Proposed|Accepted|Deprecated|Superseded}


  ## Context

  {What is the issue?}


  ## Decision

  {What is the change?}


  ## Consequences

  {What becomes easier/harder?}


  ## Alternatives Considered

  {What else was considered?}

  '
branch_protection:
  main:
    allow_deletions: false
    allow_force_pushes: false
    dismiss_stale_reviews: true
    require_branches_up_to_date: true
    require_code_owner_reviews: true
    require_status_checks:
    - test
    - lint
    - security
    required_reviews: 1
    restrict_pushes: true
description: Add governance and automation
id: ws_governance
priority: P1

```

## Validation
Must comply with `rup-schema.json`.
