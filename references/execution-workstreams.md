# Execution Workstreams - Canonical Reference

This document outlines the canonical workstreams and execution rules for the Execution phase of RUP Protocol v3.0.0.

## Phase 3: Execution

### Workstream Dispatch

**Purpose**: Execute planned backlog items through specialized workstreams.

**Available Workstreams**:

#### 1. Bug Fixes Workstream
- **ID**: `bug-fixes`
- **Purpose**: Fix identified bugs with regression tests
- **Process**:
  1. Select bug from backlog (highest severity, lowest complexity)
  2. Write failing test that reproduces the bug
  3. Implement minimal fix (prefer targeted over broad changes)
  4. Verify test passes (run 3x to check for flakiness)
  5. Update documentation (add to changelog, update affected docs)
- **Verification**: Test must pass, no regressions introduced

#### 2. Tests Workstream
- **ID**: `tests`
- **Purpose**: Add missing tests or improve test coverage
- **Process**:
  1. Identify untested or under-tested code
  2. Write comprehensive tests (unit, integration, e2e as appropriate)
  3. Run tests to verify they pass
  4. Ensure tests are maintainable and follow best practices
- **Verification**: All new tests pass, coverage metrics improve

#### 3. CI/CD Workstream
- **ID**: `ci-cd`
- **Purpose**: Add or fix CI/CD workflows
- **Process**:
  1. Identify missing or broken CI/CD configurations
  2. Create/fix workflow files with best practices
  3. Test locally if possible
  4. Ensure security best practices are followed
- **Verification**: Workflows are syntactically valid, can be dry-run

#### 4. Documentation Workstream
- **ID**: `documentation`
- **Purpose**: Add or improve documentation
- **Process**:
  1. Identify missing or outdated documentation
  2. Write clear, comprehensive docs
  3. Follow existing documentation style and structure
  4. Add examples where helpful
- **Verification**: Documentation is readable, accurate, and complete

#### 5. Governance Workstream
- **ID**: `governance`
- **Purpose**: Add or improve governance files
- **Process**:
  1. Identify missing governance files (CODEOWNERS, templates, etc.)
  2. Create files following repository conventions
  3. Ensure proper formatting and placement
- **Verification**: Files are valid, follow conventions, and are properly placed

#### 6. Security Workstream
- **ID**: `security`
- **Purpose**: Address security findings
- **Process**:
  1. Review identified security issues
  2. Implement fixes following security best practices
  3. Verify secrets are properly redacted
  4. Add security tests where possible
- **Verification**: Security scans pass, no new vulnerabilities introduced

### Baseline State Snapshotting

**Purpose**: Capture repository state before execution for rollback safety.

**Rules**:
- Record git commit hash before any changes
- Track all file modifications, creations, and deletions
- Store baseline in `.rup/state/` directory
- Never modify files outside the target repository
- Respect `--dry-run` flag to preview changes without applying

**Baseline Data**:
- Git HEAD commit hash
- List of all files with their hashes
- Git status (clean or dirty)
- Branch name and remote

### Deterministic Execution

**Purpose**: Execute backlog items in a deterministic, repeatable manner.

**Rules**:
- Execute items in `execution_order` from planning phase
- For each item:
  1. Check preconditions (dependencies completed, no conflicts)
  2. Apply changes (create, modify, or delete files)
  3. Track all changes with `backlog_item_id` linkage
  4. Run local verification if applicable
  5. Record execution results
- If any item fails:
  - Stop execution
  - Generate rollback instructions
  - Preserve partial state for debugging

**Change Tracking**:
- Each change MUST be linked to a specific `backlog_item_id`
- Record:
  - `file_path`: path to modified file
  - `change_type`: create, modify, delete, or rename
  - `rationale`: explanation of why this change was made
  - `backlog_item_id`: the item that caused this change

**Execution Safety**:
- Never overwrite unrelated dirty worktree changes
- Always check if files exist before modifying
- Use atomic operations where possible
- Provide clear error messages on failures

### Rollback Safety

**Purpose**: Ensure changes can be safely reverted if needed.

**Rules**:
- Generate rollback instructions for each executed item
- Store rollback state in `.rup/rollback/` directory
- Include:
  - List of all changes made
  - Git commands to revert (git checkout, git stash, etc.)
  - Manual rollback steps if needed
  - Verification commands to confirm rollback success

**Rollback Granularity**:
- Per-item rollback: revert changes from a specific backlog item
- Full rollback: revert all changes from the execution

**Required Outputs**:
- `changes`: Array of all ExecutionChange objects
- `commits`: Array of all ExecutionCommit objects
- `local_verification`: Results of local verification runs
- `rollback_instructions`: How to revert changes if needed
