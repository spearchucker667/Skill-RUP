# Governance Workflow

## Purpose
Add governance and automation

## Canonical Rules & Process
Follow canonical RUP directives for this workflow.

## Raw Protocol Data
```yaml
id: ws_governance
priority: P1
description: Add governance and automation
branch_protection:
  main:
    required_reviews: 1
    dismiss_stale_reviews: true
    require_code_owner_reviews: true
    require_status_checks:
    - test
    - lint
    - security
    require_branches_up_to_date: true
    restrict_pushes: true
    allow_force_pushes: false
    allow_deletions: false
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
```

## Validation
Must comply with `rup-schema.json`.
