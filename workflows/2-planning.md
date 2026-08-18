# 2 Planning Workflow

## Purpose
No description provided.

## Canonical Rules & Process
1. **Backlog Generation**: 
1. **Risk Analysis**: 
1. **Work Selection**: 
1. **Execution Planning**: 

## Raw Protocol Data
```yaml
agent: planning_agent
id: phase_2_planning
name: Planning & Prioritization
output_template: "# PLAN\n\n## Constraints\n- **Time Budget**: {time_budget} minutes\n\
  - **Max Files**: {max_files}\n- **Risk Tolerance**: {risk_tolerance}\n\n## Backlog\n\
  \n### P0 (Critical) \u2014 {p0_count} items\n{p0_items}\n\n### P1 (High) \u2014\
  \ {p1_count} items\n{p1_items}\n\n### P2 (Medium) \u2014 {p2_count} items\n{p2_items}\n\
  \n## Selected for This Run\n| ID | Title | Effort | Risk |\n|----|-------|--------|------|\n\
  {selected_table}\n\n## Execution Order\n1. {item_1}\n2. {item_2}\n...\n\n## Risk\
  \ Analysis\n- **Breaking Changes**: {breaking_possible}\n- **Manual Review Required**:\
  \ {manual_review}\n- **Rollback Complexity**: {rollback_complexity}\n"
steps:
- actions:
  - Convert gaps to actionable items
  - Assign P0/P1/P2/P3 priority
  - Estimate effort (minutes)
  - Identify dependencies
  - Define acceptance criteria
  id: '2.1'
  name: Backlog Generation
- actions:
  - Assess change risk (low/medium/high)
  - Identify breaking changes
  - Determine rollback complexity
  - Flag manual review needs
  id: '2.2'
  name: Risk Analysis
- actions:
  - Select high-impact, low-risk items
  - Respect time budget
  - Ensure independence or proper sequencing
  - Balance priorities (mostly P0)
  id: '2.3'
  name: Work Selection
- actions:
  - Define execution order
  - Plan verification for each item
  - Identify tools needed
  - Set checkpoints
  id: '2.4'
  name: Execution Planning
timeout_minutes: 5

```

## Validation
Must comply with `rup-schema.json`.
