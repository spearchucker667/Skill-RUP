# Planning Heuristics - Canonical Reference

This document outlines the canonical heuristics and rules for the Planning phase of RUP Protocol v3.0.0.

## Phase 2: Planning

### 2.1 Backlog Generation

**Purpose**: Convert identified gaps into actionable backlog items.

**Rules**:
- Each gap MUST map to at least one backlog item
- Backlog items MUST have:
  - Unique `id` (e.g., ITEM-001, ITEM-002)
  - `priority` (P0, P1, P2, P3)
  - `category` (tests, security, docs, ci, governance, refactor, etc.)
  - `title` (concise description)
  - `description` (detailed explanation)
  - `scope` (files and packages affected)
  - `risk` (low, medium, high)
  - `estimated_effort_minutes` (numeric estimate)
  - `verification_method` (how to verify completion)
  - `dependencies` (array of item IDs this depends on)
  - `acceptance_criteria` (list of success conditions)

**Priority Mapping**:
- P0 (Critical): Security vulnerabilities, broken builds, data loss risks
- P1 (High): Test failures, missing critical features, blocking issues
- P2 (Medium): Quality improvements, technical debt reduction
- P3 (Low): Nice-to-haves, documentation polish

### 2.2 Risk Analysis

**Purpose**: Assess and document risks associated with planned changes.

**Rules**:
- Analyze each backlog item for:
  - **Breaking changes**: Will this break existing functionality?
  - **Manual review required**: Does this need human review before merge?
  - **Rollback complexity**: How difficult is it to revert if something goes wrong?
- Document risk factors for the overall plan
- Flag items that require special attention

**Risk Categories**:
- **Breaking changes**: API changes, database schema changes, config format changes
- **High rollback complexity**: Changes that are hard to revert (database migrations, data deletions)
- **Manual review required**: Security changes, permission changes, payment-related code

### 2.3 Work Selection & Budgeting

**Purpose**: Select items for execution within constraints.

**Rules**:
- Default time budget: 45 minutes
- Configurable via `--time-budget` flag
- Respect maximum file change bounds (default: no limit, configurable)
- Select items using these heuristics (in order):
  1. P0 items first (all critical issues must be addressed)
  2. P1 items next (high-impact improvements)
  3. P2 items (medium priority)
  4. P3 items only if time permits
- Within each priority level, prefer:
  - Items with lower effort estimates
  - Items with higher impact scores
  - Items with fewer dependencies
  - Items that can be verified automatically

**Budget Enforcement**:
- Track total estimated effort
- Stop selection when budget would be exceeded
- Include buffer time (10% of budget) for verification

### 2.4 Execution Planning & Checkpoints

**Purpose**: Define execution order and verification checkpoints.

**Rules**:
- Topologically sort items by dependencies
- Group related items into workstreams:
  - `bug-fixes`: Fixing identified bugs
  - `tests`: Adding or improving tests
  - `ci-cd`: CI/CD pipeline improvements
  - `documentation`: Documentation updates
  - `governance`: Governance and policy files
  - `security`: Security-related changes
- Define checkpoints after each workstream
- Each checkpoint must include:
  - Verification method (tests, manual review, etc.)
  - Success criteria
  - Rollback instructions if failed

**Execution Order Rules**:
- Dependencies must be executed first
- Higher-priority items execute before lower-priority
- Group similar changes together for efficiency
- Security and test items should be interleaved with feature changes

**Required Outputs**:
- `backlog`: Full list of generated backlog items
- `selected_items`: IDs of items selected for execution
- `execution_order`: Ordered list of item IDs to execute
- `estimated_effort`: total_minutes, confidence
