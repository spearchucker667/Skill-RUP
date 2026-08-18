# Source Authority

This document defines the source authority and precedence for the `Skill-RUP` repository.

## Authority Order

The following authority order applies to all implementation choices, unless direct evidence proves a newer intentionally maintained RUP source should be used:

1. `spearchucker667/RUP-Protocol` at the recorded canonical commit.
2. Its canonical `rup-schema.json` for validation structure.
3. Its canonical `rup-protocol.yaml` for behavioral and process semantics.
4. Its validators and tests for executable validation behavior.
5. RUP examples, docs, AGENTS guidance, security, governance, and legacy snapshots.
6. Local `.reference/` only as a supplementary corpus after classification (no canonical files were found here).
7. `Skill-HQE` only as an architectural pattern for skill packaging and runtime design, never as RUP behavioral authority.

## Source Isolation

Every file considered for porting must be classified into exactly one category:
- `RUP_CANONICAL_MATCH`
- `RUP_MODIFIED`
- `RUP_LEGACY`
- `RUP_SUPPLEMENTAL`
- `HQE_OR_HQE_WORKBENCH`
- `FOREIGN_OR_UNKNOWN`
- `GENERATED_OR_BUILD_ARTIFACT`

If a file cannot be classified, it is marked `FOREIGN_OR_UNKNOWN` and is excluded from the runtime skill.
