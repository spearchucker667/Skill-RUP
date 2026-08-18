# User Guide

This guide covers how to utilize Skill-RUP manually or via an autonomous agent.

## Core Commands
The primary interface is `runtime/cli.py`.

```bash
# Discovery Phase (analyzes codebase)
python3 -m runtime.cli discovery /path/to/target-repo

# Planning Phase (generates execution plan)
python3 -m runtime.cli plan /path/to/target-repo

# Execution Phase (applies changes)
python3 -m runtime.cli execute /path/to/target-repo

# Verification Phase (tests changes)
python3 -m runtime.cli verify /path/to/target-repo

# Reporting Phase (summarizes outcomes)
python3 -m runtime.cli report /path/to/target-repo
```

## Agent Directives
Agents should be prompted to read `SKILL.md`, which defines the following workflow triggers:
- `/RUP`: Complete lifecycle execution.
- `/RUP discovery`: Triggers discovery phase.
- `/RUP plan`: Triggers planning.
- `/RUP execute`: Triggers execution.
- `/RUP verify`: Triggers verification.
- `/RUP report`: Triggers reporting.
- `/RUP rollback`: Reverts changes.
- `/RUP handoff`: Ends the session cleanly.

## Common Workstreams
The protocol supports specific focus modes:
- **Hotfix:** For rapid bug fixing.
- **Security:** Focused on vulnerability patching.
- **Documentation:** For pure documentation updates.

If verification fails, the agent is expected to catch the non-zero exit code, diagnose the issue via the generated `RUP_VERIFICATION.json`, and re-attempt execution.
