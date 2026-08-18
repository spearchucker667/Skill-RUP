# 2 Planning & prioritization Workflow

## Purpose
Planning & Prioritization

## Canonical Rules & Process
1. **Backlog Generation**: Convert gaps to actionable items Assign P0/P1/P2/P3 priority Estimate effort (minutes) Identify dependencies Define acceptance criteria
1. **Risk Analysis**: Assess change risk (low/medium/high) Identify breaking changes Determine rollback complexity Flag manual review needs
1. **Work Selection**: Select high-impact, low-risk items Respect time budget Ensure independence or proper sequencing Balance priorities (mostly P0)
1. **Execution Planning**: Define execution order Plan verification for each item Identify tools needed Set checkpoints

## Raw Protocol Data
```yaml
id: phase_2_planning
name: Planning & Prioritization
agent: planning_agent
timeout_minutes: 5
steps:
- id: '2.1'
  name: Backlog Generation
  actions:
  - Convert gaps to actionable items
  - Assign P0/P1/P2/P3 priority
  - Estimate effort (minutes)
  - Identify dependencies
  - Define acceptance criteria
- id: '2.2'
  name: Risk Analysis
  actions:
  - Assess change risk (low/medium/high)
  - Identify breaking changes
  - Determine rollback complexity
  - Flag manual review needs
- id: '2.3'
  name: Work Selection
  actions:
  - Select high-impact, low-risk items
  - Respect time budget
  - Ensure independence or proper sequencing
  - Balance priorities (mostly P0)
- id: '2.4'
  name: Execution Planning
  actions:
  - Define execution order
  - Plan verification for each item
  - Identify tools needed
  - Set checkpoints
```

## Validation
Must comply with `rup-schema.json`.
