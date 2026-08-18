# Agent Instructions

This repository is the implementation of `Skill-RUP`, a portable, agent-native skill based on RUP Protocol v3.0.0.

## Mandatory Session Handoff

Before concluding your session, you **MUST** update `docs/summary_of_work.md`.
Log your exact accomplishments, open blockers, validation results, and next actions. Do not end a session without updating the ledger.

## Project Context
- **Target Repository**: `/Users/super_user/Projects/Skill-RUP/`
- **Canonical Source**: `https://github.com/spearchucker667/RUP-Protocol` (Use commit `c3d6f70375db15d53db2fba76d70b5b7c9cf98bb` for protocol version 3.0.0)
- **Reference Material**: `.reference/` contains mixed canonical RUP, HQE Workbench, and other files. *Never* copy blindly from `.reference/` without classifying via source audit.

## Architecture
- `protocol/`: Canonical machine-readable RUP sources.
- `SKILL.md`: Runtime contract and workflow router.
- `workflows/`: Separated playbook steps.
- `runtime/`: Portable Python 3.11+ scripts for deterministic execution.
- `scripts/`: Validation and building utilities.
- `provenance/`: Lineage and mapping records to ensure nothing is lost.
